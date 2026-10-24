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


os.environ.setdefault("AGENT", "naveo")
os.environ.setdefault("TASK_NAME", "answer-onboarding-question")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, MCP_GATEWAY_URL, TASK_NAME, _unifai, auth_headers  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "common"))
import unifai_checks  # noqa: E402
from okf_release import okf_root, task_declarations  # noqa: E402  (WP-165: agents and corp policies)
try:
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass

_LOG_AGENT = AGENT

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False


def naveo_declares_only_scaffolded_knowledge_and_tools() -> CheckResult:
    """Self-consistency check (no live cluster needed): every
    agents/naveo/tasks/*.md file's actual YAML frontmatter must
    stay within the knowledge domains and tool capabilities this agent
    was scaffolded with - catches undeclared scope creep as the bundle
    evolves past its initial scaffold.
    """
    allowed_knowledge_ceiling = ['knowledge.tech', 'knowledge.project']
    allowed_tools_ceiling = ['search_confluence', 'web_search', 'list_drive_files']
    declarations = task_declarations(okf_root(REPO_ROOT), "naveo")
    offending = []
    checked = 0
    for task_name, zuno in declarations.items():
        checked += 1
        for domain in zuno.get("allowed_knowledge") or []:
            if domain not in allowed_knowledge_ceiling:
                offending.append(f"{task_name}.md: allowed_knowledge includes undeclared {domain}")
        for tool in zuno.get("allowed_tools") or []:
            if tool not in allowed_tools_ceiling:
                offending.append(f"{task_name}.md: allowed_tools includes undeclared {tool}")
    ok = not offending
    return CheckResult(
        "naveo_declares_only_scaffolded_knowledge_and_tools",
        ok,
        f"offending={offending}" if offending else f"checked {checked} task file(s)' frontmatter, all within the scaffolded ceiling",
    )


# Checks about the agent itself (WP-155 wave 0; UnifAI is the only target since WP-156):
# ADR-0032/0033/0040 proven through UnifAI's session API, built from the shared factories in
# evaluations/common/unifai_checks.py. The checks above reach shared services (MCP gateway,
# ai-gateway, MCP servers) directly.
unifai_forwards_identity_to_the_gateways = unifai_checks.skip(
    CheckResult,
    "unifai_forwards_identity_to_the_gateways",
    "naveo is a placeholder agent (ADR-0007): it has no UnifAI workflow to chat with",
)
unifai_ignores_a_client_supplied_identity_header = unifai_checks.client_identity_header_refused(CheckResult, _unifai)
business_role_without_entitlement_denied_by_unifai = unifai_checks.entitlement_denied(
    CheckResult, _unifai, agent=AGENT, task=TASK_NAME, persona="consultant-role-only-user-01",
    mcp_gateway_url=MCP_GATEWAY_URL, auth_headers=auth_headers,
)
# ADR-0040, entitlement without any business role: the legacy check only proved a chat turn
# was answered or refused (a documented scaffold seam, see NEXT_STEPS.md). Naveo has no
# UnifAI workflow to chat with, so it is reported as skipped until a concrete tool-call
# assertion replaces it.
entitlement_without_business_role_denied = unifai_checks.skip(
    CheckResult,
    "entitlement_without_business_role_denied",
    "naveo is a placeholder agent (ADR-0007): it has no UnifAI workflow to chat with",
)


CHECKS = [
    unifai_forwards_identity_to_the_gateways,
    unifai_ignores_a_client_supplied_identity_header,
    entitlement_without_business_role_denied,
    business_role_without_entitlement_denied_by_unifai,
    naveo_declares_only_scaffolded_knowledge_and_tools,
]


def run() -> list:
    results = []
    for check in CHECKS:
        try:
            result = check()
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            result = CheckResult(check.__name__, False, f"unhandled error: {exc}")
        results.append(result)
        log_test_line(_LOG_AGENT, "security", result.name, result.name, result.passed, result.detail)
    return results


def main() -> int:
    results = run()

    print(f"{'PASS':<6}{'CHECK'}")
    for r in results:
        print(f"{'-' if r.skipped else '✓' if r.passed else '✗':<6}{r.name}")
        if (not r.passed or r.skipped) and r.detail:
            print(f"      -> {r.detail}")

    _unifai().cleanup()
    if all(r.passed for r in results if not r.skipped):
        print("\nRESULT: PASS")
        return 0
    print("\nRESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
