"""ADR-0524 clause 3 tests for app/mcp_frontdoor.py's tools/list construction:

- a tool-policy.yaml entry's `description` field propagates verbatim into
  the MCP `tools/list` response the front-door sends to a client (e.g.
  OpenShift Lightspeed);
- an entry with no `description` still falls back to the generic
  "Zuno platform capability ..." sentence (Track-B-not-yet-authored
  degradation, unchanged);
- aap.cluster.audit carries `readOnlyHint: false` (it launches a real AAP
  Job Template) while every other real front-door capability keeps
  `readOnlyHint: true` - live-caught 2026-09-09 alongside the missing-
  description bug this file's first two tests guard against.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_mcp_frontdoor.py
"""
from __future__ import annotations

import os
import sys
import tempfile

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(COMPONENT_DIR))
sys.path.insert(0, COMPONENT_DIR)

from app import mcp_frontdoor  # noqa: E402
from app.auth import CallerIdentity  # noqa: E402
from app.bindings import BindingRegistry  # noqa: E402
from app.policy import PolicyStore  # noqa: E402

REAL_BINDINGS_PATH = os.path.join(REPO_ROOT, "platform", "bindings", "tools", "tool-bindings.yaml")
REAL_POLICY_PATH = os.path.join(REPO_ROOT, "policies", "tools", "tool-policy.yaml")
REAL_CLASSIFICATION_PATH = os.path.join(
    REPO_ROOT, "policies", "data-classification", "classification.yaml"
)

_IDENTITY = CallerIdentity(
    sub="ai-ops-1", groups=["ocp-ai-ops", "lightspeed_readonly"], raw_claims={}, token="caller-jwt"
)


def _tmp_policy(text: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(text)
        return fh.name


def test_description_field_propagates_verbatim() -> None:
    policy_path = _tmp_policy(
        """
tools:
  - tool: aap.platform.audit
    capability: aap.platform.audit
    mcp_server: aap
    description: "Summarize AAP's own state. Read-only."
    min_classification: C2
    allowed_groups:
      - ocp-ai-ops
"""
    )
    try:
        store = PolicyStore(tool_policy_path=policy_path, classification_path=REAL_CLASSIFICATION_PATH)
        registry = BindingRegistry(path=REAL_BINDINGS_PATH)
        os.environ["MCP_FRONTDOOR_CAPABILITIES"] = "aap.platform.audit"
        try:
            tools = mcp_frontdoor.list_tools(
                policy_store=store, binding_registry=registry, identity=_IDENTITY, classification="C2"
            )
        finally:
            del os.environ["MCP_FRONTDOOR_CAPABILITIES"]
        assert len(tools) == 1, tools
        assert tools[0]["description"] == "Summarize AAP's own state. Read-only."
    finally:
        os.unlink(policy_path)


def test_missing_description_falls_back_to_generic_sentence() -> None:
    policy_path = _tmp_policy(
        """
tools:
  - tool: aap.platform.audit
    capability: aap.platform.audit
    mcp_server: aap
    min_classification: C2
    allowed_groups:
      - ocp-ai-ops
"""
    )
    try:
        store = PolicyStore(tool_policy_path=policy_path, classification_path=REAL_CLASSIFICATION_PATH)
        registry = BindingRegistry(path=REAL_BINDINGS_PATH)
        os.environ["MCP_FRONTDOOR_CAPABILITIES"] = "aap.platform.audit"
        try:
            tools = mcp_frontdoor.list_tools(
                policy_store=store, binding_registry=registry, identity=_IDENTITY, classification="C2"
            )
        finally:
            del os.environ["MCP_FRONTDOOR_CAPABILITIES"]
        assert len(tools) == 1, tools
        assert tools[0]["description"] == (
            "Zuno platform capability 'aap.platform.audit', served by the "
            "'aap' backend through the Zuno MCP Gateway."
        )
    finally:
        os.unlink(policy_path)


def test_real_frontdoor_capabilities_have_real_descriptions() -> None:
    """None of the 5 capabilities this repo actually exposes through the
    front-door (gitops/charts/mcp-gateway/values.yaml's
    lightspeed.frontdoorCapabilities) should still be carrying the generic
    fallback sentence - that was exactly the live bug."""
    store = PolicyStore(tool_policy_path=REAL_POLICY_PATH, classification_path=REAL_CLASSIFICATION_PATH)
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    assert store.loaded, store.load_error
    assert registry.loaded, registry.load_error

    real_capabilities = (
        "confluence.page.search",
        "confluence.page.read",
        "knowledge.tech.search",
        "aap.platform.audit",
        "aap.cluster.audit",
    )
    os.environ["MCP_FRONTDOOR_CAPABILITIES"] = ",".join(real_capabilities)
    try:
        tools = mcp_frontdoor.list_tools(
            policy_store=store, binding_registry=registry, identity=_IDENTITY, classification="C2"
        )
    finally:
        del os.environ["MCP_FRONTDOOR_CAPABILITIES"]

    by_name = {t["name"]: t for t in tools}
    assert set(by_name) == set(real_capabilities), by_name.keys()
    for name, tool in by_name.items():
        assert "Zuno platform capability" not in tool["description"], (
            f"'{name}' still has no real description in policies/tools/tool-policy.yaml"
        )


def test_cluster_audit_is_not_read_only_others_are() -> None:
    store = PolicyStore(tool_policy_path=REAL_POLICY_PATH, classification_path=REAL_CLASSIFICATION_PATH)
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    real_capabilities = (
        "confluence.page.search",
        "confluence.page.read",
        "knowledge.tech.search",
        "aap.platform.audit",
        "aap.cluster.audit",
    )
    os.environ["MCP_FRONTDOOR_CAPABILITIES"] = ",".join(real_capabilities)
    try:
        tools = mcp_frontdoor.list_tools(
            policy_store=store, binding_registry=registry, identity=_IDENTITY, classification="C2"
        )
    finally:
        del os.environ["MCP_FRONTDOOR_CAPABILITIES"]

    by_name = {t["name"]: t for t in tools}
    assert by_name["aap.cluster.audit"]["annotations"]["readOnlyHint"] is False
    for name in ("confluence.page.search", "confluence.page.read", "knowledge.tech.search", "aap.platform.audit"):
        assert by_name[name]["annotations"]["readOnlyHint"] is True, name


TESTS = [
    test_description_field_propagates_verbatim,
    test_missing_description_falls_back_to_generic_sentence,
    test_real_frontdoor_capabilities_have_real_descriptions,
    test_cluster_audit_is_not_read_only_others_are,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
