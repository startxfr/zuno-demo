"""The Limitador counters sampler of the stress runner (WP-312, ADR-0624, WP-313 step 4).

  limitador-counters   a SAMPLER: reads the counters of every Limitador namespace at the start of the run, every minute
                       and at the end, then reports which counters moved and under which identity. It is the proof that
                       a stress run spends the stress ServiceAccount's budget and not the ai-gateway's (WP-306):
                       `system:serviceaccount:zuno-ai-run:ai-gateway-stress` moves, `...:ai-gateway` does not move
                       because of this run (it moves with every other caller's traffic: the row says so).

It reuses the reader of platform/testing/quota_counters_probe.py (WP-177): `GET /counters/<url-encoded namespace>` on the
Limitador Service, one namespace at a time. The namespaces are discovered from the `limitador_namespace` labels of
Limitador's own /metrics, so no route is hard-coded. In-cluster URL: LIMITADOR_URL, default
http://limitador-limitador.kuadrant-system.svc:8080. kuadrant-system has no NetworkPolicy of this repository, but an
installation may add one: when the sampler cannot connect it says so in one row, and the same read works from a workstation
with LIMITADOR_URL pointing at a port-forward (`oc -n kuadrant-system port-forward svc/limitador-limitador 8080`).

Caveat measured live on 2026-11-19: the Kuadrant wasm shim never creates a counter for the LAST token limit of a route, ordered
by limit name (memory kuadrant-shim-drops-trailing-limit-actions): a limit with no counter is a limit that is not enforced,
and this sampler reports "no counter" for it rather than zero.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import sys

_PLATFORM_TESTING = pathlib.Path(__file__).resolve().parents[2] / "platform" / "testing"
sys.path.insert(0, str(_PLATFORM_TESTING))

import quota_counters_probe as probe  # noqa: E402
import stress_runner as sr  # noqa: E402
from stress_runner import register, row  # noqa: E402

LIMITADOR_DEFAULT = "http://limitador-limitador.kuadrant-system.svc:8080"
NAMESPACE_RE = re.compile(r'limitador_namespace="([^"]+)"')
SERVICE_ACCOUNT_RE = re.compile(r"system:serviceaccount:[A-Za-z0-9_.:-]+")
STRESS_SA = "system:serviceaccount:zuno-ai-run:ai-gateway-stress"
SHARED_SA = "system:serviceaccount:zuno-ai-run:ai-gateway"


def namespaces_of(metrics_text: str) -> list:
    """The Limitador namespaces named by the labels of its /metrics, sorted, each once."""
    return sorted(set(NAMESPACE_RE.findall(metrics_text)))


def identity_of(counter: dict) -> str:
    """The identity a counter belongs to: the ServiceAccount named by its variables, else the first variable value, else ''."""
    values = [str(v) for v in (counter.get("set_variables") or {}).values()]
    for value in values:
        match = SERVICE_ACCOUNT_RE.search(value)
        if match:
            return match.group(0)
    return values[0] if values else ""


def read_all(url: str) -> dict:
    """{namespace: [counters]} for every namespace Limitador reports. Blocking."""
    import httpx

    base = url.rstrip("/")
    with httpx.Client(timeout=20) as client:
        metrics = client.get(f"{base}/metrics")
        metrics.raise_for_status()
        return {ns: probe.read_counters(client, base, ns) for ns in namespaces_of(metrics.text)}


def moved_by_identity(first: dict, last: dict) -> dict:
    """{identity: {"tokens": n, "limits": [names]}} consumed between two reads, over every namespace."""
    out = {}
    for ns, counters in last.items():
        before = probe.consumed(first.get(ns, []))
        for counter in counters:
            key = probe._key(counter)
            delta = (int(counter["limit"]["max_value"]) - int(counter["remaining"])) - before.get(key, 0)
            if delta > 0:
                entry = out.setdefault(identity_of(counter) or "(no identity)", {"tokens": 0, "limits": set()})
                entry["tokens"] += delta
                entry["limits"].add(f"{ns}:{key[0]}")
    return {identity: {"tokens": e["tokens"], "limits": sorted(e["limits"])} for identity, e in out.items()}


SHARED_WARN_FRACTION = 0.10  # the isolation row warns when the shared ServiceAccount moved more than this share of a window budget


def spent_fraction(counters_by_namespace: dict, identity: str = SHARED_SA):
    """The largest share of its limit that a counter of `identity` has spent right now (0..1), None without such a counter."""
    best = None
    for counters in counters_by_namespace.values():
        for counter in counters:
            if identity_of(counter) != identity:
                continue
            limit = int(counter["limit"]["max_value"])
            if limit > 0:
                share = (limit - int(counter["remaining"])) / limit
                best = share if best is None else max(best, share)
    return best


def moved_fraction(first: dict, last: dict, identity: str = SHARED_SA):
    """The largest share of its limit that a counter of `identity` moved between two reads (0..1), None without such a counter."""
    best = None
    for ns, counters in last.items():
        before = probe.consumed(first.get(ns, []))
        for counter in counters:
            if identity_of(counter) != identity:
                continue
            limit = int(counter["limit"]["max_value"])
            if limit > 0:
                delta = (limit - int(counter["remaining"])) - before.get(probe._key(counter), 0)
                share = max(delta, 0) / limit
                best = share if best is None else max(best, share)
    return best


def shared_budget_probe(ctx):
    """Blocking probe of the runner's shared-budget guard: how much of the shared ai-gateway ServiceAccount's budget is spent."""
    return spent_fraction(read_all(ctx.env.get("LIMITADOR_URL") or LIMITADOR_DEFAULT))


if shared_budget_probe not in sr.SHARED_BUDGET_PROBES:
    sr.SHARED_BUDGET_PROBES.append(shared_budget_probe)


def finish_counters(ctx, samples):
    errors = [s for s in samples if isinstance(s, Exception)]
    taken = [s for s in samples if isinstance(s, dict)]
    if len(taken) < 2:
        why = str(errors[0])[:200] if errors else "fewer than two reads"
        return [row("limitador-counters", "counters", "sampler", "counters", False,
                    f"{why} (set LIMITADOR_URL, or run the same read from a workstation through a port-forward)")]
    first, last = taken[0], taken[-1]
    if not any(last.values()):
        return [row("limitador-counters", "counters", "no-counter", "counters", False,
                    f"Limitador returned no counter in {len(last)} namespace(s): its limits are not enforced. Known cause on demo333 "
                    "(zuno-demo-cluster, 2026-11-19): the Kuadrant EnvoyFilter openshift-ingress/kuadrant-maas-default-gateway "
                    "is stale (since 2026-11-05) and lacks the load and praxis limit actions, so the -load limits never count: "
                    "re-create it from the current policies (an operational step, the owner's go). The wasm shim also creates no "
                    "counter for the last token limit of a route, ordered by limit name")]
    moved = moved_by_identity(first, last)
    rows = []
    for identity, entry in sorted(moved.items(), key=lambda kv: -kv[1]["tokens"]):
        rows.append(row("limitador-counters", "counters", identity, "counters", True,
                        f"moved +{entry['tokens']} tokens on {len(entry['limits'])} limit(s): {', '.join(entry['limits'][:4])}"
                        + (" ..." if len(entry["limits"]) > 4 else "")))
    stress = moved.get(STRESS_SA, {}).get("tokens", 0)
    shared = moved.get(SHARED_SA, {}).get("tokens", 0)
    share = moved_fraction(first, last) or 0.0
    warn = share > SHARED_WARN_FRACTION
    rows.append(row("limitador-counters", "counters", "isolation", "counters", not warn,
                    ("WARNING the shared ai-gateway ServiceAccount moved " + f"{share:.0%} of its window budget during this run "
                     f"(the warning starts at {SHARED_WARN_FRACTION:.0%}): the drivers and Jobs that ride it spend what Open WebUI, Dify, kagent "
                     "and OpenClaw share. " if warn else "")
                    + f"stress ServiceAccount +{stress} tokens, shared ai-gateway ServiceAccount +{shared} tokens "
                    "(the shared one also carries every other caller's traffic during the run)"
                    + ("" if stress else "; the stress counter did not move: no stress call reached MaaS, or its limit has no counter")))
    if errors:
        rows.append(row("limitador-counters", "counters", "sampler", "counters", False, f"{len(errors)} read(s) failed: {str(errors[0])[:160]}"))
    return rows


@register("limitador-counters", family="counters", sampler=True, interval=60, finish=finish_counters,
          description="a sampler: which Limitador counters moved during the run, per identity (the isolation proof of WP-306)",
          needs=("Limitador's HTTP API reachable from the Job (LIMITADOR_URL)",))
async def limitador_counters(ctx, i):
    url = ctx.env.get("LIMITADOR_URL") or LIMITADOR_DEFAULT
    return await asyncio.to_thread(read_all, url)
