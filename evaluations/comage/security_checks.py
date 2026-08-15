#!/usr/bin/env python3
"""Security-negative checks for Comage, mirroring evaluations/arkos/
security_checks.py's structure with ADR-0040's entitlement/business-role
fixtures substituted for Comage's own
(`comage-entitlement-only-user-01`/`sales-role-only-user-01`) and the
Confluence policy check replaced with Salesforce's own (Comage's live-read
capability, `salesforce.opportunity.*`, not Confluence).

Covers ADR-0032/0033 (identity propagation), ADR-0034 (classification
aggregation), ADR-0040 (agent entitlement vs. business-role separation)
and ADR-0037 (MCP server network/workload-identity boundary) - see
evaluations/tekos/security_checks.py's own module docstring for why these
are kept out of the fixed 20-scenario acceptance count.

Deliberately does NOT re-assert `external_model_policy.allow_context:
false` for Salesforce the way Arkos's own check does for Confluence:
ADR-0035's local-only restriction is Confluence's own source-level/
contractual restriction (see that ADR's Context), not a general C2 rule -
Salesforce content stays governed by C2's ordinary restricted-SaaS
routing (policies/tools/tool-policy.yaml's salesforce.opportunity.* entries
carry no such field, deliberately).

This cannot be executed in the sandbox this repo was built in (no live
cluster) - written to be genuinely runnable once one exists, same as
run_scenarios.py.
"""
from __future__ import annotations

import os
import pathlib
import sys
import uuid
from dataclasses import dataclass

import httpx
import yaml

# Must be set before importing run_scenarios below (its AGENT constant is
# resolved at import time, os.getenv("AGENT", "tekos")) - a bare `python3
# security_checks.py` run (this file's own README-documented invocation)
# has nothing else setting it; only run_acceptance_gate.py's wrapper
# happens to set this first via its own os.environ.setdefault().
os.environ.setdefault("AGENT", "comage")

# run_scenarios.py is the canonical, AGENT-parameterized shared
# implementation physically checked in under evaluations/tekos/ (see that
# file's own module docstring for why) - added to sys.path explicitly so
# `python3 security_checks.py` works when run directly from this
# directory, not only when run_acceptance_gate.py's dynamic loader has
# already put evaluations/tekos/ on sys.path for us.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, BFF_URL, RUNTIME_URL, _invoke_tool, auth_headers  # noqa: E402

# Not part of run_scenarios.py's URL set since none of the 20 fixed
# scenarios call ai-gateway directly (only agent-runtime does, internally).
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080")

