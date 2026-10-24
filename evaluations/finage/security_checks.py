#!/usr/bin/env python3
"""Security-negative checks for Finage, mirroring evaluations/advantage/
security_checks.py's structure with ADR-0040's entitlement/business-role
fixtures substituted for Finage's own
(`finage-entitlement-only-user-01`/`finance-role-only-user-01`) and the
same static config check pattern - Finage's own OKF task bundle must
never declare the sales or ADV knowledge domains, or any live-Salesforce
capability, the config-level half of ADR-0326's least-privilege proof for
this slice (the runtime half - a live Comage/Sales capability denied by
the MCP Gateway - is covered by scenarios 12/13/18 in scenarios.yaml, not
repeated here).

Covers ADR-0032/0033 (identity propagation), ADR-0040 (agent entitlement
vs. business-role separation) and ADR-0037 (MCP server network/
workload-identity boundary) - see evaluations/tekos/security_checks.py's
own module docstring for why these are kept out of the fixed
20-scenario acceptance count.

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

# Must be set before importing run_scenarios below (its AGENT constant is
# resolved at import time, os.getenv("AGENT", "tekos")) - a bare `python3
# security_checks.py` run (this file's own README-documented invocation)
# has nothing else setting it; only run_acceptance_gate.py's wrapper
# happens to set this first via its own os.environ.setdefault(). Same fix
# every prior slice's own security_checks.py needed.
os.environ.setdefault("AGENT", "finage")
os.environ.setdefault("TASK_NAME", "answer-finance-question")

# run_scenarios.py is the canonical, AGENT-parameterized shared
# implementation physically checked in under evaluations/tekos/ (see that
# file's own module docstring for why) - added to sys.path explicitly so
# `python3 security_checks.py` works when run directly from this
# directory, not only when run_acceptance_gate.py's dynamic loader has
# already put evaluations/tekos/ on sys.path for us.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, MCP_GATEWAY_URL, TASK_NAME, _invoke_tool, _unifai, auth_headers  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "common"))
import unifai_checks  # noqa: E402
from okf_release import okf_root, task_declarations  # noqa: E402  (WP-165: agents and corp policies)
try:
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass

_LOG_AGENT = AGENT

# Not part of run_scenarios.py's URL set since none of the 20 fixed
# scenarios call ai-gateway directly (only the agents do, internally).
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080")

# Same reasoning as Arkos's/Advantage's own equivalent check: only the
# MCP Gateway calls this directly in normal operation - this check
# deliberately bypasses the gateway to prove the server itself denies an
# unauthorized direct caller (ADR-0037), independent of the NetworkPolicy
# layer. Reused here (not Finage-specific): ADR-0219 retargeted it from
# the deleted sales-db-mcp to confluence-mcp, which carries the identical
# gateway-pod-only NetworkPolicy and GatewayTokenMiddleware, so the
# boundary under test is unchanged.
CONFLUENCE_MCP_URL = os.getenv("CONFLUENCE_MCP_URL", "http://confluence-mcp.zuno-ai-run.svc.cluster.local:8000")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False


PROJECT_BINDING_CAPABILITY = "salesforce.opportunity.read"


def finage_never_declares_sales_or_adv_knowledge_domains() -> CheckResult:
    """ADR-0326 config-consistency check (no live cluster needed, same
    style as run_scenarios.py's model_router_fails_closed) - the
    config-level half of this slice's least-privilege proof: no
    agents/finage/tasks/*.md file's ACTUAL zuno.allowed_knowledge/
    allowed_tools declaration (the YAML frontmatter - never the Markdown
    body, which is free-form prose and may legitimately reference other
    agents' capabilities by name) may declare the sales or ADV knowledge
    domains, or any salesforce.*/aramis.* capability - except
    salesforce.opportunity.read on a project_required task (ADR-0512's
    project-binding check, see below). The runtime half (a
    live attempt denied by the MCP Gateway) is scenarios 12/13/18 in
    scenarios.yaml, not repeated here.
    """
    declarations = task_declarations(okf_root(REPO_ROOT), "finage")
    offending: list = []
    checked = 0
    for task_name, zuno in declarations.items():
        checked += 1
        allowed_knowledge = zuno.get("allowed_knowledge") or []
        allowed_tools = zuno.get("allowed_tools") or []
        if "knowledge.sales" in allowed_knowledge:
            offending.append(f"{task_name}.md: allowed_knowledge includes knowledge.sales")
        if "knowledge.adv" in allowed_knowledge:
            offending.append(f"{task_name}.md: allowed_knowledge includes knowledge.adv")
        for tool in allowed_tools:
            # ADR-0512 (WP-55), kept by ADR-0528: a project_required task
            # declares salesforce.opportunity.read for the project-binding
            # check only - a pre-graph call under the caller's identity
            # whose record never reaches the model. That one capability, on
            # those tasks only, is the documented exception; this check
            # predates it (2026-08-15 vs 2026-08-21).
            if tool == PROJECT_BINDING_CAPABILITY and zuno.get("project_required") is True:
                continue
            if tool.startswith("salesforce.") or tool.startswith("aramis."):
                offending.append(f"{task_name}.md: allowed_tools includes {tool}")
    ok = not offending
    return CheckResult(
        "finage_never_declares_sales_or_adv_knowledge_domains",
        ok,
        f"offending={offending}" if offending else f"checked {checked} task file(s)' frontmatter, none declare sales/ADV",
    )


def ai_gateway_local_only_forces_local_provider() -> CheckResult:
    """ADR-0035's mandatory acceptance test: a C2 request with
    X-Zuno-Local-Only: true must be served by the local provider even
    though C2 alone would otherwise permit an approved SaaS provider
    (policies/data-classification/classification.yaml: C2 is
    "approved-saas-only", not "local-only" - X-Zuno-Local-Only is what
    forces local regardless). Platform-wide (ai-gateway), not
    Finage-specific - included here for the same reason every prior
    slice's own gate includes it.
    """
    resp = httpx.post(
        f"{AI_GATEWAY_URL}/v1/chat/completions",
        headers={
            **auth_headers("finance-01"),
            "X-Zuno-Data-Classification": "C2",
            "X-Zuno-Local-Only": "true",
        },
        json={"model": "zuno-auto", "messages": [{"role": "user", "content": "Say OK."}]},
        timeout=30,
    )
    if resp.status_code != 200:
        return CheckResult("ai_gateway_local_only_forces_local_provider", False, f"status={resp.status_code} body={resp.text[:200]}")
    provider = resp.json().get("zuno_provider")
    # ADR-0412: several local providers exist; the ADR-0035 invariant is
    # "a local provider answered", not any particular name. Resolve the
    # answering provider's `kind` from provider-routing.yaml instead of
    # keeping a name allow-list here: this asserted
    # provider in ("local", "local-gpt-oss") and broke when WP-076/ADR-0521
    # added the MaaS-routed local entries (`local-maas`,
    # `local-gpt-oss-maas`) and made local-maas the preferred one - a false
    # failure, since a local provider had in fact answered. Same fix as
    # run_scenarios.py's model_router_prefers_local. Do not re-hardcode names.
    # Candidate paths, not one hardcoded depth: in a checkout this file sits
    # under evaluations/<agent>/, but in the acceptance-gate Job the same
    # ConfigMap is mounted at three places at once (/gate with flat keys,
    # /gate/policies, and /platform/ai-gateway at the filesystem root), so a
    # single parents[N] guess resolves differently depending on where the
    # loader put this module - which is exactly how this check first failed
    # with "/gate/platform/ai-gateway/provider-routing.yaml not found".
    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parents[2] / "platform/ai-gateway/provider-routing.yaml",
        pathlib.Path("/platform/ai-gateway/provider-routing.yaml"),
        here.parent / "provider-routing.yaml",
        pathlib.Path("/gate/provider-routing.yaml"),
    ]
    routing_path = next((c for c in candidates if c.is_file()), None)
    if routing_path is None:
        return CheckResult(
            "ai_gateway_local_only_forces_local_provider",
            False,
            f"provider-routing.yaml not found in any of {[str(c) for c in candidates]}",
        )
    routing = yaml.safe_load(routing_path.read_text())
    kinds = {p["name"]: p.get("kind") for p in routing.get("providers", [])}
    ok = kinds.get(provider) == "local"
    return CheckResult(
        "ai_gateway_local_only_forces_local_provider",
        ok,
        f"zuno_provider={provider} kind={kinds.get(provider)}",
    )



def entitlement_without_business_role_denied() -> CheckResult:
    """ADR-0040: agent entitlement and business role are orthogonal.
    finage-entitlement-only-user-01 holds agent_finage (can sign in /
    reach Finage) but no business role at all - not finance, not board.
    The MCP Gateway's user_group_rights factor
    (policies/tools/tool-policy.yaml: gmail.message.read.allowed_groups:
    [consultant, board, cdp, sales, adv, finance]) must still deny the
    call with 403, proving agent entitlement alone never substitutes for
    the business-role check.

    Probes read_gmail, which Finage DOES declare
    (tasks/check-my-drive-and-mail.md), so the agent_declaration factor
    passes and this check isolates the group factor exactly as it did
    before ADR-0219 removed the sxa.customer.read it originally used.
    """
    resp = _invoke_tool(
        "finage-entitlement-only-user-01",
        "read_gmail",
        {"query": "invoice"},
        classification="C1",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "entitlement_without_business_role_denied",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def direct_call_to_confluence_mcp_denied_without_gateway_token() -> CheckResult:
    """ADR-0037's mandatory acceptance test: a call to confluence-mcp that
    bypasses the MCP Gateway entirely (no X-Zuno-Gateway-Token, the
    shared workload-identity secret only the gateway holds) must be
    denied - by the server's own workload-identity check (401) if the
    caller's network path can reach it at all, or by the NetworkPolicy
    boundary itself if it can't.
    """
    try:
        resp = httpx.post(
            f"{CONFLUENCE_MCP_URL}/mcp",
            json={"jsonrpc": "2.0"},
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
            timeout=15,
        )
    except httpx.TransportError as exc:
        return CheckResult(
            "direct_call_to_confluence_mcp_denied_without_gateway_token",
            True,
            f"denied at the network layer (NetworkPolicy) before any HTTP response: {exc}",
        )
    ok = resp.status_code == 401
    return CheckResult(
        "direct_call_to_confluence_mcp_denied_without_gateway_token",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


# Checks about the agent itself (WP-155 wave 0; UnifAI is the only target since WP-156):
# ADR-0032/0033/0040 proven through UnifAI's session API, built from the shared factories in
# evaluations/common/unifai_checks.py. The checks above reach shared services (MCP gateway,
# ai-gateway, MCP servers) directly.
unifai_forwards_identity_to_the_gateways = unifai_checks.skip(
    CheckResult,
    "unifai_forwards_identity_to_the_gateways",
    "finage is a placeholder agent (ADR-0007): it has no UnifAI workflow to chat with",
)
unifai_ignores_a_client_supplied_identity_header = unifai_checks.client_identity_header_refused(CheckResult, _unifai)
business_role_without_entitlement_denied_by_unifai = unifai_checks.entitlement_denied(
    CheckResult, _unifai, agent=AGENT, task=TASK_NAME, persona="finance-role-only-user-01",
    mcp_gateway_url=MCP_GATEWAY_URL, auth_headers=auth_headers,
)


CHECKS = [
    unifai_forwards_identity_to_the_gateways,
    unifai_ignores_a_client_supplied_identity_header,
    finage_never_declares_sales_or_adv_knowledge_domains,
    ai_gateway_local_only_forces_local_provider,
    entitlement_without_business_role_denied,
    business_role_without_entitlement_denied_by_unifai,
    direct_call_to_confluence_mcp_denied_without_gateway_token,
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
    # auth_headers()/get_token() require EVAL_CLIENT_SECRET (zuno-evaluations client) - see README.md.
    sys.exit(main())
