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

# run_scenarios.py is the canonical, AGENT-parameterized shared
# implementation physically checked in under evaluations/tekos/ (see that
# file's own module docstring for why) - added to sys.path explicitly so
# `python3 security_checks.py` works when run directly from this
# directory, not only when run_acceptance_gate.py's dynamic loader has
# already put evaluations/tekos/ on sys.path for us.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, BFF_URL, RUNTIME_URL, _invoke_tool, auth_headers  # noqa: E402
try:
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass

_LOG_AGENT = AGENT

# Not part of run_scenarios.py's URL set since none of the 20 fixed
# scenarios call ai-gateway directly (only agent-runtime does, internally).
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080")

# Same reasoning as Arkos's/Advantage's own equivalent check: only the
# MCP Gateway calls this directly in normal operation - this check
# deliberately bypasses the gateway to prove the server itself denies an
# unauthorized direct caller (ADR-0037), independent of the NetworkPolicy
# layer. Reused here (not Finage-specific) - Finage's own declared sxa.*
# capabilities are served by this same backend, so it's a directly
# relevant boundary for this slice too.
SALES_DB_MCP_URL = os.getenv("SALES_DB_MCP_URL", "http://sales-db-mcp.zuno-ai-run.svc.cluster.local:8000")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def bff_forwards_identity_to_runtime() -> CheckResult:
    """ADR-0032: the BFF must forward the validated end-user bearer token to
    the Agent Runtime, which requires one (app/auth.py:validate_token) and
    rejects calls without it. Before this ADR's fix, every BFF -> Runtime
    call was unauthenticated and the Runtime would have rejected it with
    401, surfaced to the client as a 502 from the BFF - so a 200 here with a
    real reply is direct evidence the token now reaches the Runtime.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("finance-01"),
        json={"session_id": "sec-check-1", "message": "What invoices are outstanding for the Acme account?"},
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult(
        "bff_forwards_identity_to_runtime",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def runtime_ignores_mismatched_user_sub() -> CheckResult:
    """ADR-0033: a request body's user_sub is informational only - the
    Runtime must derive the authoritative subject from the validated token,
    not this field. Submitting a token for a real persona (finance-01)
    with a body user_sub claiming to be an unrelated, nonexistent identity
    must not be rejected or otherwise change the outcome (impersonation via
    the body field is impossible because the field is never trusted).
    """
    import uuid

    forged_sub = f"not-a-real-user-{uuid.uuid4().hex[:8]}"
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers("finance-01"),
        json={
            "session_id": "sec-check-2",
            "user_sub": forged_sub,
            "message": "What invoices are outstanding for the Acme account?",
        },
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult(
        "runtime_ignores_mismatched_user_sub",
        ok,
        f"status={resp.status_code} forged_sub={forged_sub} body={resp.text[:200]}",
    )


def finage_never_declares_sales_or_adv_knowledge_domains() -> CheckResult:
    """ADR-0326 config-consistency check (no live cluster needed, same
    style as run_scenarios.py's model_router_fails_closed) - the
    config-level half of this slice's least-privilege proof: no
    agents/finage/tasks/*.md file's ACTUAL zuno.allowed_knowledge/
    allowed_tools declaration (the YAML frontmatter - never the Markdown
    body, which is free-form prose and may legitimately reference other
    agents' capabilities by name) may declare the sales or ADV knowledge
    domains, or any salesforce.*/aramis.* capability. The runtime half (a
    live attempt denied by the MCP Gateway) is scenarios 12/13/18 in
    scenarios.yaml, not repeated here.
    """
    tasks_dir = REPO_ROOT / "agents" / "finage" / "tasks"
    offending: list = []
    checked = 0
    for task_path in sorted(tasks_dir.glob("*.md")):
        parts = task_path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            continue
        checked += 1
        frontmatter = yaml.safe_load(parts[1]) or {}
        zuno = frontmatter.get("zuno") or {}
        allowed_knowledge = zuno.get("allowed_knowledge") or []
        allowed_tools = zuno.get("allowed_tools") or []
        if "knowledge.sales" in allowed_knowledge:
            offending.append(f"{task_path.name}: allowed_knowledge includes knowledge.sales")
        if "knowledge.adv" in allowed_knowledge:
            offending.append(f"{task_path.name}: allowed_knowledge includes knowledge.adv")
        for tool in allowed_tools:
            if tool.startswith("salesforce.") or tool.startswith("aramis."):
                offending.append(f"{task_path.name}: allowed_tools includes {tool}")
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
    # ADR-0412: two local providers exist (qwen + gpt-oss); the ADR-0035
    # invariant is "a local provider answered", not the qwen name
    # specifically (a preference or a fallback may pick the other one).
    ok = provider in ("local", "local-gpt-oss")
    return CheckResult("ai_gateway_local_only_forces_local_provider", ok, f"zuno_provider={provider}")


def entitlement_without_business_role_denied_sxa() -> CheckResult:
    """ADR-0040: agent entitlement and business role are orthogonal.
    finage-entitlement-only-user-01 holds agent_finage (can sign in /
    reach Finage) but no business role at all - not finance, not board.
    The MCP Gateway's user_group_rights factor
    (policies/tools/tool-policy.yaml: sxa.customer.read.allowed_groups:
    [sales, adv, board, finance]) must still deny the call with 403,
    proving agent entitlement alone never substitutes for the
    business-role check.
    """
    resp = _invoke_tool(
        "finage-entitlement-only-user-01",
        "sxa.customer.read",
        {"customer_id": 1},
        classification="C2",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "entitlement_without_business_role_denied_sxa",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def business_role_without_entitlement_denied_by_bff() -> CheckResult:
    """ADR-0040: the converse case. finance-role-only-user-01 holds the
    finance business role (would pass the MCP Gateway's group check for
    sxa.customer.read) but lacks agent_finage entitlement. The BFF's
    server-side entitlement check (components/agent-bff/main.go) must
    deny the call with 403 before it ever reaches the Agent Runtime,
    proving business role alone never substitutes for agent entitlement.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("finance-role-only-user-01"),
        json={"session_id": "sec-check-3", "message": "What invoices are outstanding for the Acme account?"},
        timeout=30,
    )
    ok = resp.status_code == 403
    return CheckResult(
        "business_role_without_entitlement_denied_by_bff",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def direct_call_to_sales_db_mcp_denied_without_gateway_token() -> CheckResult:
    """ADR-0037's mandatory acceptance test: a call to sales-db-mcp that
    bypasses the MCP Gateway entirely (no X-Zuno-Gateway-Token, the
    shared workload-identity secret only the gateway holds) must be
    denied - by the server's own workload-identity check (401) if the
    caller's network path can reach it at all, or by the NetworkPolicy
    boundary itself if it can't. Directly relevant to Finage: this is the
    same backend its own sxa.* capabilities are served by.
    """
    try:
        resp = httpx.post(
            f"{SALES_DB_MCP_URL}/mcp",
            json={"jsonrpc": "2.0"},
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
            timeout=15,
        )
    except httpx.TransportError as exc:
        return CheckResult(
            "direct_call_to_sales_db_mcp_denied_without_gateway_token",
            True,
            f"denied at the network layer (NetworkPolicy) before any HTTP response: {exc}",
        )
    ok = resp.status_code == 401
    return CheckResult(
        "direct_call_to_sales_db_mcp_denied_without_gateway_token",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


CHECKS = [
    bff_forwards_identity_to_runtime,
    runtime_ignores_mismatched_user_sub,
    finage_never_declares_sales_or_adv_knowledge_domains,
    ai_gateway_local_only_forces_local_provider,
    entitlement_without_business_role_denied_sxa,
    business_role_without_entitlement_denied_by_bff,
    direct_call_to_sales_db_mcp_denied_without_gateway_token,
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
        print(f"{'✓' if r.passed else '✗':<6}{r.name}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    if all(r.passed for r in results):
        print("\nRESULT: PASS")
        return 0
    print("\nRESULT: FAIL")
    return 1


if __name__ == "__main__":
    # auth_headers()/get_token() require FINAGE_FRONTEND_CLIENT_SECRET - see README.md.
    sys.exit(main())
