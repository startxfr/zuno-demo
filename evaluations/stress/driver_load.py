"""Load and saturation drivers of the stress runner (WP-309, ADR-0624).

Where the demo drivers prove that a path works, these push on it:

  load-unifai-scenarios  replays the message-bearing scenarios of evaluations/<agent>/scenarios.yaml as UnifAI turns,
                         round-robin over the active agents (STRESS_LOAD_AGENTS, default tekos,arkos,comage), one fresh
                         session per turn, concurrently. It replaces the sequential `day2_bulk.py` loop of the per-agent
                         Jobs, which keeps working untouched.
  load-ai-gateway        direct chat completions on the ai-gateway Service with the same prompts, no UI in between
  load-mcp-gateway       tool calls (search_confluence, varied queries) on the mcp-gateway REST path
  saturation             a SAMPLER, not a load: while the other drivers run it reads, every 15 s, the signals that say a
                         platform is saturated (vLLM requests waiting and KV-cache pressure, the p95 of the two gateways
                         at the Istio sidecars, Postgres backends) and reports the max, the mean and whether a limit was
                         crossed. It needs a token Prometheus accepts: grant the Job's ServiceAccount
                         `cluster-monitoring-view` (the row says so when Thanos answers 401 or 403).

load-ai-gateway sends `X-Zuno-Quota-Class` from STRESS_LOAD_QUOTA_CLASS (default `loadtest`, the class of WP-306: 250,000
tokens an hour per user, fail-closed; only the zuno-stresstest client may choose a class). Until 2026-11-21 it asked for
`stresstest` (2,000 tokens per 5 minutes per user), the class of the functional drivers, which is no budget for a load. An
empty value sends no header and leaves the class to the persona's group. The class is read by stress_runner.quota_headers,
the one place the drivers take it from. Direct MaaS calls per model are not here: the ai-gateway reaches MaaS with the stress
class's own credential (WP-306), which is the path a user takes; a driver holding a MaaS token itself would test another one.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import time

import yaml

_EVALUATIONS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EVALUATIONS))
sys.path.insert(0, str(_EVALUATIONS / "common"))

import golden_path_probe as gpp  # noqa: E402
import unifai_target as ut  # noqa: E402
from stress_runner import quota_headers, register, row  # noqa: E402

DEFAULT_AGENTS = "tekos,arkos,comage"
LOAD_MAX_TOKENS = 256  # the completion allowance of one load-ai-gateway call
QUERIES = ("onboarding", "kubernetes", "openshift", "architecture", "runbook", "security", "gpu", "release notes")
_CORPUS = {}


# -- the scenario corpus ---------------------------------------------------------------------------------------------


def _scenario_file(agent: str, env) -> "pathlib.Path | None":
    """`<agent>-scenarios.yaml` flat next to the drivers in the Job, evaluations/<agent>/scenarios.yaml in the repository."""
    for candidate in (pathlib.Path(env.get("STRESS_DIR") or ".") / f"{agent}-scenarios.yaml", _EVALUATIONS / agent / "scenarios.yaml"):
        if candidate.is_file():
            return candidate
    return None


def scenario_corpus(env) -> list:
    """[(agent, message)] of every message-bearing scenario of the active agents, in file order, cached per agent list."""
    agents = tuple(a.strip() for a in (env.get("STRESS_LOAD_AGENTS") or DEFAULT_AGENTS).split(",") if a.strip())
    if agents not in _CORPUS:
        corpus = []
        for agent in agents:
            path = _scenario_file(agent, env)
            if path is None:
                continue
            data = yaml.safe_load(path.read_text()) or {}
            corpus += [(agent, s["message"]) for s in data.get("scenarios", []) if s.get("message")]
        _CORPUS[agents] = corpus
    return _CORPUS[agents]


def pick(corpus: list, i: int, worker: int = 0):
    """The corpus entry of iteration `i`: round-robin, offset by the worker so concurrent workers do not repeat one prompt."""
    return corpus[(i + worker * 7) % len(corpus)] if corpus else None


def _unifai_url(ctx) -> str:
    return ctx.env.get("UNIFAI_URL") or "https://unifai-ui-zuno-unifai." + ctx.env.get("CLUSTER_BASE_DOMAIN", "apps.invalid")


# -- load drivers ----------------------------------------------------------------------------------------------------


def _agent_turn(ctx, persona: str, agent: str, message: str):
    """One blocking UnifAI turn of `agent` as `persona`, in a fresh session that is deleted afterwards (a thread)."""
    target = ut.UnifaiTarget(ctx.env.get("DEMO_PERSONA_PASSWORD", ""), ui_url=_unifai_url(ctx), agent=agent, team_name=f"agent-{agent}")
    try:
        return target.run(persona, message, timeout=240)
    finally:
        target.cleanup()


@register("load-unifai-scenarios", family="load",
          description="the message-bearing scenarios of the active agents replayed as concurrent UnifAI turns (replaces day2_bulk's sequential loop)",
          needs=("unifai", "the agents' teams", "a persona pool"))
async def load_unifai_scenarios(ctx, i):
    entry = pick(scenario_corpus(ctx.env), i, ctx.worker)
    if entry is None:
        return [row("load-unifai-scenarios", "load", "corpus", "load", False, "no message-bearing scenario found for STRESS_LOAD_AGENTS")]
    agent, message = entry
    started = time.monotonic()
    run = await asyncio.to_thread(_agent_turn, ctx, ctx.persona, agent, message)
    ok = run.status == 200 and bool((run.reply or "").strip())
    return [row("load-unifai-scenarios", "load", f"scenario-{agent}", "load", ok,
                f"status={run.status} agent={agent} {len(run.reply or '')} chars", (time.monotonic() - started) * 1000)]


@register("load-ai-gateway", family="load",
          description="chat completions straight on the ai-gateway Service, scenario prompts, no UI in between",
          needs=("ai-gateway", "a persona pool"))
async def load_ai_gateway(ctx, i):
    entry = pick(scenario_corpus(ctx.env), i, ctx.worker)
    prompt = entry[1] if entry else "Say OK."
    token = await ctx.token()
    headers = {"Authorization": "Bearer " + token, "X-Zuno-Data-Classification": "C1", "X-Zuno-Agent": "tekos",
               "X-Zuno-Task": "answer-technical-question", **quota_headers(ctx, "load"), **ctx.trace_headers("load-ai-gateway", i)}
    started = time.monotonic()
    # max_tokens 256, not 64 (2026-11-21): gpt-oss spends most of a small allowance on its reasoning, and 16 % of the answers
    # of the aggressive campaign ended by length, empty or cut. A call now costs up to four times the completion tokens:
    # size the profile's budget.max_tokens with that in mind.
    r = await ctx.http.post(f"{ctx.ai_gateway}/v1/chat/completions", headers=headers, timeout=180, json={
        "model": "auto", "max_tokens": LOAD_MAX_TOKENS, "stream": False, "messages": [{"role": "user", "content": prompt}]})
    ms = (time.monotonic() - started) * 1000
    answered = False
    if r.status_code == 200:
        try:
            body = r.json()
            ctx.add_tokens((body.get("usage") or {}).get("total_tokens") or 0)
            message = (body.get("choices") or [{}])[0].get("message") or {}
            answered = bool(((message.get("content") or "") + (message.get("reasoning_content") or "")).strip())
        except ValueError:
            pass
    return [row("load-ai-gateway", "load", "chat", "load", answered,
                f"status={r.status_code}" + ("" if answered else f" {r.text[:120]}"), ms)]


@register("load-mcp-gateway", family="load",
          description="search_confluence through the mcp-gateway REST path with varied queries",
          needs=("mcp-gateway", "mcp-confluence", "a persona pool"))
async def load_mcp_gateway(ctx, i):
    token = await ctx.token()
    query = QUERIES[(i + ctx.worker) % len(QUERIES)]
    headers = {"Authorization": "Bearer " + token, "X-Zuno-Data-Classification": "C2", "X-Zuno-Agent": "tekos",
               "X-Zuno-Task": "answer-technical-question", **ctx.trace_headers("load-mcp-gateway", i)}
    started = time.monotonic()
    r = await ctx.http.post(f"{ctx.mcp_gateway}/v1/tools/search_confluence/invoke", headers=headers, json={"query": query}, timeout=60)
    ms = (time.monotonic() - started) * 1000
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    result = body.get("result") or {}
    verdict = gpp.judge_tool({"status": r.status_code, "server": body.get("mcp_server"), "ms": body.get("duration_ms"),
                              "results": len(result.get("results") or []) if isinstance(result, dict) else 0,
                              "error": "" if r.status_code == 200 else r.text[:160]})
    return [row("load-mcp-gateway", "load", "search_confluence", "load", verdict.status == gpp.PASS, f"status={r.status_code} {verdict.detail}", ms)]


# -- the saturation sampler ------------------------------------------------------------------------------------------

# (name, PromQL, limit): `limit` is where the signal says "saturated" (None: reported only). The series are the ones the
# dashboards plot (gitops/charts/grafana/templates/dashboard-ai-models.yaml, -mesh-gateway, -data); first values, tuned
# after the first runs.
SIGNALS = (
    ("vllm requests waiting", "max(vllm:num_requests_waiting)", 4.0),
    ("vllm requests running", "sum(vllm:num_requests_running)", None),
    ("vllm kv-cache usage", "max(vllm:kv_cache_usage_perc)", 0.9),
    ("p95 ai-gateway and mcp-gateway at the sidecar (ms)",
     'histogram_quantile(0.95, sum by (le) (rate(istio_request_duration_milliseconds_bucket{reporter="destination",'
     'destination_workload=~"ai-gateway|mcp-gateway"}[1m])))', 10000.0),
    ("postgres backends", "sum(pg_stat_database_numbackends)", 160.0),
)
# The Istio series live in the mesh's own Prometheus (zuno-mesh, no auth; the Grafana datasource `mesh-prometheus`), not in Thanos.
MESH_SIGNALS = {"p95 ai-gateway and mcp-gateway at the sidecar (ms)"}
MESH_PROMETHEUS_URL = "http://mesh-monitoring-prometheus.zuno-mesh.svc.cluster.local:9090"
SA_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"


def _thanos_token(env) -> str:
    if env.get("THANOS_TOKEN"):
        return env["THANOS_TOKEN"]
    try:
        return pathlib.Path(SA_TOKEN).read_text().strip()
    except OSError:
        return ""


async def _query(client, base: str, token: str, promql: str):
    """The value of an instant query (float), None when the series does not exist; raises on a refusal."""
    r = await client.get(f"{base}/api/v1/query", params={"query": promql}, headers={"Authorization": f"Bearer {token}"} if token else {})
    if r.status_code in (401, 403):
        raise PermissionError(f"status={r.status_code} {base} refused the Job's token: grant its ServiceAccount cluster-monitoring-view")
    r.raise_for_status()
    result = (r.json().get("data") or {}).get("result") or []
    if not result:
        return None
    try:
        value = float(result[0]["value"][1])
    except (KeyError, IndexError, ValueError, TypeError):
        return None
    return None if value != value else value  # NaN: histogram_quantile of no traffic


def summarise_signals(samples: list, signals=SIGNALS) -> list:
    """[(name, max, mean, count, limit, saturated)] over the samples (dicts {name: value}); exceptions are skipped."""
    out = []
    for name, _promql, limit in signals:
        values = [s[name] for s in samples if isinstance(s, dict) and s.get(name) is not None]
        if values:
            top = max(values)
            out.append((name, top, sum(values) / len(values), len(values), limit, limit is not None and top >= limit))
        else:
            out.append((name, None, None, 0, limit, False))
    return out


def _finish_saturation(ctx, samples):
    errors = [s for s in samples if isinstance(s, Exception)]
    taken = [s for s in samples if isinstance(s, dict)]
    if not taken:
        why = str(errors[0])[:200] if errors else "no sample taken"
        return [row("saturation", "saturation", "sampler", "saturation", False, f"{why}")]
    rows = []
    for name, top, mean, count, limit, saturated in summarise_signals(taken):
        if top is None:
            rows.append(row("saturation", "saturation", name, "saturation", True, f"no series for this signal in {len(taken)} sample(s)"))
            continue
        flag = f" SATURATED (limit {limit:g})" if saturated else (f" (limit {limit:g})" if limit is not None else "")
        rows.append(row("saturation", "saturation", name, "saturation", not saturated, f"max={top:g} mean={mean:.4g} samples={count}{flag}"))
    if errors:
        rows.append(row("saturation", "saturation", "sampler", "saturation", False, f"{len(errors)} sample(s) failed: {str(errors[0])[:160]}"))
    return rows


@register("saturation", family="saturation", sampler=True, interval=15, finish=_finish_saturation,
          description="a sampler: vLLM queue and KV-cache, gateway p95 at the sidecars and Postgres backends while the load runs",
          needs=("Thanos querier", "cluster-monitoring-view for the Job's ServiceAccount", "the mesh Prometheus (zuno-mesh) for the sidecar p95"))
async def saturation(ctx, i):
    import httpx

    base = (ctx.env.get("THANOS_URL") or "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091").rstrip("/")
    token = _thanos_token(ctx.env)
    values = {}
    # verify=False: the querier serves the cluster's service CA, as the Grafana datasource does (tlsSkipVerify, demo scope)
    async with httpx.AsyncClient(verify=False, timeout=30) as client:  # noqa: S501
        mesh = (ctx.env.get("MESH_PROMETHEUS_URL") or MESH_PROMETHEUS_URL).rstrip("/")
        for name, promql, _limit in SIGNALS:
            values[name] = await (_query(client, mesh, "", promql) if name in MESH_SIGNALS else _query(client, base, token, promql))
    return values
