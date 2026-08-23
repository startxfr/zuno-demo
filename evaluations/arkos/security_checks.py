#!/usr/bin/env python3
"""Security-negative checks for Arkos, mirroring evaluations/tekos/
security_checks.py's structure with ADR-0040's entitlement/business-role
fixtures substituted for Arkos's own (`arkos-entitlement-only-user-01`/
`consultant-role-only-user-01` - ADR-0349 moved Arkos's audience from
board to the consultant architect tier, so the shared consultant
role-only fixture now carries the converse case; the old
`board-role-only-user-01` fixture stays in the realm, forward-reserved
for Cognos) and the Confluence policy check retargeted at
the canonical `confluence.page.*` capability IDs Arkos's task declares
(rather than Tekos's legacy `search_confluence` tool name - both resolve
to the same policy entries, ADR-0116's migration-alias guarantee, but
checking the canonical ID directly is the more honest assertion for a
bundle that only ever declares the canonical form).

Covers ADR-0032/0033 (identity propagation), ADR-0034/0035 (classification
aggregation and source-level external-model restrictions), ADR-0040
(agent entitlement vs. business-role separation) and ADR-0037 (MCP server
network/workload-identity boundary) - see evaluations/tekos/
security_checks.py's own module docstring for why these are kept out of
the fixed 20-scenario acceptance count and why sales-db-mcp's bypass
check is included here even though it's unrelated to Arkos specifically
(ADR-0037's boundary is platform-wide, not agent-scoped, so any agent's
gate proving it is equally valid coverage).

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
# happens to set this first via its own os.environ.setdefault(). Found as
# a real, previously-unrun latent bug while adding evaluations/comage/
# security_checks.py (WP-33) and fixed here too.
os.environ.setdefault("AGENT", "arkos")

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
# layer (gitops/charts/mcp-sales-db's NetworkPolicy), which an HTTP-level
# check like this can't directly exercise.
SALES_DB_MCP_URL = os.getenv("SALES_DB_MCP_URL", "http://sales-db-mcp.zuno-ai-run.svc.cluster.local:8000")


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
        headers=auth_headers("consultant-01"),
        json={"session_id": "sec-check-1", "message": "Draft a DAT for a test project."},
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
    not this field. Submitting a token for a real persona (consultant-01)
    with a body user_sub claiming to be an unrelated, nonexistent identity
    must not be rejected or otherwise change the outcome (impersonation via
    the body field is impossible because the field is never trusted).
    """
    forged_sub = f"not-a-real-user-{uuid.uuid4().hex[:8]}"
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers("consultant-01"),
        json={
            "session_id": "sec-check-2",
            "user_sub": forged_sub,
            "message": "Draft a DAT for a test project.",
        },
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult(
        "runtime_ignores_mismatched_user_sub",
        ok,
        f"status={resp.status_code} forged_sub={forged_sub} body={resp.text[:200]}",
    )


def confluence_policy_is_c2_and_local_only() -> CheckResult:
    """ADR-0034/0035 config-consistency check (no live cluster needed, same
    style as run_scenarios.py's model_router_fails_closed): the canonical
    confluence.page.search/read capabilities Arkos's task declares must be
    classified C2 in both policies/data-classification/classification.yaml
    and policies/tools/tool-policy.yaml, with
    external_model_policy.allow_context: false on both entries.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    classification = yaml.safe_load((repo_root / "policies/data-classification/classification.yaml").read_text())
    tool_policy = yaml.safe_load((repo_root / "policies/tools/tool-policy.yaml").read_text())

    confluence_domain = classification.get("data_domains", {}).get("confluence")
    entries = {
        t["capability"]: t
        for t in tool_policy.get("tools", [])
        if t.get("capability") in ("confluence.page.search", "confluence.page.read")
    }
    ok = confluence_domain == "C2" and len(entries) == 2
    for capability, entry in entries.items():
        min_classification = entry.get("min_classification")
        allow_context = entry.get("external_model_policy", {}).get("allow_context", True)
        ok = ok and min_classification == "C2" and allow_context is False
    return CheckResult(
        "confluence_policy_is_c2_and_local_only",
        ok,
        f"confluence_domain={confluence_domain} entries={sorted(entries.keys())}",
    )


def ai_gateway_local_only_forces_local_provider() -> CheckResult:
    """ADR-0035's mandatory acceptance test: a C2 request with
    X-Zuno-Local-Only: true must be served by the local provider even
    though C2 alone would otherwise permit an approved SaaS provider
    (policies/data-classification/classification.yaml: C2 is
    "approved-saas-only", not "local-only" - X-Zuno-Local-Only is what
    forces local regardless).
    """
    resp = httpx.post(
        f"{AI_GATEWAY_URL}/v1/chat/completions",
        headers={
            **auth_headers("consultant-01"),
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


def entitlement_without_business_role_denied_confluence() -> CheckResult:
    """ADR-0040: agent entitlement and business role are orthogonal.
    arkos-entitlement-only-user-01 holds agent_arkos (can sign in / reach
    Arkos) but no business role at all - not board, not consultant. The MCP
    Gateway's user_group_rights factor (policies/tools/tool-policy.yaml:
    confluence.page.search.allowed_groups: [consultant, board]) must still
    deny the call with 403, proving agent entitlement alone never
    substitutes for the business-role check.
    """
    resp = _invoke_tool(
        "arkos-entitlement-only-user-01",
        "confluence.page.search",
        {"query": "OpenShift AI GPU sizing"},
        classification="C2",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "entitlement_without_business_role_denied_confluence",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def business_role_without_entitlement_denied_by_bff() -> CheckResult:
    """ADR-0040: the converse case. consultant-role-only-user-01 holds
    the consultant business role (would pass the MCP Gateway's group check
    for confluence.page.search; ADR-0349 made consultants Arkos's
    audience) but lacks agent_arkos entitlement. The BFF's
    server-side entitlement check (components/agent-bff/main.go) must deny
    the call with 403 before it ever reaches the Agent Runtime, proving
    business role alone never substitutes for agent entitlement.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("consultant-role-only-user-01"),
        json={"session_id": "sec-check-3", "message": "Draft a DAT for a test project."},
        timeout=30,
    )
    ok = resp.status_code == 403
    return CheckResult(
        "business_role_without_entitlement_denied_by_bff",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def direct_call_to_sales_db_mcp_denied_without_gateway_token() -> CheckResult:
    """ADR-0037's mandatory acceptance test (platform-wide boundary, not
    Arkos-specific - see this module's own docstring for why it's still
    included here): a call to sales-db-mcp that bypasses the MCP Gateway
    entirely (no X-Zuno-Gateway-Token, the shared workload-identity secret
    only the gateway holds) must be denied - by the server's own
    workload-identity check (401) if the caller's network path can reach
    it at all, or by the NetworkPolicy boundary itself if it can't.
    """
    try:
        resp = httpx.post(
            f"{SALES_DB_MCP_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_customer", "arguments": {"customer_id": 1}},
            },
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