# Same reasoning: only the MCP Gateway calls this directly in normal
# operation (components/mcp-gateway/app/downstream.py) - this check
# deliberately bypasses the gateway to prove the server itself denies an
# unauthorized direct caller (ADR-0037), independent of the NetworkPolicy
# layer (gitops/charts/mcp-salesforce's NetworkPolicy), which an HTTP-level
# check like this can't directly exercise. Unlike Arkos's own equivalent
# check (which re-proves this boundary against an already-covered server,
# sales-db-mcp), this one exercises Comage's OWN new server for real.
SALESFORCE_MCP_URL = os.getenv("SALESFORCE_MCP_URL", "http://salesforce-mcp.zuno-ai-run.svc.cluster.local:8000")


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
        headers=auth_headers("sales-user-01"),
        json={"session_id": "sec-check-1", "message": "What's the status of the Acme Renewal deal?"},
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
    not this field. Submitting a token for a real persona (sales-user-01)
    with a body user_sub claiming to be an unrelated, nonexistent identity
    must not be rejected or otherwise change the outcome (impersonation via
    the body field is impossible because the field is never trusted).
    """
    forged_sub = f"not-a-real-user-{uuid.uuid4().hex[:8]}"
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers("sales-user-01"),
        json={
            "session_id": "sec-check-2",
            "user_sub": forged_sub,
            "message": "What's the status of the Acme Renewal deal?",
        },
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult(
        "runtime_ignores_mismatched_user_sub",
        ok,
        f"status={resp.status_code} forged_sub={forged_sub} body={resp.text[:200]}",
    )


def salesforce_policy_is_c2() -> CheckResult:
    """ADR-0034 config-consistency check (no live cluster needed, same
    style as run_scenarios.py's model_router_fails_closed): the three
    salesforce.opportunity.* capabilities Comage's tasks declare must be
    classified C2 in policies/tools/tool-policy.yaml, matching
    knowledge.sales's own `sales-data: C2` domain in
    policies/data-classification/classification.yaml.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    classification = yaml.safe_load((repo_root / "policies/data-classification/classification.yaml").read_text())
    tool_policy = yaml.safe_load((repo_root / "policies/tools/tool-policy.yaml").read_text())

    sales_data_domain = classification.get("data_domains", {}).get("sales-data")
    entries = {
        t["capability"]: t
        for t in tool_policy.get("tools", [])
        if t.get("capability", "").startswith("salesforce.opportunity.")
    }
    ok = sales_data_domain == "C2" and len(entries) == 3
    for capability, entry in entries.items():
        ok = ok and entry.get("min_classification") == "C2"
    return CheckResult(
        "salesforce_policy_is_c2",
        ok,
        f"sales_data_domain={sales_data_domain} entries={sorted(entries.keys())}",
    )


def ai_gateway_local_only_forces_local_provider() -> CheckResult:
    """ADR-0035's mandatory acceptance test: a C2 request with
    X-Zuno-Local-Only: true must be served by the local provider even
    though C2 alone would otherwise permit an approved SaaS provider
    (policies/data-classification/classification.yaml: C2 is
    "approved-saas-only", not "local-only" - X-Zuno-Local-Only is what
    forces local regardless). Platform-wide (ai-gateway), not Comage-
    specific - included here for the same reason Arkos's own gate includes
    it (every agent's gate is independent, this boundary is worth
    re-proving from each).
    """
    resp = httpx.post(
        f"{AI_GATEWAY_URL}/v1/chat/completions",
        headers={
            **auth_headers("sales-user-01"),
            "X-Zuno-Data-Classification": "C2",
            "X-Zuno-Local-Only": "true",
        },
        json={"model": "zuno-auto", "messages": [{"role": "user", "content": "Say OK."}]},
        timeout=30,
    )
    if resp.status_code != 200:
        return CheckResult("ai_gateway_local_only_forces_local_provider", False, f"status={resp.status_code} body={resp.text[:200]}")
    provider = resp.json().get("zuno_provider")
    ok = provider == "local"
    return CheckResult("ai_gateway_local_only_forces_local_provider", ok, f"zuno_provider={provider}")


def entitlement_without_business_role_denied_salesforce() -> CheckResult:
    """ADR-0040: agent entitlement and business role are orthogonal.
    comage-entitlement-only-user-01 holds agent_comage (can sign in / reach
    Comage) but no business role at all - not sales, not board. The MCP
    Gateway's user_group_rights factor (policies/tools/tool-policy.yaml:
    salesforce.opportunity.read.allowed_groups: [sales, board]) must still
    deny the call with 403, proving agent entitlement alone never
    substitutes for the business-role check.
    """
    resp = _invoke_tool(
        "comage-entitlement-only-user-01",
        "salesforce.opportunity.read",
        {"query": "Acme Renewal"},
        classification="C2",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "entitlement_without_business_role_denied_salesforce",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def business_role_without_entitlement_denied_by_bff() -> CheckResult:
    """ADR-0040: the converse case. sales-role-only-user-01 holds the
    sales business role (would pass the MCP Gateway's group check for
    salesforce.opportunity.read) but lacks agent_comage entitlement. The
    BFF's server-side entitlement check (components/agent-bff/main.go)
    must deny the call with 403 before it ever reaches the Agent Runtime,
    proving business role alone never substitutes for agent entitlement.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("sales-role-only-user-01"),
        json={"session_id": "sec-check-3", "message": "What's the status of the Acme Renewal deal?"},
        timeout=30,
    )
    ok = resp.status_code == 403
    return CheckResult(
        "business_role_without_entitlement_denied_by_bff",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def direct_call_to_salesforce_mcp_denied_without_gateway_token() -> CheckResult:
    """ADR-0037's mandatory acceptance test, exercised against Comage's own
    new MCP server this time (components/mcp-servers/salesforce): a call
    that bypasses the MCP Gateway entirely (no X-Zuno-Gateway-Token, the
    shared workload-identity secret only the gateway holds) must be denied
    - by the server's own workload-identity check (401) if the caller's
    network path can reach it at all, or by the NetworkPolicy boundary
    itself (gitops/charts/mcp-salesforce's NetworkPolicy) if it can't.
    """
    try:
        resp = httpx.post(
            f"{SALESFORCE_MCP_URL}/mcp",
            json={"jsonrpc": "2.0"},
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
            timeout=15,
        )
    except httpx.TransportError as exc:
        return CheckResult(
            "direct_call_to_salesforce_mcp_denied_without_gateway_token",
            True,
            f"denied at the network layer (NetworkPolicy) before any HTTP response: {exc}",
        )
    ok = resp.status_code == 401
    return CheckResult(
        "direct_call_to_salesforce_mcp_denied_without_gateway_token",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


CHECKS = [
    bff_forwards_identity_to_runtime,
    runtime_ignores_mismatched_user_sub,
    salesforce_policy_is_c2,
    ai_gateway_local_only_forces_local_provider,
    entitlement_without_business_role_denied_salesforce,
    business_role_without_entitlement_denied_by_bff,
    direct_call_to_salesforce_mcp_denied_without_gateway_token,
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
    # auth_headers()/get_token() require COMAGE_FRONTEND_CLIENT_SECRET - see README.md.
    sys.exit(main())
