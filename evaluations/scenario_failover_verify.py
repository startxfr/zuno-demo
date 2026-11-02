#!/usr/bin/env python3
"""Orchestrator for WP-105/ADR-0536's node failover drill: fires one live
chat turn each at Comage and Tekos and determines which `ai-gateway`
provider actually served each one.

Comage's `check-deal-status` task is the actual fallback under test
(local-wesh -> local-qwen35 when the wesh pod is cordoned/killed - see
ADR-0536's Context section for why the original direction, killing
qwen3.5-9b to prove Tekos fails over, turned out to be unprovable through
real chat traffic). Tekos is the control, and what it controls changed on
2026-11-02 (zuno-demo WP-187, agents release v0.8.1): its chat-reachable task
`answer-technical-question` reads Confluence, so it is local only at every
level and must NEVER be served by an external provider. It used to be the
"decoupling control" that stayed on ovhcloud-gpt-oss-120b in all three phases;
that premise ended with tekos 0.4.3 (local first) and is now forbidden. The
control passes when the turn is answered by a local provider, or - only in the
failover phase - when it is refused cleanly (the ai-gateway answers 503 "no
eligible provider" while no local model is ready). It fails when any external
provider was reached, and it is reported "unknown" (not ok) when neither can
be established, so a broken probe never reads as a pass.

Runs as the in-cluster Job's entrypoint (ansible/tasks/
scenario_failover_probe_job.yml). WP-156: the agents are served by UnifAI
(ADR-0561), reached through its UI route like a browser; the Job stays
in-cluster because the fallback below reads Thanos Querier, which has no
external Route. Delegates the actual chat call to scenario_failover_probe.py
(invoked as a subprocess per agent, AGENT set in its environment - each
agent signs in to its own team workspace, so one process per agent keeps
the two transports apart).

Which provider served the turn: first the routing decision UnifAI carries on
the answer (`metadata.llm_response.routing`, fetched by its LLM element from
the ai-gateway, WP-148) - exact, per request, immune to concurrent traffic.
When the answer carries none (the lookup is best effort), fall back to the
before/after delta of `zuno_model_calls_total{agent, provider, outcome}`,
the only signal the retired agent stack ever offered. The `agent` label is set from
the X-Zuno-Agent header that unifai-operator puts on every bundle LLM, so
the counter still moves per agent. `source` in the output says which one
decided.

Why the fallback polls instead of an instant before/after diff: `zuno.model_calls`
(components/ai-gateway/app/telemetry.py) is pushed via OTel's
PeriodicExportingMetricReader (SDK default 60s export interval) to the
otel-collector, which prometheus-k8s then scrapes on its own 30s interval
(gitops/charts/observability/templates/servicemonitor-otel-collector.yaml).
A single request's effect on the counter can take up to ~90-100s to become
visible - an instant diff would false-negative on a perfectly healthy
fallback. POLL_TIMEOUT_SECONDS below is set generously past that worst case.

Usage (inside the Job container):
    UNIFAI_URL=https://unifai-ui-zuno-unifai.<base-domain> DEMO_PERSONA_PASSWORD=... \\
    PROM_URL=https://thanos-querier.openshift-monitoring.svc.cluster.local:9091 \\
    PROM_BEARER_TOKEN=... \\
    python3 evaluations/scenario_failover_verify.py --phase baseline

Prints one JSON object to stdout:
    {"phase": "baseline",
     "comage": {"provider": "local-wesh", "ok": true, "source": "routing-metadata"},
     "tekos": {"provider": "local-gpt-oss-maas", "ok": true, "outcome": "answered-local", "source": "routing-metadata"}}
`provider` is null if the answer carried no routing decision AND no
candidate's counter moved within the poll window - a real failure, not
swallowed silently. Tekos's entry also carries `outcome`: answered-local,
refused, external or unknown (see above).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

import httpx

PROM_URL = os.environ.get("PROM_URL", "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091")
PROM_BEARER_TOKEN = os.environ.get("PROM_BEARER_TOKEN", "")
POLL_TIMEOUT_SECONDS = 150
POLL_INTERVAL_SECONDS = 10

# One fixed persona/message per agent - each run creates its own UnifAI
# session (deleted by scenario_failover_probe.py itself). The persona must
# be a member of the agent's team workspace: sale-01 is in agent_comage,
# consultant-01 in agent_tekos (gitops/charts/keycloak/files/realm-zuno.json).
_AGENTS = [
    # check-deal-status is Comage's primary (only chat-reachable) task -
    # leads with local-wesh(-maas) then local-qwen35(-maas), non-reflexional.
    # This is the actual fallback under test.
    {"agent": "comage", "persona": "sale-01", "message": "Peux-tu me faire un point rapide sur nos opportunités en cours ?"},
    # answer-technical-question is Tekos's primary (only chat-reachable) task. It reads Confluence, so
    # since agents v0.8.1 (zuno-demo WP-187) it is local only at every level: the control checks that
    # it is answered locally or refused cleanly, never served by an external provider. The exact message
    # doesn't matter for the assertion; kept as a real, previously live-tested question from
    # evaluations/tekos/scenarios.yaml.
    {"agent": "tekos", "persona": "consultant-01", "message": "What GPU does the local model run on?", "control": "local-only"},
]


def _query_provider_counts(agent: str, successes_only: bool = True) -> dict:
    """Returns {provider: count} for zuno_model_calls_total{agent=...}. Comage's check keeps counting
    successful calls; the local-only control counts every attempt, because a call that fails at an
    external provider has still sent the context there."""
    outcome = ', outcome="success"' if successes_only else ""
    resp = httpx.get(
        f"{PROM_URL}/api/v1/query",
        params={"query": f'sum by (provider) (zuno_model_calls_total{{agent="{agent}"{outcome}}})'},
        headers={"Authorization": f"Bearer {PROM_BEARER_TOKEN}"},
        timeout=15,
        verify=False,  # thanos-querier's serving cert - same demo-scope shortcut as gitops/charts/grafana's datasource (tlsSkipVerify: true)
    )
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    return {row["metric"]["provider"]: float(row["value"][1]) for row in result}


# A freshly-rescheduled model's pod reaching Running/Ready (checked by the
# calling playbook before the restore-phase probe) only proves the container
# and its readiness probe are up - not that vLLM has finished loading model
# weights onto the MIG slice. Live-caught 2026-08-30: the restore probe's
# first real chat request after a reschedule hit a genuine HTTP-layer
# timeout at the old 30s default, well before the counter-polling phase even
# started. 90s comfortably covers a cold-loaded 9B model's first response
# without masking a truly broken fallback (POLL_TIMEOUT_SECONDS below still
# bounds the overall wait separately). WP-156: on UnifAI it is the stream's
# per-read timeout, and the stream sends heartbeats, so the subprocess
# timeout is what bounds the whole turn: it also covers the browser-style
# sign-in and a ReAct turn's tool calls, hence the larger margin.
_PROBE_HTTP_TIMEOUT_SECONDS = 90
_PROBE_SUBPROCESS_TIMEOUT_SECONDS = 150  # must stay above the probe's own timeout plus sign-in, tool calls and interpreter overhead


def _run_probe(agent: str, persona: str, message: str) -> dict:
    env = dict(os.environ, AGENT=agent, UNIFAI_TEAM_NAME=f"agent-{agent}")
    script = str(pathlib.Path(__file__).resolve().parent / "scenario_failover_probe.py")
    try:
        proc = subprocess.run(
            [
                sys.executable, script,
                "--persona", persona,
                "--message", message,
                "--timeout-seconds", str(_PROBE_HTTP_TIMEOUT_SECONDS),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=_PROBE_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return {"agent": agent, "persona": persona, "ok": False, "detail": f"probe subprocess exceeded {_PROBE_SUBPROCESS_TIMEOUT_SECONDS}s: stdout={exc.stdout!r} stderr={exc.stderr!r}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"agent": agent, "persona": persona, "ok": False, "detail": f"probe subprocess failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"}


# What the ai-gateway answers when a local-only task finds no ready local model
# (WP-188): HTTP 503 "no eligible provider is available for classification ...: <name>: not ready".
_REFUSAL_MARKERS = ("no eligible provider", "503", "service unavailable", "not ready")


def _is_local(provider: str) -> bool:
    return provider == "local" or provider.startswith("local-")


def _looks_like_refusal(detail) -> bool:
    text = str(detail or "").lower()
    return any(marker in text for marker in _REFUSAL_MARKERS)


def _moved_since(agent: str, before: dict, timeout_seconds: float) -> dict:
    """Providers whose attempt counter (any outcome) rose since `before`. Polls until one moves or the
    timeout ends: the counter reaches Prometheus up to ~100s late (see the module docstring)."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        after = _query_provider_counts(agent, successes_only=False)
        moved = {p: after.get(p, 0) - before.get(p, 0) for p in after}
        moved = {p: d for p, d in moved.items() if d > 0}
        if moved or time.monotonic() >= deadline:
            return moved
        time.sleep(POLL_INTERVAL_SECONDS)