def git_forge_never_grants_private_github_access() -> CheckResult:
    """ADR-0121: this server never grants private GitHub access, GitHub-side
    private/internal listing simply doesn't exist as a capability - only
    GitLab has a private variant. consultant-01 IS authorized to call
    git.repository.private.list (it's in draft-architecture-testimonial's
    allowed_tools, ADR-0121's table), so this call passes every policy-layer
    check and reaches the real git-forge server, which raises ValueError for
    provider="github" (components/mcp-servers/git-forge/server.py). MCP
    Gateway surfaces a downstream tool's raised error as 502 (downstream.py:
    `if result.is_error: raise DownstreamError(502, ...)`), not 403 - this
    check is defense-in-depth confirming the server's own refusal actually
    fires end to end, independent of the policy layer that would otherwise
    be the only thing standing between a caller and private GitHub data.
    """
    resp = _invoke_tool(
        "consultant-01",
        "git.repository.private.list",
        {"provider": "github", "owner": "openshift", "owner_type": "organization"},
        classification="C2",
    )
    ok = resp.status_code == 502
    return CheckResult(
        "git_forge_never_grants_private_github_access",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def arkos_chat_never_returns_photorealistic_images() -> CheckResult:
    """Policy update (post-ADR-0516): Arkos's tasks never list
    `image.generation.create` (SDXL/photorealistic) any more, only
    `diagram.generation.create` (Mermaid rendering) - see
    evaluations/tekos/gate_checks.py's
    arkos_declares_no_photorealistic_image_generation_capability for the
    static counterpart. app/graph/arkos_nodes.py's draft_node never even
    offers the generate_image tool schema to the model for Arkos any
    more, so no entry in the chat response's images can structurally be a
    generate_image/SDXL result. Mirrors
    evaluations/tekos/security_checks.py's own
    tekos_chat_never_returns_photorealistic_images exactly: asserts every
    returned image's mime_type is image/svg+xml (a rendered diagram),
    never image/png (what SDXL always returns).
    """
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/arkos/chat",
        headers=auth_headers("consultant-01"),
        json={
            "session_id": "sec-check-9",
            "user_sub": "consultant-01",
            "message": "Draft a short architecture testimonial and include a diagram illustrating a Kubernetes Deployment rolling update.",
        },
        timeout=30,
    )
    images = resp.json().get("images", []) if resp.status_code == 200 else []
    ok = resp.status_code == 200 and all(img.get("mime_type") == "image/svg+xml" for img in images)
    return CheckResult(
        "arkos_chat_never_returns_photorealistic_images",
        ok,
        f"status={resp.status_code} images={[img.get('mime_type') for img in images]}",
    )


CHECKS = [
    bff_forwards_identity_to_runtime,
    runtime_ignores_mismatched_user_sub,
    confluence_policy_is_c2_and_local_only,
    ai_gateway_local_only_forces_local_provider,
    entitlement_without_business_role_denied_confluence,
    business_role_without_entitlement_denied_by_bff,
    direct_call_to_sales_db_mcp_denied_without_gateway_token,
    git_forge_never_grants_private_github_access,
    arkos_chat_never_returns_photorealistic_images,
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
    # auth_headers()/get_token() require ARKOS_FRONTEND_CLIENT_SECRET - see README.md.
    sys.exit(main())
