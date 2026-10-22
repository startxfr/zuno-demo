"""ADR-0571 (WP-152) tests for the `/mcp` front-door's agent mode (app/main.py's
_agent_surface + app/mcp_frontdoor.py's Surface), against the real repo
bindings, tool policy and OKF bundles:

- with X-Zuno-Agent/X-Zuno-Task, tools/list shows only tools the agent task
  declares AND the caller's groups/classification allow;
- a tool outside the task's declaration is refused on tools/call;
- a caller whose groups lack the right sees nothing and is refused;
- a caller outside the agent's zuno.access.groups is refused (ADR-0040);
- without X-Zuno-Agent the ADR-0524 ceiling (Lightspeed) still applies;
- an unknown agent gets an empty surface;
- an OpenShift (TokenReview) identity cannot declare an agent.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_mcp_frontdoor_agent.py
"""
from __future__ import annotations

import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
# Same "point the import-time singletons at the real repo files" pattern as
# tests/test_auth_mode_enforcement.py - must run before `import app.main`.
os.environ.setdefault("TOOL_BINDINGS_PATH", str(_REPO_ROOT / "platform/bindings/tools/tool-bindings.yaml"))
os.environ.setdefault("TOOL_POLICY_PATH", str(_REPO_ROOT / "policies/tools/tool-policy.yaml"))
os.environ.setdefault(
    "DATA_CLASSIFICATION_PATH", str(_REPO_ROOT / "policies/data-classification/classification.yaml")
)
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from fastapi.testclient import TestClient  # noqa: E402

import app.main as gateway_main  # noqa: E402
from app import mcp_frontdoor  # noqa: E402
from app.auth import CallerIdentity, validate_token_or_kubernetes  # noqa: E402

AGENT, TASK = "tekos", "answer-technical-question"

_CONSULTANT = CallerIdentity(
    sub="consultant-01", groups=["consultant", "agent_tekos"], raw_claims={"iss": "zuno"}, token="caller-jwt"
)
_ENTITLED_ONLY = CallerIdentity(
    sub="tekos-entitlement-only-user-01", groups=["agent_tekos"], raw_claims={"iss": "zuno"}, token="caller-jwt"
)
_FINANCE = CallerIdentity(sub="finance-01", groups=["finance"], raw_claims={"iss": "zuno"}, token="caller-jwt")
_OPENSHIFT = CallerIdentity(
    sub="kube:admin", groups=["system:authenticated"], raw_claims={"tokenReview": {}}, token="ocp-token"
)


def _client(identity: CallerIdentity) -> TestClient:
    assert gateway_main.binding_registry.loaded, gateway_main.binding_registry.load_error
    assert gateway_main.policy_store.loaded, gateway_main.policy_store.load_error
    assert gateway_main.agent_declarations.get(AGENT) is not None, gateway_main.agent_declarations.load_error
    gateway_main.app.dependency_overrides[validate_token_or_kubernetes] = lambda: identity
    return TestClient(gateway_main.app)


def _rpc(identity: CallerIdentity, method: str, params: dict | None = None, agent: str = AGENT, task: str = TASK):
    headers = {"X-Zuno-Data-Classification": "C2"}
    if agent:
        headers.update({"X-Zuno-Agent": agent, "X-Zuno-Task": task})
    try:
        return _client(identity).post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, headers=headers
        )
    finally:
        gateway_main.app.dependency_overrides.clear()


def _listed(identity: CallerIdentity, **kw) -> set:
    resp = _rpc(identity, "tools/list", **kw)
    assert resp.status_code == 200, resp.text
    return {t["name"] for t in resp.json()["result"]["tools"]}


def _declared_capabilities() -> set:
    declared = gateway_main.agent_declarations.get(AGENT).tasks[TASK]
    out = set()
    for name in declared:
        binding = gateway_main.binding_registry.resolve(name)
        out.add(binding.capability if binding else name)
    return out


def test_tools_list_is_the_agent_task_intersection() -> None:
    listed = _listed(_CONSULTANT)
    assert "confluence.page.search" in listed, listed
    assert listed <= _declared_capabilities(), listed - _declared_capabilities()
    # Each listed tool is allowed by the full five-factor evaluate().
    for capability in listed:
        binding = gateway_main.binding_registry.resolve(capability)
        decision = gateway_main.evaluate(
            store=gateway_main.policy_store, agents=gateway_main.agent_declarations, tool_name=capability,
            agent_name=AGENT, task_name=TASK, caller_groups=_CONSULTANT.groups,
            request_classification="C2", equivalent_names=binding.all_names(),
        )
        assert decision.allowed, (capability, decision.reason)


def test_tool_outside_the_task_declaration_is_refused() -> None:
    assert "confluence.page.create" not in _declared_capabilities()
    resp = _rpc(_CONSULTANT, "tools/call", {"name": "confluence.page.create", "arguments": {}})
    result = resp.json()["result"]
    assert result["isError"] is True, result
    assert "not exposed" in result["content"][0]["text"], result


def test_caller_without_the_group_sees_nothing_and_is_refused() -> None:
    assert "confluence.page.search" not in _listed(_ENTITLED_ONLY)
    resp = _rpc(_ENTITLED_ONLY, "tools/call", {"name": "confluence.page.search", "arguments": {"query": "x"}})
    result = resp.json()["result"]
    assert result["isError"] is True, result
    assert "denied" in result["content"][0]["text"], result


def test_without_agent_the_lightspeed_ceiling_applies() -> None:
    listed = _listed(_CONSULTANT, agent="")
    assert listed <= set(mcp_frontdoor.frontdoor_capabilities()), listed


def test_caller_not_entitled_to_the_agent_is_refused() -> None:
    assert "agent_tekos" not in _FINANCE.groups
    assert _rpc(_FINANCE, "tools/list").status_code == 403
    resp = _rpc(_FINANCE, "tools/call", {"name": "confluence.page.search", "arguments": {"query": "x"}})
    assert resp.status_code == 403, resp.text


def test_unknown_agent_gets_an_empty_surface() -> None:
    assert _listed(_CONSULTANT, agent="no-such-agent") == set()


def test_openshift_identity_cannot_declare_an_agent() -> None:
    resp = _rpc(_OPENSHIFT, "tools/list")
    assert resp.status_code == 403, resp.text


TESTS = [
    test_tools_list_is_the_agent_task_intersection,
    test_tool_outside_the_task_declaration_is_refused,
    test_caller_without_the_group_sees_nothing_and_is_refused,
    test_without_agent_the_lightspeed_ceiling_applies,
    test_caller_not_entitled_to_the_agent_is_refused,
    test_unknown_agent_gets_an_empty_surface,
    test_openshift_identity_cannot_declare_an_agent,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc!r}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
