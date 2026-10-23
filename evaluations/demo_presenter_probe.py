#!/usr/bin/env python3
"""WP-136/ADR-0550: verify the webinar presenter persona can authenticate
and can see the three named demo projects, as `make demo check`'s "Zuno
application"/"Projects" sections require.

WP-156: ported from the retired legacy agent stack to UnifAI, which serves
the agents (ADR-0561). The persona signs in through the UnifAI UI route
exactly as a browser does (evaluations/common/unifai_target.py: identity
service -> Keycloak form -> session cookie), so this needs
DEMO_PERSONA_PASSWORD and UNIFAI_URL only - no OIDC client secret, no
in-cluster agent URL. UnifAI's internal APIs only admit UnifAI pods
(NetworkPolicy unifai-internal-apis), so the UI route is the only way in.

"Authenticated" now means: the sign-in succeeded AND the agent's workflow
(AGENT, default comage, matching this repo's "sale-01" demo-persona
fixture) is visible to the persona in the agent's team workspace
(`agent-<agent>`, the group-bound team unifai-operator emits from the
bundle's access groups). A presenter who can sign in but not open the
agent cannot run the demo, so both are one row; `detail` says which part
failed.

Projects: ADR-0569 clause 1 maps a Zuno project (ADR-0527) to a UnifAI team
workspace, so a demo project is a team named `webinar-*` the persona is a
member of. A UnifAI team carries NO classification: the session-level
"raise to the project's level" of ADR-0565 clause 3 is not implemented, so
the C1/C2/C3 of each demo project cannot be checked here. It is reported as
`null` in `projects[].classification` and named in `detail`, never
silently passed as matching.

Does NOT probe the three local models - live-caught 2026-09-05 running
`make demo check` from a plain workstation (DNS to `*.svc.cluster.local`
unresolvable there) and then from the in-cluster Job (DNS resolves,
but the connection is reset: gitops/charts/models's own NetworkPolicies
(networkpolicy-gptoss.yaml/networkpolicy-qwen35.yaml) allow ingress on
port 8000 only from ai-gateway/the MaaS gateway/lightspeed/
monitoring/lm-eval - never from this acceptance-gate-labeled pod, and
widening that allow-list for a presenter preflight tool is a real
security-boundary change, not this WP's call to make unilaterally).
ansible/playbooks/demo_check.yml instead reads each model's
LLMInferenceService `Ready` condition directly from the Kubernetes API
(same mechanism ansible/roles/argocd/tasks/apply_resource_health_checks.yml
already trusts) - a control-plane read, never subject to a workload
NetworkPolicy.

`--ensure-projects` (used by `make demo reset`, never by the read-only
`make demo check`) creates any missing demo project as a UnifAI team
workspace (identity service `team.create`, the same call the UI's "New
team" dialog makes - not a second creation mechanism). Each created team's
members are BOTH the `consultant` and `sales` business-role groups, plus its
creator: `sale-01` (this script's own persona, `/sales`) and
`consultant-01` (the persona evaluations/arkos and evaluations/tekos both
use, `/consultant`) are in disjoint Keycloak groups with no shared one,
confirmed against gitops/charts/keycloak/files/realm-zuno.json - a team
granted only to its creator would be invisible to Arkos/Tekos's demo steps.
ADR-0527's per-group `admin` grant has no team-role equivalent yet
(ADR-0569, "grant model, unverified"): membership is all a team expresses.
A team name is unique across UnifAI: if a `webinar-*` team exists but this
persona is not a member, the create fails and is reported, never retried
under another name.

Usage:
    UNIFAI_URL=https://unifai-ui-zuno-unifai.<base-domain> DEMO_PERSONA_PASSWORD=... \\
        python3 evaluations/demo_presenter_probe.py --persona sale-01 [--ensure-projects]

Prints one JSON object to stdout:
{"auth_ok", "persona", "projects": [{"title", "classification"}, ...],
 "missing": [...], "created": [...], "detail"}
Exit code 0 regardless of whether the probe itself succeeded - failure is
reported IN the JSON body, so the calling playbook can add it as one more
row to the demo-check report rather than aborting the whole check early.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

AGENT = os.getenv("AGENT", "comage")

# In the repo this file sits in evaluations/, the transport in
# evaluations/common/; the probe Job mounts both flat under /gate. Both
# layouts are covered by these two sys.path entries.
_here = pathlib.Path(__file__).parent.resolve()
for _candidate in (_here / "common", _here):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
from unifai_target import UnifaiTarget  # noqa: E402

# ADR-0550/WP-136: the three demo projects `make demo check` expects to
# exist - created via --ensure-projects (`make demo reset`) or live through
# the UnifAI UI if the presenter wants the audience to see it happen. The
# classification is the intended one; UnifAI cannot store it (see the
# module docstring).
REQUIRED_PROJECTS = {
    "webinar-public": "C1",
    "webinar-confidential": "C2",
    "webinar-restricted": "C3",
}

# Both business-role groups are members of every created demo team - see
# this module's own docstring for why a creator-only team is not enough
# (sale-01/consultant-01 are in disjoint Keycloak groups).
_DEMO_PROJECT_GROUPS = ["consultant", "sales"]

_NO_CLASSIFICATION = "classification not checked: UnifAI team workspaces carry none (ADR-0565 clause 3 open)"


def _team_projects(target: UnifaiTarget, persona: str):
    """The demo-project teams `persona` is a member of, in the probe's output shape."""
    names = {t.get("name") for t in target.teams(persona)}
    return [{"title": n, "classification": None} for n in REQUIRED_PROJECTS if n in names]


