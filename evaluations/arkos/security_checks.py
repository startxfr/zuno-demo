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
the fixed 20-scenario acceptance count and why confluence-mcp's bypass
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
os.environ.setdefault("TASK_NAME", "draft-architecture-testimonial")

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
from okf_release import okf_root  # noqa: E402  (WP-165: agents and corp policies)
try:
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass

_LOG_AGENT = AGENT

# Not part of run_scenarios.py's URL set since none of the 20 fixed
# scenarios call ai-gateway directly (only the agents do, internally).
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080")

# Same reasoning: only the MCP Gateway calls this directly in normal
# operation (components/mcp-gateway/app/downstream.py) - this check
# deliberately bypasses the gateway to prove the server itself denies an
# unauthorized direct caller (ADR-0037), independent of the NetworkPolicy
# layer (gitops/charts/mcp-confluence's NetworkPolicy), which an HTTP-level
# check like this can't directly exercise.
#
# ADR-0219 retargeted this from sales-db-mcp, which it deleted, to
# confluence-mcp: identical gateway-pod-only ingress NetworkPolicy and the
# same GatewayTokenMiddleware (both enforced by
# platform/supply-chain/check_mcp_server_conformance.py), so the boundary
# under test is unchanged. ADR-0037's acceptance test is retargeted, never
# dropped.
CONFLUENCE_MCP_URL = os.getenv("CONFLUENCE_MCP_URL", "http://confluence-mcp.zuno-ai-run.svc.cluster.local:8000")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False


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
    tool_policy = yaml.safe_load((okf_root(repo_root) / "policies/tools/tool-policy.yaml").read_text())

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


def direct_call_to_confluence_mcp_denied_without_gateway_token() -> CheckResult:
    """ADR-0037's mandatory acceptance test (platform-wide boundary, not
    Arkos-specific - see this module's own docstring for why it's still
    included here): a call to confluence-mcp that bypasses the MCP Gateway
    entirely (no X-Zuno-Gateway-Token, the shared workload-identity secret
    only the gateway holds) must be denied - by the server's own
    workload-identity check (401) if the caller's network path can reach
    it at all, or by the NetworkPolicy boundary itself if it can't.
    """
    try:
        resp = httpx.post(
            f"{CONFLUENCE_MCP_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_confluence", "arguments": {"query": "test"}},
            },
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