def _control_verdict(providers: set, source: str, detail: str) -> dict:
    external = sorted(p for p in providers if not _is_local(p))
    if external:
        return {"provider": external[0], "ok": False, "outcome": "external", "source": source,
                "detail": f"an external provider was reached by a local-only task: {external}; {detail}"}
    return {"provider": sorted(providers)[0], "ok": True, "outcome": "answered-local", "source": source, "detail": detail}


def verify_local_only_control(agent: str, persona: str, message: str, phase: str) -> dict:
    """Tekos's local-only control. Passes (ok) when the turn was answered by a local provider or refused
    cleanly with no external attempt; fails when any external provider was reached or the outcome cannot
    be established."""
    before = _query_provider_counts_or_none(agent, successes_only=False)
    probe_result = _run_probe(agent, persona, message)
    unknown = {"provider": None, "ok": False, "outcome": "unknown", "source": None}

    if probe_result.get("ok"):
        provider = (probe_result.get("routing") or {}).get("provider")
        if provider:
            return _control_verdict({provider}, "routing-metadata", f"phase={phase} session={probe_result.get('session_id')}")
        if before is None:
            return dict(unknown, detail="the answer carried no routing decision and Prometheus could not be read")
        moved = _moved_since(agent, before, POLL_TIMEOUT_SECONDS)
        if not moved:
            return dict(unknown, detail=f"no routing decision on the answer and no provider counter moved within {POLL_TIMEOUT_SECONDS}s")
        return _control_verdict(set(moved), "prometheus", f"phase={phase} moved={moved}")

    if not _looks_like_refusal(probe_result.get("detail")):
        return dict(unknown, detail=f"the turn failed without the ai-gateway's refusal: {probe_result.get('detail')}")
    if before is None:
        return dict(unknown, detail="the turn was refused but Prometheus could not be read, so a missing external attempt is unproved")
    moved = _moved_since(agent, before, POLL_TIMEOUT_SECONDS)
    external = sorted(p for p in moved if not _is_local(p))
    if external:
        return {"provider": external[0], "ok": False, "outcome": "external", "source": "prometheus",
                "detail": f"the turn was refused yet an external provider was attempted: {external}"}
    return {"provider": None, "ok": True, "outcome": "refused", "source": "prometheus",
            "detail": f"phase={phase} refused cleanly, no external attempt in {POLL_TIMEOUT_SECONDS}s: {probe_result.get('detail')}"}


