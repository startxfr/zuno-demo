#!/usr/bin/env python3
"""Single-agent, single-turn live chat probe for WP-105/ADR-0536's node
failover drill (`make d3 scenario-failover-node`).

This deliberately does NOT try to determine which model provider answered -
`zuno_provider` (components/ai-gateway/app/schemas.py) never reaches
agent-runtime, so that judgment is made by the calling Ansible playbook from
the before/after delta of the `zuno_model_calls_total{agent, provider,
outcome}` Prometheus counter, queried separately via `oc exec` into the
ai-gateway pod (Thanos Querier is cluster-internal only). This script's only
job is to actually fire one real chat turn through the real path so that
counter has something to move, and report whether the HTTP call itself
succeeded.

Reuses evaluations/tekos/run_scenarios.py's auth/cleanup helpers rather than
reimplementing them - same cross-agent trick evaluations/comage/stress_test.py
already uses: AGENT must be set in the environment BEFORE this module is
imported, since run_scenarios.py resolves AGENT/RUNTIME_URL/the frontend
client secret at import time.

Usage:
    AGENT=tekos python3 evaluations/scenario_failover_probe.py \\
        --persona consultant-01 --message "..."
    AGENT=comage python3 evaluations/scenario_failover_probe.py \\
        --persona sale-01 --message "..."

Prints one JSON object to stdout: {"agent", "persona", "ok", "run_id", "detail"}.
Exit code 0 whether or not the chat call itself succeeded - failure is
reported IN the JSON body, not via process exit, because the caller (the
inject playbook) needs to keep going and interpret a failed baseline call as
a precondition problem, not crash the whole drill.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

# AGENT must already be set by the caller's environment - see module
# docstring. Default matches run_scenarios.py's own default so a bare
# invocation without AGENT= still does something sane for manual testing.
os.environ.setdefault("AGENT", "tekos")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tekos"))
import httpx  # noqa: E402
from run_scenarios import AGENT, RUNTIME_URL, auth_headers, cleanup_created_runs, record_run_id  # noqa: E402


def probe(persona: str, message: str, session_id: str, timeout_seconds: float = 30) -> dict:
    try:
        resp = httpx.post(
            f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
            headers=auth_headers(persona),
            json={"session_id": session_id, "user_sub": persona, "message": message},
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return {"agent": AGENT, "persona": persona, "ok": False, "run_id": None, "detail": str(exc)}

    if resp.status_code != 200:
        return {
            "agent": AGENT,
            "persona": persona,
            "ok": False,
            "run_id": None,
            "detail": f"status={resp.status_code} body={resp.text[:500]}",
        }

    body = resp.json()
    record_run_id(persona, body)
    return {"agent": AGENT, "persona": persona, "ok": True, "run_id": body.get("run_id"), "detail": "chat call succeeded"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--session-id", default="wp-105-scenario-failover-node")
    parser.add_argument("--timeout-seconds", type=float, default=30)
    args = parser.parse_args()

    result = probe(args.persona, args.message, args.session_id, args.timeout_seconds)
    # Best-effort cleanup of the conversation this probe just created, same
    # posture as every other evaluations/*/*.py script - a demo persona's
    # real conversation list must not accumulate synthetic drill turns.
    cleanup_created_runs()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