def arkos_cannot_launch_cluster_automation() -> CheckResult:
    """ADR-0355/WP-074: `aap.cluster.audit` launches real cluster automation.
    Arkos declares only the read-only `aap.platform.audit`
    (agents/arkos/tasks/draft-architecture-testimonial.md and
    workshop-presentation.md); Tekos alone declares the launch capability.

    Because both aap.* entries deliberately carry the SAME allowed_groups
    (policies/tools/tool-policy.yaml), the agent_declaration factor is the
    only thing separating Arkos from cluster automation - which is exactly
    why it gets its own check. consultant-01 IS in allowed_groups and IS
    entitled to Arkos, so a 403 here can only be the declaration factor.

    Headers are set explicitly rather than reusing _invoke_tool: that helper
    sends tekos's AGENT/TASK_NAME, and the whole point here is to call the
    gateway *as Arkos*.
    """
    resp = httpx.post(
        f"{MCP_GATEWAY_URL}/v1/tools/aap.cluster.audit/invoke",
        headers={
            **auth_headers("consultant-01"),
            "X-Zuno-Data-Classification": "C2",
            "X-Zuno-Agent": "arkos",
            "X-Zuno-Task": "draft-architecture-testimonial",
        },
        json={},
        timeout=15,
    )
    ok = resp.status_code == 403
    return CheckResult(
        "arkos_cannot_launch_cluster_automation",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def arkos_can_read_aap_platform_status() -> CheckResult:
    """The positive control for the check above: the same caller, the same
    agent, the same headers, but the capability Arkos DOES declare. Without
    this, a 403 from a blanket failure (gateway down, token rejected,
    binding missing) would look identical to the deliberate denial and the
    negative check would pass for the wrong reason.
    """
    resp = httpx.post(
        f"{MCP_GATEWAY_URL}/v1/tools/aap.platform.audit/invoke",
        headers={
            **auth_headers("consultant-01"),
            "X-Zuno-Data-Classification": "C2",
            "X-Zuno-Agent": "arkos",
            "X-Zuno-Task": "draft-architecture-testimonial",
        },
        json={},
        timeout=30,
    )
    ok = resp.status_code == 200
    return CheckResult(
        "arkos_can_read_aap_platform_status",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


# Checks about the agent itself (WP-155 wave 0; UnifAI is the only target since WP-156):
# ADR-0032/0033/0040 proven through UnifAI's session API, built from the shared factories in
# evaluations/common/unifai_checks.py. The checks above reach shared services (MCP gateway,
# ai-gateway, MCP servers) directly.
unifai_forwards_identity_to_the_gateways = unifai_checks.identity_forwarded(
    CheckResult, _unifai, "consultant-01", "Draft a Design & Architecture Testimonial for the Satellite scheduling project S0R42, using the Confluence documentation.",
        # Any call through the MCP gateway proves the caller's token reached it; the model may read a page or list a repository.
        ("confluence.page.search", "confluence.page.read", "git.repository.list")
)
unifai_ignores_a_client_supplied_identity_header = unifai_checks.client_identity_header_refused(CheckResult, _unifai)
business_role_without_entitlement_denied_by_unifai = unifai_checks.entitlement_denied(
    CheckResult, _unifai, agent=AGENT, task=TASK_NAME, persona="consultant-role-only-user-01",
    mcp_gateway_url=MCP_GATEWAY_URL, auth_headers=auth_headers,
)
# ADR-0415/ADR-0516: Arkos's tasks declare `diagram.generation.create` but never
# `image.generation.create` (gate_checks.py's
# arkos_declares_no_photorealistic_image_generation_capability is the static counterpart).
unifai_arkos_never_generates_photorealistic_images = unifai_checks.image_tool_boundary(
    CheckResult, _unifai, name="unifai_arkos_never_generates_photorealistic_images", persona="consultant-01",
    prompt="Draft a short architecture testimonial and include a diagram illustrating a Kubernetes Deployment rolling update.",
)

# Platform-wide checks (ADR-0583 two-user isolation, ADR-0585 A2A gateway identity contract) also run for this
# agent: `sale-01` has no `agent_arkos` group, `sale-01` is outside `consultant-02`'s team workspace.
A2A_GATEWAY_URL = os.getenv("A2A_GATEWAY_URL", "http://a2a-gateway.zuno-ai-run.svc.cluster.local:8080")
unifai_denies_another_users_objects_like_missing_ones = unifai_checks.cross_user_isolation(
    CheckResult, _unifai, owner="consultant-02", other="sale-01"
)
a2a_gateway_denies_unentitled_callers_like_unknown_agents = unifai_checks.a2a_gateway_denies_unentitled(
    CheckResult, agent="arkos", persona="sale-01", a2a_gateway_url=A2A_GATEWAY_URL, auth_headers=auth_headers
)


CHECKS = [
    unifai_forwards_identity_to_the_gateways,
    unifai_ignores_a_client_supplied_identity_header,
    confluence_policy_is_c2_and_local_only,
    ai_gateway_local_only_forces_local_provider,
    entitlement_without_business_role_denied_confluence,
    business_role_without_entitlement_denied_by_unifai,
    direct_call_to_confluence_mcp_denied_without_gateway_token,
    git_forge_never_grants_private_github_access,
    unifai_arkos_never_generates_photorealistic_images,
    arkos_cannot_launch_cluster_automation,
    arkos_can_read_aap_platform_status,
    unifai_denies_another_users_objects_like_missing_ones,
    a2a_gateway_denies_unentitled_callers_like_unknown_agents,
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
