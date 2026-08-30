#!/usr/bin/env python3
"""Orchestrator for WP-105/ADR-0536's node failover drill: fires one live
chat turn each at Comage and Tekos and determines, from Prometheus, which
`ai-gateway` provider actually served each one.

Runs as the in-cluster Job's entrypoint (agent-runtime/ai-gateway have no
external Route - see ansible/roles/agents/tasks/run_acceptance_gate.yml's own
header comment for why every live chat probe in this repo already runs
in-cluster, never from the operator's shell). Delegates the actual chat call
to scenario_failover_probe.py (invoked as a subprocess per agent, AGENT set
in its environment - same cross-agent reuse trick
evaluations/comage/stress_test.py already uses for run_scenarios.py).

Why poll instead of an instant before/after diff: `zuno.model_calls`
(components/ai-gateway/app/telemetry.py) is pushed via OTel's
PeriodicExportingMetricReader (SDK default 60s export interval) to the
otel-collector, which prometheus-k8s then scrapes on its own 30s interval
(gitops/charts/observability/templates/servicemonitor-otel-collector.yaml).
A single request's effect on the counter can take up to ~90-100s to become
visible - an instant diff would false-negative on a perfectly healthy
fallback. POLL_TIMEOUT_SECONDS below is set generously past that worst case.

Usage (inside the Job container):
    PROM_URL=https://thanos-querier.openshift-monitoring.svc.cluster.local:9091 \\
    PROM_BEARER_TOKEN=... \\
    python3 evaluations/scenario_failover_verify.py --phase baseline

Prints one JSON object to stdout:
    {"phase": "baseline", "comage": {"provider": "local-wesh", "ok": true},
     "tekos": {"provider": "local-qwen35", "ok": true}}
`provider` is null if no candidate's counter moved within the poll window -
a real failure, not swallowed silently.
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

# One fixed persona/message per agent - session_id is unique per drill phase
# so each run creates its own conversation (cleaned up by
# scenario_failover_probe.py's own call to cleanup_created_runs()).
_AGENTS = [
    {"agent": "comage", "persona": "sale-01", "message": "Peux-tu me faire un point rapide sur nos opportunités en cours ?"},
    # Deliberately a plain retrieval-style question, NOT an open-ended
    # "explain the architecture" one - live-caught 2026-08-30: the latter
    # got classified as a reflexional/reasoning task and routed to
    # ovhcloud-gpt-oss-120b (ADR-0412/ADR-0416, extended to Tekos by
    # WP-096/ADR-0531) instead of Tekos's normal local-qwen35 chain,
    # producing a false-negative baseline failure. Reused verbatim from
    # evaluations/tekos/scenarios.yaml's own known-good, non-reflexional
    # scenario set.
    {"agent": "tekos", "persona": "consultant-01", "message": "What GPU does the local model run on?"},
]


def _query_provider_counts(agent: str) -> dict:
    """Returns {provider: count} for zuno_model_calls_total{agent=..., outcome="success"}."""
    resp = httpx.get(
        f"{PROM_URL}/api/v1/query",
        params={"query": f'sum by (provider) (zuno_model_calls_total{{agent="{agent}", outcome="success"}})'},
        headers={"Authorization": f"Bearer {PROM_BEARER_TOKEN}"},
        timeout=15,
        verify=False,  # thanos-querier's serving cert - same demo-scope shortcut as gitops/charts/grafana's datasource (tlsSkipVerify: true)
    )
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    return {row["metric"]["provider"]: float(row["value"][1]) for row in result}


def _run_probe(agent: str, persona: str, message: str, session_id: str) -> dict:
    env = dict(os.environ, AGENT=agent)
    script = str(pathlib.Path(__file__).resolve().parent / "scenario_failover_probe.py")
    proc = subprocess.run(
        [sys.executable, script, "--persona", persona, "--message", message, "--session-id", session_id],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"agent": agent, "persona": persona, "ok": False, "detail": f"probe subprocess failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"}


def verify_one_agent(agent: str, persona: str, message: str, phase: str) -> dict:
    before = _query_provider_counts(agent)
    probe_result = _run_probe(agent, persona, message, session_id=f"wp-105-{phase}-{agent}")
    if not probe_result.get("ok"):
        return {"provider": None, "ok": False, "detail": probe_result.get("detail")}

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
            return {"provider": provider, "ok": True, "detail": f"counts_before={before} counts_after={after}"}
        time.sleep(POLL_INTERVAL_SECONDS)

    return {"provider": None, "ok": False, "detail": f"no provider counter moved within {POLL_TIMEOUT_SECONDS}s (before={before})"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, help="baseline|failover|restore - used only for the session_id/output label")
    args = parser.parse_args()

    result = {"phase": args.phase}
    for spec in _AGENTS:
        result[spec["agent"]] = verify_one_agent(spec["agent"], spec["persona"], spec["message"], args.phase)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
