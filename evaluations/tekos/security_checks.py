#!/usr/bin/env python3
"""Security-negative checks for ADR-0032/0033 (identity propagation),
ADR-0034/0035 (classification aggregation and source-level external-model
restrictions), ADR-0040 (agent entitlement vs. business-role separation),
ADR-0037 (MCP server network/workload-identity boundary), and ADR-0415/
ADR-0036 (image-generation entitlement vs. Tekos's own agent_declaration -
see the two checks appended at the bottom for the live/behavioral half of
the DAT/image-generation capability-boundary probe stress_test.py's
module docstring describes; gate_checks.py's
tekos_declares_no_dat_or_image_generation_capability is its static
config-only counterpart).

Kept separate from scenarios.yaml/run_scenarios.py rather than added as
scenarios 21+: ADR-0027 fixes Tekos's acceptance suite at exactly 20
scenarios, and these are security-negative checks for specific ADRs, not
part of that fixed acceptance count. Reuses run_scenarios.py's token-fetch
helpers rather than duplicating them. gate_checks.py holds ADR-0053's
remaining non-negative, non-scenario capability checks (currently
"permitted SaaS fallback" plus the two write-code/DAT-boundary checks
added alongside these). run_acceptance_gate.py (ADR-0053) is the single
entrypoint `make check` actually invokes, combining this module (100%
mandatory), gate_checks.py (100% mandatory) and run_scenarios.py (75%
threshold) into one gate with one exit code.

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

from run_scenarios import BFF_URL, RUNTIME_URL, _invoke_tool, auth_headers
try:
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass

_LOG_AGENT = "tekos"

# Not part of run_scenarios.py's URL set since none of the 20 fixed
# scenarios call ai-gateway directly (only agent-runtime does, internally).
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
        json={"session_id": "sec-check-1", "message": "What GPU does the local model run on?"},
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
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers("consultant-01"),
        json={
            "session_id": "sec-check-2",
            "user_sub": forged_sub,
            "message": "What GPU does the local model run on?",
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
    style as run_scenarios.py's model_router_fails_closed): Confluence must
    be classified C2 (not the old, incorrect C1) in both
    policies/data-classification/classification.yaml and
    policies/tools/tool-policy.yaml's search_confluence entry, and that
    entry must declare external_model_policy.allow_context: false.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    classification = yaml.safe_load((repo_root / "policies/data-classification/classification.yaml").read_text())
    tool_policy = yaml.safe_load((repo_root / "policies/tools/tool-policy.yaml").read_text())

    confluence_domain = classification.get("data_domains", {}).get("confluence")
    entry = next((t for t in tool_policy.get("tools", []) if t["tool"] == "search_confluence"), None)
    min_classification = entry.get("min_classification") if entry else None
    allow_context = (entry or {}).get("external_model_policy", {}).get("allow_context", True)

    ok = confluence_domain == "C2" and min_classification == "C2" and allow_context is False
    return CheckResult(
        "confluence_policy_is_c2_and_local_only",
        ok,
        f"confluence_domain={confluence_domain} min_classification={min_classification} allow_context={allow_context}",
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
    tekos-entitlement-only-user-01 holds agent_tekos (can sign in / reach
    Tekos) but no business role at all - not consultant, not board. The MCP
    Gateway's user_group_rights factor (policies/tools/tool-policy.yaml:
    search_confluence.allowed_groups: [consultant, board]) must still deny
    the call with 403, proving agent entitlement alone never substitutes
    for the business-role check.
    """
    resp = _invoke_tool(
        "tekos-entitlement-only-user-01",
        "search_confluence",
        {"query": "RHOAI 3.5 EA2 rollout"},
        classification="C2",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "entitlement_without_business_role_denied_confluence",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def business_role_without_entitlement_denied_by_bff() -> CheckResult:
    """ADR-0040: the converse case. consultant-role-only-user-01 holds the
    consultant business role (would pass the MCP Gateway's group check for
    search_confluence) but lacks agent_tekos entitlement. The BFF's
    server-side entitlement check (components/agent-bff/main.go) must deny
    the call with 403 before it ever reaches the Agent Runtime, proving
    business role alone never substitutes for agent entitlement.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("consultant-role-only-user-01"),
        json={"session_id": "sec-check-3", "message": "What GPU does the local model run on?"},
        timeout=30,
    )
    ok = resp.status_code == 403
    return CheckResult(
        "business_role_without_entitlement_denied_by_bff",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def direct_call_to_confluence_mcp_denied_without_gateway_token() -> CheckResult:
    """ADR-0037's mandatory acceptance test: a call to confluence-mcp that
    bypasses the MCP Gateway entirely (no X-Zuno-Gateway-Token, the shared
    workload-identity secret only the gateway holds - ansible/roles/vault/
    tasks/configure.yml, secret/zuno/mcp/gateway-workload-token) must be
    denied - by the server's own workload-identity check (401) if the
    caller's network path can reach it at all, or by the NetworkPolicy
    boundary itself (gitops/charts/mcp-confluence's NetworkPolicy, ADR-0052)
    if it can't. Since ADR-0053 wires this into `make check` as a Job
    running from inside the cluster (ansible/roles/agents/tasks/check.yml),
    that NetworkPolicy - which allows ingress only from the mcp-gateway
    pod, deliberately never extended to the acceptance-gate identity - is
    now the layer this check actually exercises in practice: a connection
    timeout/refusal is just as valid a "denied" outcome as an explicit 401,
    proving network location alone is already sufficient here and the
    workload-identity check is defense in depth, not the only layer.
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


def mcp_gateway_denies_generate_image_for_tekos_agent_declaration() -> CheckResult:
    """ADR-0036's agent_declaration factor, isolated from the group/role
    factor: `generate_image`'s allowed_groups
    (policies/tools/tool-policy.yaml) includes `consultant` -
    consultant-01's own business-role group - so a 403 here can only be
    explained by Tekos's `answer-technical-question` task never declaring
    `image.generation.create`/`generate_image` in its allowed_tools
    (agents/tekos/tasks/answer-technical-question.md; that capability
    belongs to Arkos/Advantage/Comage alone, ADR-0415). This is the
    isolated-boundary counterpart to entitlement_without_business_role_
    denied_confluence above (which isolates the opposite factor).
    """
    resp = _invoke_tool(
        "consultant-01",
        "generate_image",
        {"prompt": "a simple test diagram"},
        classification="C2",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "mcp_gateway_denies_generate_image_for_tekos_agent_declaration",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def mcp_gateway_denies_aap_cluster_audit_for_unauthorized_group() -> CheckResult:
    """ADR-0355 Security considerations, the mandated security-negative test:
    `aap.cluster.audit` is this repository's only capability that RUNS
    cluster automation, so an unauthorized caller must be stopped by the
    platform's own policy layer - not merely by AAP-side RBAC further down.

    tekos-entitlement-only-user-01 holds agent_tekos (so the BFF/runtime let
    it through) but no business role at all, while Tekos's
    answer-technical-question task DOES declare this capability - so the
    agent_declaration factor passes and a 403 here can only come from the
    user_group_rights factor (policies/tools/tool-policy.yaml:
    aap.cluster.audit.allowed_groups: [consultant, board, cdp]). That is the
    defence-in-depth claim ADR-0355 requires evidence for: the call never
    reaches AAP at all.
    """
    resp = _invoke_tool(
        "tekos-entitlement-only-user-01",
        "aap.cluster.audit",
        {},
        classification="C2",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "mcp_gateway_denies_aap_cluster_audit_for_unauthorized_group",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def mcp_gateway_denies_aap_platform_audit_for_unauthorized_group() -> CheckResult:
    """The read-only half of the same boundary. Both aap.* entries carry the
    same allowed_groups on purpose (see the block comment on them in
    policies/tools/tool-policy.yaml), so both must deny the same caller -
    an asymmetry here would mean one of the two entries drifted.
    """
    resp = _invoke_tool(
        "tekos-entitlement-only-user-01",
        "aap.platform.audit",
        {},
        classification="C2",
    )
    ok = resp.status_code == 403
    return CheckResult(
        "mcp_gateway_denies_aap_platform_audit_for_unauthorized_group",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def aap_platform_audit_succeeds_for_an_authorized_caller() -> CheckResult:
    """The ALLOW half - deliberately paired with the two denial checks above.

    Every other aap.* check in this repo asserts a 403, which means a green
    gate proves only that the boundary refuses the wrong caller; it says
    nothing about whether the tool works at all. That gap hid a real outage
    on 2026-08-27: the zuno-mcp AAP identity had no read access (the
    gateway silently drops `is_platform_auditor` on user create, so the
    Platform Auditor role was never actually held), and aap.platform.audit
    failed on every call with "no project named 'zuno-demo' in AAP" while
    all three checks stayed green.

    Asserting on the payload, not just the status: a 200 carrying an error
    body would be exactly as broken. `project.name` is the field that was
    unreachable without the role, so it is the one worth pinning.
    """
    resp = _invoke_tool(
        "consultant-01",
        "aap.platform.audit",
        {"recent_jobs": 3},
        classification="C2",
    )
    if resp.status_code != 200:
        return CheckResult(
            "aap_platform_audit_succeeds_for_an_authorized_caller",
            False,
            f"status={resp.status_code} body={resp.text[:200]}",
        )
    body = resp.json()
    result = body.get("result", body)
    project = (result.get("project") or {}).get("name")
    controller = (result.get("controller") or {}).get("version")
    ok = project == "zuno-demo" and bool(controller)
    return CheckResult(
        "aap_platform_audit_succeeds_for_an_authorized_caller",
        ok,
        f"project={project!r} controller_version={controller!r}",
    )


def tekos_chat_never_returns_photorealistic_images() -> CheckResult:
    """ADR-0415/ADR-0516: Tekos's task never lists
    `image.generation.create` (SDXL/photorealistic), only
    `diagram.generation.create` (ADR-0516's Mermaid rendering) as of the
    latter's deliberate carve-out - app/graph/nodes.py's reason_node never
    even offers the generate_image tool schema to the model for Tekos, so
    NO entry in `ChatResponse.images` can structurally be a
    generate_image/SDXL result. This used to assert `images == []`
    unconditionally (renamed from tekos_chat_never_returns_image_
    artifacts) - that broke the moment Tekos legitimately started
    returning diagram images, so the check now asserts the structural
    fact that actually matters: every image entry's mime_type is
    image/svg+xml (a rendered diagram), never image/png (what SDXL always
    returns - see components/mcp-gateway/app/handlers/image_gen.py's own
    hardcoded "mime_type": "image/png"). The prompt below deliberately
    asks for a diagram (not a photorealistic image) specifically to prove
    the positive path doesn't accidentally produce a PNG.
    """
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers("consultant-01"),
        json={
            "session_id": "sec-check-8",
            "user_sub": "consultant-01",
            "message": "Generate a diagram illustrating a Kubernetes Deployment rolling update.",
        },
        timeout=30,
    )
    images = resp.json().get("images", []) if resp.status_code == 200 else []
    ok = resp.status_code == 200 and all(img.get("mime_type") == "image/svg+xml" for img in images)
    return CheckResult(
        "tekos_chat_never_returns_photorealistic_images",
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
    direct_call_to_confluence_mcp_denied_without_gateway_token,
    mcp_gateway_denies_generate_image_for_tekos_agent_declaration,
    tekos_chat_never_returns_photorealistic_images,
    mcp_gateway_denies_aap_cluster_audit_for_unauthorized_group,
    mcp_gateway_denies_aap_platform_audit_for_unauthorized_group,
    aap_platform_audit_succeeds_for_an_authorized_caller,
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
    # auth_headers()/get_token() require TEKOS_FRONTEND_CLIENT_SECRET - see README.md.
    sys.exit(main())
