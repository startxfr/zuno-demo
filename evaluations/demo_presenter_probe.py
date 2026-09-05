#!/usr/bin/env python3
"""WP-136/ADR-0550: verify the webinar presenter persona can authenticate,
can see the three named demo projects, and that the three local models
answer - as `make demo-check`'s "Zuno application"/"Projects"/"Models"
sections require.

Reuses evaluations/tekos/run_scenarios.py's Keycloak auth helper rather
than reimplementing a token exchange - same cross-agent trick
evaluations/scenario_failover_probe.py already uses: AGENT must be set in
the environment BEFORE this module is imported, since run_scenarios.py
resolves AGENT/RUNTIME_URL/the frontend client secret at import time.
GET /v1/projects (components/agent-runtime/app/main.py) is deliberately
agent-agnostic (ADR-0527 clause 6 - a project is cross-agent), so any one
agent's persona token is sufficient to prove the check; AGENT defaults to
comage to match this repo's existing demo-persona ("sale-01") fixture.

The three local models are probed from THIS SAME in-cluster Job rather
than from the Ansible control node - live-caught 2026-09-05 running
`make demo-check` from a plain workstation: the control node has no route
to `*.svc.cluster.local` DNS names at all (`urlopen error [Errno -2] Nom
ou service inconnu`), while this Job's pod (same acceptance-gate identity
already proven able to reach agent-runtime for the projects check above)
does.

`--ensure-projects` (used by `make demo-reset`, never by the read-only
`make demo-check`) creates any missing demo project via this same
POST /v1/projects endpoint the frontend's own "New project" dialog calls -
not a second creation mechanism. Each created project grants `admin` to
BOTH the `consultant` and `sales` business-role groups: `sale-01` (this
script's own persona, `/sales`) and `consultant-01` (the persona
evaluations/arkos and evaluations/tekos both use, `/consultant`) are in
disjoint Keycloak groups with no shared one, confirmed against
gitops/charts/keycloak/files/realm-zuno.json - a project granted only to
its creator's own subject would be invisible to Arkos/Tekos's demo steps.
A project that already exists with the wrong classification is reported,
never auto-corrected - only genuinely missing projects are created.

Usage:
    AGENT=comage python3 evaluations/demo_presenter_probe.py --persona sale-01 [--ensure-projects]

Prints one JSON object to stdout:
{"auth": {"auth_ok", "persona", "projects": [{"title", "classification"}, ...],
          "missing": [...], "created": [...], "detail"},
 "models": [{"model", "ok", "detail"}, ...]}
Exit code 0 regardless of whether any individual probe succeeded - every
failure is reported IN the JSON body, so the calling playbook can add each
as its own row to the demo-check report rather than aborting early.
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
# exist - created via --ensure-projects (`make demo-reset`) or live through
# the frontend if the presenter wants the audience to see it happen.
REQUIRED_PROJECTS = {
    "webinar-public": "C1",
    "webinar-confidential": "C2",
    "webinar-restricted": "C3",
}

# Both business-role groups get `admin` on every created demo project - see
# this module's own docstring for why a single creator-only grant is not
# enough (sale-01/consultant-01 are in disjoint Keycloak groups).
_DEMO_PROJECT_GRANT_GROUPS = ["consultant", "sales"]

# ADR-0521-style workload Service naming (<name>-kserve-workload-svc), same
# three local models WP-136's demo-check section lists.
LOCAL_MODELS = [
    {"model": "gpt-oss-20b", "service": "gpt-oss-20b-kserve-workload-svc"},
    {"model": "qwen3.5-9b", "service": "qwen35-9b-kserve-workload-svc"},
    {"model": "qwen3.5-9b-wesh", "service": "qwen35-9b-wesh-kserve-workload-svc"},
]


def _list_projects(persona: str, timeout_seconds: float):
    """Returns (projects, error_detail). error_detail is None on success."""
    try:
        resp = httpx.get(f"{RUNTIME_URL}/v1/projects", headers=auth_headers(persona), timeout=timeout_seconds)
    except Exception as exc:
        return None, str(exc)
    if resp.status_code != 200:
        return None, f"status={resp.status_code} body={resp.text[:500]}"
    return [{"title": p["title"], "classification": p["classification"]} for p in resp.json()], None


def probe_auth_and_projects(persona: str, timeout_seconds: float = 30, ensure_projects: bool = False) -> dict:
    """auth_ok reflects whether the HTTP call itself succeeded (the persona
    really authenticated and agent-runtime really answered) - independent
    of whether the required demo projects happen to exist yet. Conflating
    the two into one flag was a real bug (live-caught 2026-09-05): a
    persona that authenticates fine against a cluster with none of the
    three demo projects created yet showed as "persona-auth: FAIL", which
    reads as an auth problem when it is actually a project-provisioning
    step the operator has not done yet (see the separate `missing` field).
    """
    projects, error = _list_projects(persona, timeout_seconds)
    if error is not None:
        return {"auth_ok": False, "persona": persona, "projects": [], "missing": list(REQUIRED_PROJECTS), "created": [], "detail": error}

    seen = {p["title"]: p["classification"] for p in projects}
    missing = [name for name in REQUIRED_PROJECTS if name not in seen]
    mismatched = [
        name for name, want in REQUIRED_PROJECTS.items() if name in seen and seen[name] != want
    ]

    created, create_failures = [], []
    if ensure_projects and missing:
        for name in missing:
            try:
                resp = httpx.post(
                    f"{RUNTIME_URL}/v1/projects",
                    headers=auth_headers(persona),
                    json={
                        "title": name,
                        "classification": REQUIRED_PROJECTS[name],
                        "grants": [{"group_name": g, "role": "admin"} for g in _DEMO_PROJECT_GRANT_GROUPS],
                    },
                    timeout=timeout_seconds,
                )
                if resp.status_code == 200:
                    created.append(name)
                else:
                    create_failures.append(f"{name} (status={resp.status_code} body={resp.text[:200]})")
            except Exception as exc:
                create_failures.append(f"{name} ({exc})")

        # Re-list rather than assume: a failed create must not be reported
        # as present, and this also picks up the actual stored classification.
        refreshed, refresh_error = _list_projects(persona, timeout_seconds)
        if refresh_error is None:
            projects = refreshed
            seen = {p["title"]: p["classification"] for p in projects}
            missing = [name for name in REQUIRED_PROJECTS if name not in seen]
            mismatched = [
                name for name, want in REQUIRED_PROJECTS.items() if name in seen and seen[name] != want
            ]

    ok = not missing and not mismatched
    detail = "authenticated; all three demo projects present with the expected classification" if ok else (
        f"authenticated; missing={missing} mismatched_classification={mismatched}"
        + (f" created={created}" if created else "")
        + (f" create_failures={create_failures}" if create_failures else "")
    )
    return {"auth_ok": True, "persona": persona, "projects": projects, "missing": missing, "created": created, "detail": detail}


def probe_models(timeout_seconds: float = 10) -> list:
    results = []
    for entry in LOCAL_MODELS:
        url = f"https://{entry['service']}.zuno-ai-run.svc.cluster.local:8000/v1/models"
        try:
            resp = httpx.get(url, timeout=timeout_seconds, verify=False)
            ok = resp.status_code == 200
            detail = "reachable" if ok else f"status={resp.status_code}"
        except Exception as exc:
            ok, detail = False, str(exc)
        results.append({"model": entry["model"], "ok": ok, "detail": detail})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--ensure-projects", action="store_true", default=False)
    args = parser.parse_args()
    print(json.dumps({
        "auth": probe_auth_and_projects(args.persona, args.timeout_seconds, ensure_projects=args.ensure_projects),
        "models": probe_models(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