def probe_auth_and_projects(persona: str, ensure_projects: bool = False, target: UnifaiTarget = None) -> dict:
    """auth_ok reflects whether the persona really signed in and can open
    AGENT's workflow - independent of whether the demo projects exist yet.
    Conflating the two into one flag was a real bug (live-caught
    2026-09-05): a persona that authenticates fine against a cluster with
    none of the three demo projects created yet showed as
    "persona-auth: FAIL", which reads as an auth problem when it is
    actually a project-provisioning step the operator has not done yet
    (see the separate `missing` field).
    """
    missing_all = list(REQUIRED_PROJECTS)
    try:
        if target is None:
            target = UnifaiTarget(os.getenv("DEMO_PERSONA_PASSWORD", ""), agent=AGENT, team_name=f"agent-{AGENT}")
        target.client(persona)
        workflows = target.visible_workflows(persona) if target.team_id else []
        projects = _team_projects(target, persona)
    except Exception as exc:  # noqa: BLE001 - any sign-in/transport failure is a failed row
        return {"auth_ok": False, "persona": persona, "projects": [], "missing": missing_all, "created": [], "detail": str(exc)}

    if AGENT not in workflows:
        why = f"signed in, but {AGENT!r} is not visible: " + (
            f"workflows in agent-{AGENT}={workflows}" if target.team_id else f"{persona} is not a member of team agent-{AGENT}"
        )
        return {"auth_ok": False, "persona": persona, "projects": projects, "missing": missing_all, "created": [], "detail": why}

    missing = [name for name in REQUIRED_PROJECTS if name not in {p["title"] for p in projects}]

    created, create_failures = [], []
    if ensure_projects and missing:
        for name in missing:
            try:
                target.create_team(persona, name, _DEMO_PROJECT_GROUPS)
                created.append(name)
            except Exception as exc:  # noqa: BLE001 - reported per project, never raised
                create_failures.append(f"{name} ({exc})")

        # Re-list rather than assume: a failed create must not be reported
        # as present.
        try:
            projects = _team_projects(target, persona)
            missing = [name for name in REQUIRED_PROJECTS if name not in {p["title"] for p in projects}]
        except Exception as exc:  # noqa: BLE001
            create_failures.append(f"re-list failed ({exc})")

    ok = not missing
    detail = (
        f"authenticated; {AGENT} visible; all three demo projects present as team workspaces; {_NO_CLASSIFICATION}"
        if ok
        else (
            f"authenticated; {AGENT} visible; missing={missing}"
            + (f" created={created}" if created else "")
            + (f" create_failures={create_failures}" if create_failures else "")
            + f"; {_NO_CLASSIFICATION}"
        )
    )
    return {"auth_ok": True, "persona": persona, "projects": projects, "missing": missing, "created": created, "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--ensure-projects", action="store_true", default=False)
    args = parser.parse_args()
    print(json.dumps(probe_auth_and_projects(args.persona, ensure_projects=args.ensure_projects)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
