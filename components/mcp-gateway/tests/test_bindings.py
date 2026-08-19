"""ADR-0116 tests for app/bindings.py and the alias-aware policy path:

- the real repository registry (platform/bindings/tools/tool-bindings.yaml)
  loads, and every canonical capability + legacy alias resolves to the same
  binding;
- every name the real tool-policy answers to (legacy tool + capability) has
  exactly one binding (the startup/readiness coverage rule);
- unknown names fail closed (resolve -> None; downstream.invoke -> 502
  without contacting any backend);
- malformed registries (duplicate capability, in-process without handler,
  streamable-http without endpoint) are rejected at load;
- policy evaluation treats a capability and its aliases as one tool
  (an OKF bundle declaring the legacy name authorizes the canonical ID).

Run from the component directory:

    python3 tests/test_bindings.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(COMPONENT_DIR))
sys.path.insert(0, COMPONENT_DIR)

from app import downstream  # noqa: E402
from app.bindings import Binding, BindingRegistry  # noqa: E402
from app.policy import PolicyStore, evaluate  # noqa: E402

REAL_BINDINGS_PATH = os.path.join(REPO_ROOT, "platform", "bindings", "tools", "tool-bindings.yaml")
REAL_POLICY_PATH = os.path.join(REPO_ROOT, "policies", "tools", "tool-policy.yaml")
REAL_CLASSIFICATION_PATH = os.path.join(
    REPO_ROOT, "policies", "data-classification", "classification.yaml"
)


def _registry_from(text: str) -> BindingRegistry:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        return BindingRegistry(path=path)
    finally:
        os.unlink(path)


def test_real_registry_loads_and_aliases_resolve() -> None:
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    assert registry.loaded, registry.load_error
    for binding in [registry.resolve(c) for c in registry.capabilities()]:
        assert binding is not None
        for alias in binding.aliases:
            assert registry.resolve(alias) is binding, (
                f"alias '{alias}' must resolve to the same binding as "
                f"'{binding.capability}'"
            )


def test_real_policy_names_are_fully_covered() -> None:
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    store = PolicyStore(
        tool_policy_path=REAL_POLICY_PATH, classification_path=REAL_CLASSIFICATION_PATH
    )
    assert store.loaded, store.load_error
    problems = registry.validate_policy_coverage(store.policy_names())
    assert problems == [], problems


def test_unknown_name_fails_closed() -> None:
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    assert registry.resolve("no.such.capability") is None
    assert registry.resolve("totally_unknown_tool") is None
    problems = registry.validate_policy_coverage(["no.such.capability"])
    assert len(problems) == 1


def test_sxa_legacy_capabilities_never_share_the_sales_namespace() -> None:
    """ADR-0206 (WP-23) write-path guard, binding-registry level: the
    `sales-db` server's data is legacy SXA, not current Salesforce, and a
    future real Salesforce write capability (WP-33) must never resolve to
    it. Proven two ways: (1) every capability this legacy server backs is
    namespaced `sxa.*`, never `sales.*` - the namespace stays fully vacant
    until WP-33 defines it against a different backend; (2) resolving any
    `sales.*` name today (including one that would be a natural write
    capability name) fails closed rather than silently matching a sxa.*
    entry or an alias."""
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    assert registry.loaded, registry.load_error

    sxa_capabilities = [c for c in registry.capabilities() if c.startswith("sxa.")]
    assert sxa_capabilities, "expected at least one sxa.* capability"
    for capability in sxa_capabilities:
        binding = registry.resolve(capability)
        assert binding.backend == "sales-db", (
            f"{capability} unexpectedly bound to backend '{binding.backend}', "
            "not the legacy sales-db server"
        )

    for probe in ("sales.customer.read", "sales.opportunity.write", "sales.opportunity.create"):
        assert registry.resolve(probe) is None, (
            f"'{probe}' unexpectedly resolved - the sales.* namespace must stay "
            "vacant (reserved for WP-33's real Salesforce capabilities) until a "
            "binding for it is explicitly authored"
        )


def test_duplicate_capability_rejected_at_load() -> None:
    registry = _registry_from(
        """
bindings:
  - capability: a.b.read
    backend: x
    transport: in-process
    handler: web_search
    provider_tool: t1
    auth_mode: service-identity
  - capability: a.b.read
    backend: y
    transport: in-process
    handler: web_search
    provider_tool: t2
    auth_mode: service-identity
"""
    )
    assert not registry.loaded
    assert "duplicate" in (registry.load_error or "")


def test_malformed_entries_rejected_at_load() -> None:
    no_handler = _registry_from(
        """
bindings:
  - capability: a.b.read
    backend: x
    transport: in-process
    provider_tool: t1
    auth_mode: service-identity
"""
    )
    assert not no_handler.loaded and "handler" in (no_handler.load_error or "")

    no_endpoint = _registry_from(
        """
bindings:
  - capability: a.b.read
    backend: x
    transport: streamable-http
    provider_tool: t1
    auth_mode: service-identity
"""
    )
    assert not no_endpoint.loaded and "endpoint" in (no_endpoint.load_error or "")


def test_binding_without_auth_mode_fails_to_load() -> None:
    """ADR-0208: auth_mode is required, never defaulted or inferred."""
    missing = _registry_from(
        """
bindings:
  - capability: a.b.read
    backend: x
    transport: in-process
    handler: web_search
    provider_tool: t1
