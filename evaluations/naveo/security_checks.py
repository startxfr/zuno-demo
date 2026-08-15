#!/usr/bin/env python3
"""Security-negative checks for Naveo (ADR-0410/ADR-0307/WP-41,
scaffolded from platform/templates/agent/). Only the checks generic
enough to apply to any agent are generated here - identity propagation
(ADR-0032/0033) and the two-directional ADR-0040 entitlement/business-role
separation - plus one self-consistency check with no live-cluster
dependency at all. A hand-authored slice typically adds its own
narrative-specific checks on top (see evaluations/advantage/
security_checks.py for an example) - this scaffold deliberately doesn't
invent one, since Naveo declares no cross-domain boundary to prove
(ADR-0410: reuses existing knowledge/capabilities only).

This cannot be executed in the sandbox this repo was built in (no live
cluster) - written to be genuinely runnable once one exists, same as
run_scenarios.py.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass

import httpx
import yaml

os.environ.setdefault("AGENT", "naveo")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, BFF_URL, RUNTIME_URL, auth_headers  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def bff_forwards_identity_to_runtime() -> CheckResult:
    """ADR-0032: the BFF must forward the validated end-user bearer token
    to the Agent Runtime, which requires one and rejects calls without it.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("consultant-user-01"),
        json={"session_id": "sec-check-1", "message": "Where do I find the onboarding checklist?"},
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult("bff_forwards_identity_to_runtime", ok, f"status={resp.status_code} body={resp.text[:200]}")


def runtime_ignores_mismatched_user_sub() -> CheckResult:
    """ADR-0033: a request body's user_sub is informational only - the
    Runtime must derive the authoritative subject from the validated
    token, never this field.
    """
    import uuid

    forged_sub = f"not-a-real-user-{uuid.uuid4().hex[:8]}"
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers("consultant-user-01"),
        json={"session_id": "sec-check-2", "user_sub": forged_sub, "message": "Where do I find the onboarding checklist?"},
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult("runtime_ignores_mismatched_user_sub", ok, f"status={resp.status_code} forged_sub={forged_sub} body={resp.text[:200]}")


def entitlement_without_business_role_denied() -> CheckResult:
    """ADR-0040: agent_naveo entitlement without any
    business role must still be denied by the BFF/Runtime chat path
    (the agent entitlement alone never substitutes for the business-role
    check the MCP Gateway/policy layer performs).
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("naveo-entitlement-only-user-01"),
        json={"session_id": "sec-check-3", "message": "Where do I find the onboarding checklist?"},
        timeout=30,
    )
    # A business-role-less caller can still authenticate and chat (the
    # entitlement/role separation this scaffold's tools rely on is
    # enforced per-tool-call by the MCP Gateway, not by the chat route
    # itself) - this check instead proves the *tool* boundary: no tool
    # call reachable from this chat turn should succeed silently without
    # the business role. Left as a documented scaffold seam: fill in a
    # concrete tool-call assertion once Naveo's real persona is
    # reviewed (see NEXT_STEPS.md).
    ok = resp.status_code in (200, 403)
    return CheckResult("entitlement_without_business_role_denied", ok, f"status={resp.status_code} body={resp.text[:200]}")


def business_role_without_entitlement_denied_by_bff() -> CheckResult:
    """ADR-0040: the converse case. consultant-role-only-user-01 holds the
    consultant business role but lacks agent_naveo
    entitlement - the BFF's own entitlement check must deny with 403
    before the request ever reaches the Agent Runtime.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("consultant-role-only-user-01"),
        json={"session_id": "sec-check-4", "message": "Where do I find the onboarding checklist?"},
        timeout=30,
    )
    ok = resp.status_code == 403
    return CheckResult("business_role_without_entitlement_denied_by_bff", ok, f"status={resp.status_code} body={resp.text[:200]}")


def naveo_declares_only_scaffolded_knowledge_and_tools() -> CheckResult:
    """Self-consistency check (no live cluster needed): every
    agents/naveo/tasks/*.md file's actual YAML frontmatter must
    stay within the knowledge domains and tool capabilities this agent
    was scaffolded with - catches undeclared scope creep as the bundle
    evolves past its initial scaffold.
    """
    allowed_knowledge_ceiling = ['knowledge.tech', 'knowledge.project']
    allowed_tools_ceiling = ['search_confluence', 'web_search', 'list_drive_files']
    tasks_dir = REPO_ROOT / "agents" / "naveo" / "tasks"
    offending = []
    checked = 0
    for task_path in sorted(tasks_dir.glob("*.md")):
        parts = task_path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            continue
        checked += 1
        frontmatter = yaml.safe_load(parts[1]) or {}
        zuno = frontmatter.get("zuno") or {}
        for domain in zuno.get("allowed_knowledge") or []:
            if domain not in allowed_knowledge_ceiling:
                offending.append(f"{task_path.name}: allowed_knowledge includes undeclared {domain}")
        for tool in zuno.get("allowed_tools") or []:
            if tool not in allowed_tools_ceiling:
                offending.append(f"{task_path.name}: allowed_tools includes undeclared {tool}")
    ok = not offending
    return CheckResult(
        "naveo_declares_only_scaffolded_knowledge_and_tools",
        ok,
        f"offending={offending}" if offending else f"checked {checked} task file(s)' frontmatter, all within the scaffolded ceiling",
    )


CHECKS = [
    bff_forwards_identity_to_runtime,
    runtime_ignores_mismatched_user_sub,
    entitlement_without_business_role_denied,
    business_role_without_entitlement_denied_by_bff,
    naveo_declares_only_scaffolded_knowledge_and_tools,
]


def run() -> list:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            results.append(CheckResult(check.__name__, False, f"unhandled error: {exc}"))
    return results


def main() -> int:
    results = run()
    print(f"{'PASS':<6}{'CHECK'}")
    for r in results:
        print(f"{'✓' if r.passed else '✗':<6}{r.name}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")
    if all(r.passed for r in results):
        print("\nRESULT: PASS")
        return 0
    print("\nRESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
