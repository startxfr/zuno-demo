#!/usr/bin/env python3
"""WP-136/ADR-0550: verify the webinar presenter persona can authenticate
and see the three named demo projects, as `make demo-check` prompter's
"Zuno application" and "Projects" sections require.

Reuses evaluations/tekos/run_scenarios.py's Keycloak auth helper rather
than reimplementing a token exchange - same cross-agent trick
evaluations/scenario_failover_probe.py already uses: AGENT must be set in
the environment BEFORE this module is imported, since run_scenarios.py
resolves AGENT/RUNTIME_URL/the frontend client secret at import time.
GET /v1/projects (components/agent-runtime/app/main.py) is deliberately
agent-agnostic (ADR-0527 clause 6 - a project is cross-agent), so any one
agent's persona token is sufficient to prove the check; AGENT defaults to
comage to match this repo's existing demo-persona ("sale-01") fixture.

Usage:
    AGENT=comage python3 evaluations/demo_presenter_probe.py --persona sale-01

Prints one JSON object to stdout:
{"ok", "persona", "projects": [{"title", "classification"}, ...],
 "missing": [...], "detail"}
Exit code 0 whether or not the probe itself succeeded - failure is
reported IN the JSON body, so the calling playbook can add it as one more
row to the demo-check report rather than aborting the whole check early.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

os.environ.setdefault("AGENT", "comage")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tekos"))
import httpx  # noqa: E402
from run_scenarios import RUNTIME_URL, auth_headers  # noqa: E402

# ADR-0550/WP-136: the three demo projects `make demo-check` expects to
# already exist (created live through the frontend, per the WP's explicit
# "do not add a second project mechanism" instruction).
REQUIRED_PROJECTS = {
    "webinar-public": "C1",
    "webinar-confidential": "C2",
    "webinar-restricted": "C3",
}


def probe(persona: str, timeout_seconds: float = 30) -> dict:
    try:
        resp = httpx.get(f"{RUNTIME_URL}/v1/projects", headers=auth_headers(persona), timeout=timeout_seconds)
    except Exception as exc:
        return {"ok": False, "persona": persona, "projects": [], "missing": list(REQUIRED_PROJECTS), "detail": str(exc)}

    if resp.status_code != 200:
        return {
            "ok": False,
            "persona": persona,
            "projects": [],
            "missing": list(REQUIRED_PROJECTS),
            "detail": f"status={resp.status_code} body={resp.text[:500]}",
        }

    projects = [{"title": p["title"], "classification": p["classification"]} for p in resp.json()]
    seen = {p["title"]: p["classification"] for p in projects}
    missing = [name for name in REQUIRED_PROJECTS if name not in seen]
    mismatched = [
        name for name, want in REQUIRED_PROJECTS.items() if name in seen and seen[name] != want
    ]
    ok = not missing and not mismatched
    detail = "all three demo projects present with the expected classification" if ok else (
        f"missing={missing} mismatched_classification={mismatched}"
    )
    return {"ok": ok, "persona": persona, "projects": projects, "missing": missing, "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    args = parser.parse_args()
    print(json.dumps(probe(args.persona, args.timeout_seconds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