"""
    )
    assert not missing.loaded
    assert "auth_mode" in (missing.load_error or "")

    unknown = _registry_from(
        """
bindings:
  - capability: a.b.read
    backend: x
    transport: in-process
    handler: web_search
    provider_tool: t1
    auth_mode: not-a-real-mode
"""
    )
    assert not unknown.loaded
    assert "auth_mode" in (unknown.load_error or "")


def test_backends_default_endpoint_used_when_entry_omits_its_own() -> None:
    """ADR-0119: an entry may omit `endpoint:` when its `backend` has a
    default in the top-level `backends:` map; a per-entry `endpoint:`
    still wins when both are present."""
    registry = _registry_from(
        """
backends:
  x:
    env: TEST_X_MCP_URL
    default: "http://x-mcp.zuno-ai-run.svc:8000"
    path: /mcp

bindings:
  - capability: a.b.read
    backend: x
    transport: streamable-http
    provider_tool: t1
    auth_mode: service-identity
  - capability: a.c.read
    backend: x
    transport: streamable-http
    provider_tool: t2
    auth_mode: service-identity
    endpoint:
      env: TEST_X_OVERRIDE_MCP_URL
      default: "http://x-override-mcp.zuno-ai-run.svc:9000"
      path: /mcp
"""
    )
    assert registry.loaded, registry.load_error
    inherited = registry.resolve("a.b.read")
    assert inherited.endpoint_url() == "http://x-mcp.zuno-ai-run.svc:8000/mcp"
    overridden = registry.resolve("a.c.read")
    assert overridden.endpoint_url() == "http://x-override-mcp.zuno-ai-run.svc:9000/mcp"


def test_streamable_http_without_endpoint_or_backend_default_rejected_at_load() -> None:
    registry = _registry_from(
        """
bindings:
  - capability: a.b.read
    backend: unbacked
    transport: streamable-http
    provider_tool: t1
    auth_mode: service-identity
"""
    )
    assert not registry.loaded
    assert "endpoint" in (registry.load_error or "")


def test_invoke_without_binding_is_deterministic_502() -> None:
    async def run() -> None:
        try:
            await downstream.invoke(None, "anything", {}, "sub", "token")
            raise AssertionError("expected DownstreamError")
        except downstream.DownstreamError as exc:
            assert exc.status_code == 502
            assert "no backend binding" in exc.message

    asyncio.run(run())


def test_invoke_with_unknown_handler_is_deterministic_502() -> None:
    binding = Binding(
        capability="a.b.read",
        backend="x",
        transport="in-process",
        provider_tool="t",
        auth_mode="service-identity",
        handler="not_a_real_handler",
    )

    async def run() -> None:
        try:
            await downstream.invoke(binding, "a.b.read", {}, "sub", "token")
            raise AssertionError("expected DownstreamError")
        except downstream.DownstreamError as exc:
            assert exc.status_code == 502
            assert "unknown in-process handler" in exc.message

    asyncio.run(run())


class _StubAgent:
    """Duck-typed stand-in for app/agent_declarations.py's agent record: a
    bundle that still declares only the LEGACY tool name."""

    def __init__(self) -> None:
        self.tasks = {"some-task": ["search_confluence"]}

    def declared_tools(self):
        return ["search_confluence"]


class _StubAgentStore:
    load_error = None

    def get(self, name):
        return _StubAgent() if name == "tekos" else None


def test_evaluate_treats_capability_and_alias_as_one_tool() -> None:
    store = PolicyStore(
        tool_policy_path=REAL_POLICY_PATH, classification_path=REAL_CLASSIFICATION_PATH
    )
    # The real policy file indexes the entry under both names.
    assert store.get_tool("search_confluence") is store.get_tool("confluence.page.search")

    # Caller invokes by canonical ID; the OKF bundle declares the legacy
    # alias only - the equivalence set makes them one tool (ADR-0116
    # migration rule: aliases are explicit, never inferred).
    decision = evaluate(
        store=store,
        agents=_StubAgentStore(),
        tool_name="confluence.page.search",
        agent_name="tekos",
        task_name="some-task",
        caller_groups=["consultant"],
        request_classification="C2",
        equivalent_names=["confluence.page.search", "search_confluence"],
    )
    assert decision.allowed, decision.reason
    assert decision.mcp_server == "confluence"

    # Without the equivalence set (no binding would exist for this name),
    # the same request stays denied - nothing widened by default.
    denied = evaluate(
        store=store,
        agents=_StubAgentStore(),
        tool_name="confluence.page.search",
        agent_name="tekos",
        task_name="some-task",
        caller_groups=["consultant"],
        request_classification="C2",
    )
    assert not denied.allowed


TESTS = [
    test_real_registry_loads_and_aliases_resolve,
    test_real_policy_names_are_fully_covered,
    test_unknown_name_fails_closed,
    test_sxa_legacy_capabilities_never_share_the_sales_namespace,
    test_duplicate_capability_rejected_at_load,
    test_malformed_entries_rejected_at_load,
    test_binding_without_auth_mode_fails_to_load,
    test_backends_default_endpoint_used_when_entry_omits_its_own,
    test_streamable_http_without_endpoint_or_backend_default_rejected_at_load,
    test_invoke_without_binding_is_deterministic_502,
    test_invoke_with_unknown_handler_is_deterministic_502,
    test_evaluate_treats_capability_and_alias_as_one_tool,
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