def _query_provider_counts_or_none(agent: str, successes_only: bool = True):
    """Counter snapshot, or None when Prometheus cannot be read: the
    routing-metadata path must not fail because the fallback is unavailable."""
    try:
        return _query_provider_counts(agent, successes_only)
    except Exception:  # noqa: BLE001 - reported through the fallback's own detail
        return None


def verify_one_agent(agent: str, persona: str, message: str, phase: str) -> dict:
    before = _query_provider_counts_or_none(agent)
    probe_result = _run_probe(agent, persona, message)
    if not probe_result.get("ok"):
        return {"provider": None, "ok": False, "source": None, "detail": probe_result.get("detail")}

    routing = probe_result.get("routing") or {}
    if routing.get("provider"):
        return {
            "provider": routing["provider"],
            "ok": True,
            "source": "routing-metadata",
            "detail": f"phase={phase} routing={json.dumps(routing, sort_keys=True)} session={probe_result.get('session_id')}",
        }

    if before is None:
        return {
            "provider": None, "ok": False, "source": None,
            "detail": "the answer carried no routing decision and Prometheus could not be read for the fallback",
        }
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        after = _query_provider_counts(agent)
        moved = {p: after.get(p, 0) - before.get(p, 0) for p in after}
        moved = {p: d for p, d in moved.items() if d > 0}
        if moved:
            # If more than one candidate somehow moved in the same window,
            # report the one with the largest delta - ambiguous only under
            # concurrent unrelated traffic, which this drill does not expect.
            provider = max(moved, key=moved.get)
            return {"provider": provider, "ok": True, "source": "prometheus", "detail": f"counts_before={before} counts_after={after}"}
        time.sleep(POLL_INTERVAL_SECONDS)

    return {
        "provider": None, "ok": False, "source": None,
        "detail": f"no routing decision on the answer and no provider counter moved within {POLL_TIMEOUT_SECONDS}s (before={before})",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, help="baseline|failover|restore - used only for the output label")
    args = parser.parse_args()

    result = {"phase": args.phase}
    for spec in _AGENTS:
        verify = verify_local_only_control if spec.get("control") == "local-only" else verify_one_agent
        result[spec["agent"]] = verify(spec["agent"], spec["persona"], spec["message"], args.phase)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
