"""ADR-0340 (WP-32) tests: the `cdp` role's scoped-capability pattern -
Workday's self/any read/write split and the *.self.* server-side
ownership check (app/main.py:_self_scope_denial_reason).

No real agent declares a workday.* capability yet (Workday has no live
backend - see policies/tools/tool-policy.yaml's own comment on this), so
the group/classification/subject-field intersection is tested directly
against the real policy file (app/policy.py:evaluate(), same
real-registry pattern tests/test_bindings.py uses) rather than through the
full HTTP endpoint with a fixture agent bundle - there is no legitimate
fixture agent to invent here that wouldn't misrepresent which agents
actually use Workday (none do yet).

Run directly:

    cd components/mcp-gateway && python3 tests/test_workday_ownership.py
"""
from __future__ import annotations

import os
import sys

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(COMPONENT_DIR))

REAL_BINDINGS_PATH = os.path.join(REPO_ROOT, "platform", "bindings", "tools", "tool-bindings.yaml")
REAL_POLICY_PATH = os.path.join(REPO_ROOT, "policies", "tools", "tool-policy.yaml")
REAL_CLASSIFICATION_PATH = os.path.join(
    REPO_ROOT, "policies", "data-classification", "classification.yaml"
)

# app.main constructs module-level BindingRegistry()/PolicyStore() singletons
# at import time (default /app/... paths, the in-image location) - point
# them at the real repo files first, same pattern
# tests/test_auth_mode_enforcement.py uses, even though this file's own
# tests use explicit paths throughout and never touch those singletons.
os.environ.setdefault("TOOL_BINDINGS_PATH", REAL_BINDINGS_PATH)
os.environ.setdefault("TOOL_POLICY_PATH", REAL_POLICY_PATH)
os.environ.setdefault("DATA_CLASSIFICATION_PATH", REAL_CLASSIFICATION_PATH)
os.environ.setdefault("AGENTS_DIR", os.path.join(REPO_ROOT, "agents"))

sys.path.insert(0, COMPONENT_DIR)

from app.bindings import BindingRegistry  # noqa: E402
from app.main import _self_scope_denial_reason  # noqa: E402
from app.policy import PolicyDecision, PolicyStore  # noqa: E402


def _store() -> PolicyStore:
    store = PolicyStore(tool_policy_path=REAL_POLICY_PATH, classification_path=REAL_CLASSIFICATION_PATH)
    assert store.loaded, store.load_error
    return store


def test_workday_capabilities_resolve_to_provider_delegated_bindings() -> None:
    """No live Workday backend exists - every entry fails closed at the
    auth_mode dispatch (501), never reaching a downstream call."""
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    assert registry.loaded, registry.load_error
    for capability in (
        "workday.profile.self.read",
        "workday.profile.self.update",
        "workday.profile.any.read",
    ):
        binding = registry.resolve(capability)
        assert binding is not None, capability
        assert binding.auth_mode == "provider-delegated"


def test_self_read_declares_the_subject_field_and_allows_consultant_and_cdp() -> None:
    store = _store()
    entry = store.get_tool("workday.profile.self.read")
    assert entry is not None
    assert entry.subject_field == "employee_id"
    assert set(entry.allowed_groups) == {"consultant", "cdp"}


def test_self_update_declares_the_subject_field_but_excludes_cdp() -> None:
    """ADR-0340 acceptance: cdp gets self.read but never self.update -
    "CDP receives read access ... CDP write access is not implied."."""
    store = _store()
    entry = store.get_tool("workday.profile.self.update")
    assert entry is not None
    assert entry.subject_field == "employee_id"
    assert entry.allowed_groups == ["consultant"]
    assert "cdp" not in entry.allowed_groups


def test_any_read_has_no_subject_field_and_is_cdp_only() -> None:
    """any.read has no self/any distinction to enforce at the argument
    level - group membership alone is the gate, same as every capability
    before this WP."""
    store = _store()
    entry = store.get_tool("workday.profile.any.read")
    assert entry is not None
    assert entry.subject_field is None
    assert entry.allowed_groups == ["cdp"]


def test_no_any_update_capability_exists() -> None:
    """ADR-0340: "any.update is not implied and must be a separately
    approved capability if ever introduced" - there is no
    workday.profile.any.update entry anywhere in the real policy file."""
    store = _store()
    assert store.get_tool("workday.profile.any.update") is None


def test_self_scope_denial_reason_allows_a_matching_subject() -> None:
    decision = PolicyDecision(allowed=True, reason="allowed", subject_field="employee_id")
    denial = _self_scope_denial_reason(decision, {"employee_id": "alice"}, "alice")
    assert denial is None


def test_self_scope_denial_reason_denies_a_mismatched_subject() -> None:
    decision = PolicyDecision(allowed=True, reason="allowed", subject_field="employee_id")
    denial = _self_scope_denial_reason(decision, {"employee_id": "bob"}, "alice")
    assert denial is not None
    assert "employee_id" in denial


def test_self_scope_denial_reason_denies_a_missing_argument() -> None:
    """A caller who simply omits the subject-identifying argument must be
    denied, not silently treated as "not applicable" - an absent value
    can never equal a real subject."""
    decision = PolicyDecision(allowed=True, reason="allowed", subject_field="employee_id")
    denial = _self_scope_denial_reason(decision, {}, "alice")
    assert denial is not None


def test_self_scope_denial_reason_is_a_no_op_when_no_subject_field_declared() -> None:
    """Every capability before this WP, and workday.profile.any.read
    itself, must never be affected by this check."""
    decision = PolicyDecision(allowed=True, reason="allowed", subject_field=None)
    denial = _self_scope_denial_reason(decision, {"anything": "goes"}, "alice")
    assert denial is None


TESTS = [
    test_workday_capabilities_resolve_to_provider_delegated_bindings,
    test_self_read_declares_the_subject_field_and_allows_consultant_and_cdp,
    test_self_update_declares_the_subject_field_but_excludes_cdp,
    test_any_read_has_no_subject_field_and_is_cdp_only,
    test_no_any_update_capability_exists,
    test_self_scope_denial_reason_allows_a_matching_subject,
    test_self_scope_denial_reason_denies_a_mismatched_subject,
    test_self_scope_denial_reason_denies_a_missing_argument,
    test_self_scope_denial_reason_is_a_no_op_when_no_subject_field_declared,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
