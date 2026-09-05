"""ADR-0303 (WP-39) tests for app/model_routing_policy.py: loading,
reload, and the fail-closed-per-entry behavior a malformed policy entry
must have (skipped and logged, never a startup crash for the whole
gateway). No cluster/network needed - pure file I/O against a temp YAML
file.

Run from this directory:

    python3 tests/test_model_routing_policy.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402

from app.model_routing_policy import ModelRoutingPolicy  # noqa: E402


def _write_policy(entries) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as fh:
        yaml.safe_dump({"adapters": entries}, fh)
    return path


def _write_policy_doc(doc) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as fh:
        yaml.safe_dump(doc, fh)
    return path


def test_declared_adapter_is_resolved() -> None:
    path = _write_policy([{"agent": "comage", "task": "check-deal-status", "adapter": "comage-lora", "classification": "C2"}])
    try:
        policy = ModelRoutingPolicy(path)
        decl = policy.adapter_for("comage", "check-deal-status")
        assert decl is not None
        assert decl.adapter == "comage-lora"
        assert decl.classification == "C2"
    finally:
        os.unlink(path)


def test_undeclared_agent_task_returns_none() -> None:
    path = _write_policy([{"agent": "comage", "task": "check-deal-status", "adapter": "comage-lora"}])
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.adapter_for("tekos", "answer-technical-question") is None
    finally:
        os.unlink(path)


def test_empty_agent_or_task_returns_none() -> None:
    path = _write_policy([{"agent": "comage", "task": "check-deal-status", "adapter": "comage-lora"}])
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.adapter_for("", "check-deal-status") is None
        assert policy.adapter_for("comage", "") is None
    finally:
        os.unlink(path)


def test_malformed_entry_is_skipped_not_a_crash() -> None:
    """A missing `adapter` key must not raise or take down the whole
    policy file - it's dropped, logged, and every OTHER valid entry still
    loads (fail-closed per entry, not per file)."""
    path = _write_policy([
        {"agent": "comage", "task": "check-deal-status"},  # missing adapter
        {"agent": "tekos", "task": "answer-technical-question", "adapter": "tekos-lora"},
    ])
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.adapter_for("comage", "check-deal-status") is None
        decl = policy.adapter_for("tekos", "answer-technical-question")
        assert decl is not None and decl.adapter == "tekos-lora"
    finally:
        os.unlink(path)


def test_missing_file_degrades_to_no_adapters_ever() -> None:
    policy = ModelRoutingPolicy("/nonexistent/model-routing-policy.yaml")
    assert policy.adapter_for("comage", "check-deal-status") is None


def test_reload_picks_up_a_changed_file() -> None:
    path = _write_policy([{"agent": "comage", "task": "check-deal-status", "adapter": "comage-lora-v1"}])
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.adapter_for("comage", "check-deal-status").adapter == "comage-lora-v1"

        with open(path, "w") as fh:
            yaml.safe_dump({"adapters": [{"agent": "comage", "task": "check-deal-status", "adapter": "comage-lora-v2"}]}, fh)
        policy.reload()
        assert policy.adapter_for("comage", "check-deal-status").adapter == "comage-lora-v2"
    finally:
        os.unlink(path)


def test_default_classification_is_c1() -> None:
    path = _write_policy([{"agent": "tekos", "task": "answer-technical-question", "adapter": "tekos-lora"}])
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.adapter_for("tekos", "answer-technical-question").classification == "C1"
    finally:
        os.unlink(path)


# --- ADR-0412: preferences ------------------------------------------------


def test_preference_is_resolved_in_order() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local-gpt-oss", "local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("arkos", "draft-architecture-testimonial") == ["local-gpt-oss", "local"]
    finally:
        os.unlink(path)


def test_preference_absent_or_empty_key_returns_none() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local-gpt-oss"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("tekos", "answer-technical-question") is None
        assert policy.preference_for("", "draft-architecture-testimonial") is None
        assert policy.preference_for("arkos", "") is None
    finally:
        os.unlink(path)


def test_malformed_preference_is_skipped_valid_ones_load() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "comage", "task": "compare-historical-deals"},  # missing prefer
        {"agent": "comage", "task": "check-deal-status", "prefer": "local-gpt-oss"},  # not a list
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local-gpt-oss", "local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("comage", "compare-historical-deals") is None
        assert policy.preference_for("comage", "check-deal-status") is None
        assert policy.preference_for("arkos", "draft-architecture-testimonial") == ["local-gpt-oss", "local"]
    finally:
        os.unlink(path)


def test_preference_returns_a_copy_not_the_loaded_list() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local-gpt-oss", "local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        first = policy.preference_for("arkos", "draft-architecture-testimonial")
        first.append("mutated")
        assert policy.preference_for("arkos", "draft-architecture-testimonial") == ["local-gpt-oss", "local"]
    finally:
        os.unlink(path)


def test_missing_file_degrades_to_no_preferences_either() -> None:
    policy = ModelRoutingPolicy("/nonexistent/model-routing-policy.yaml")
    assert policy.preference_for("arkos", "draft-architecture-testimonial") is None


def test_reload_picks_up_preference_changes() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("arkos", "draft-architecture-testimonial") == ["local"]
        with open(path, "w") as fh:
            yaml.safe_dump({"preferences": [
                {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local-gpt-oss", "local"]},
            ]}, fh)
        policy.reload()
        assert policy.preference_for("arkos", "draft-architecture-testimonial") == ["local-gpt-oss", "local"]
    finally:
        os.unlink(path)


# --- ADR-0417: strict preferences -----------------------------------------


def test_strict_defaults_false() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local-gpt-oss"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.strict_for("arkos", "draft-architecture-testimonial") is False
    finally:
        os.unlink(path)


def test_strict_true_is_resolved() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "write-code", "prefer": ["mistral-codestral"], "strict": True},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.strict_for("arkos", "write-code") is True
        assert policy.preference_for("arkos", "write-code") == ["mistral-codestral"]
    finally:
        os.unlink(path)


def test_strict_absent_agent_task_returns_false() -> None:
    policy = ModelRoutingPolicy("/nonexistent/model-routing-policy.yaml")
    assert policy.strict_for("arkos", "write-code") is False


# --- ADR-0419: preferred/fallback split ------------------------------------


def test_preferred_and_fallback_concatenate_in_order() -> None:
    path = _write_policy_doc({"preferences": [
        {
            "agent": "tekos", "task": "answer-technical-question",
            "preferred": ["local-gpt-oss", "local", "ovhcloud-gpt-oss-120b"],
            "fallback": ["openai", "gemini", "anthropic", "mistral"],
        },
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("tekos", "answer-technical-question") == [
            "local-gpt-oss", "local", "ovhcloud-gpt-oss-120b", "openai", "gemini", "anthropic", "mistral",
        ]
    finally:
        os.unlink(path)


def test_preferred_and_fallback_is_byte_identical_to_an_equivalent_flat_prefer() -> None:
    """The whole point of the schema split (ADR-0419): preferred+fallback
    must produce the exact same resolved list a single prefer: with the
    same names in the same order would - a pure expressiveness change,
    not a new computation."""
    flat_path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["a", "b", "c"]},
    ]})
    split_path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "preferred": ["a", "b"], "fallback": ["c"]},
    ]})
    try:
        flat = ModelRoutingPolicy(flat_path).preference_for("arkos", "draft-architecture-testimonial")
        split = ModelRoutingPolicy(split_path).preference_for("arkos", "draft-architecture-testimonial")
        assert flat == split == ["a", "b", "c"]
    finally:
        os.unlink(flat_path)
        os.unlink(split_path)


def test_preferred_only_with_no_fallback_key() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "write-code", "preferred": ["mistral-codestral"], "strict": True},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("arkos", "write-code") == ["mistral-codestral"]
        assert policy.strict_for("arkos", "write-code") is True
    finally:
        os.unlink(path)


def test_fallback_only_with_no_preferred_key() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "tekos", "task": "find-relevant-docs", "fallback": ["openai", "anthropic"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("tekos", "find-relevant-docs") == ["openai", "anthropic"]
    finally:
        os.unlink(path)


def test_preferred_fallback_present_but_both_empty_is_malformed() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "tekos", "task": "check-my-drive-docs", "preferred": [], "fallback": []},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("tekos", "check-my-drive-docs") is None
    finally:
        os.unlink(path)


def test_prefer_key_still_works_unchanged_alongside_new_schema_entries() -> None:
    """Backward compatibility: an untouched prefer: entry and a new
    preferred/fallback entry coexist in the same file, each resolved
    correctly."""
    path = _write_policy_doc({"preferences": [
        {"agent": "comage", "task": "compare-historical-deals", "prefer": ["local-gpt-oss", "local"]},
        {"agent": "tekos", "task": "answer-technical-question", "preferred": ["local-gpt-oss"], "fallback": ["local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.preference_for("comage", "compare-historical-deals") == ["local-gpt-oss", "local"]
        assert policy.preference_for("tekos", "answer-technical-question") == ["local-gpt-oss", "local"]
    finally:
        os.unlink(path)


# --- ADR-0550: per-task local_only_for classification tiers ---------------


def test_local_only_for_is_resolved_for_declared_classifications() -> None:
    path = _write_policy_doc({"preferences": [
        {
            "agent": "arkos", "task": "draft-architecture-testimonial",
            "prefer": ["ovhcloud-gpt-oss-120b", "local-gpt-oss", "local"],
            "local_only_for": ["C2", "C3"],
        },
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C1") is False
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C2") is True
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C3") is True
        # Case-insensitive, matching every other classification comparison
        # in this codebase (X-Zuno-Data-Classification is upper-cased too).
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "c2") is True
    finally:
        os.unlink(path)


def test_local_only_for_absent_defaults_false() -> None:
    """An (agent, task) with a preference entry but no local_only_for key
    must behave exactly as it did before ADR-0550 - no restriction."""
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "workshop-presentation", "prefer": ["ovhcloud-gpt-oss-120b", "local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.local_only_for_classification("arkos", "workshop-presentation", "C2") is False
    finally:
        os.unlink(path)


def test_local_only_for_does_not_leak_to_other_agents_or_tasks() -> None:
    """Regression guard for the exact incident this field exists to avoid:
    Comage/Cognos legitimately reach ovhcloud-gpt-oss-120b at C2 through
    their own (agent, task) entries - Arkos DAT's own local_only_for must
    never affect them."""
    path = _write_policy_doc({"preferences": [
        {
            "agent": "arkos", "task": "draft-architecture-testimonial",
            "prefer": ["ovhcloud-gpt-oss-120b", "local"], "local_only_for": ["C2", "C3"],
        },
        {"agent": "comage", "task": "compare-historical-deals", "prefer": ["ovhcloud-gpt-oss-120b", "local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C2") is True
        assert policy.local_only_for_classification("comage", "compare-historical-deals", "C2") is False
    finally:
        os.unlink(path)


def test_local_only_for_missing_file_or_agent_task_returns_false() -> None:
    policy = ModelRoutingPolicy("/nonexistent/model-routing-policy.yaml")
    assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C2") is False
    assert policy.local_only_for_classification("", "draft-architecture-testimonial", "C2") is False
    assert policy.local_only_for_classification("arkos", "", "C2") is False


def test_local_only_for_empty_list_is_treated_as_absent() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local"], "local_only_for": []},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C2") is False
    finally:
        os.unlink(path)


def test_local_only_for_reload_picks_up_changes() -> None:
    path = _write_policy_doc({"preferences": [
        {"agent": "arkos", "task": "draft-architecture-testimonial", "prefer": ["local"]},
    ]})
    try:
        policy = ModelRoutingPolicy(path)
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C2") is False
        with open(path, "w") as fh:
            yaml.safe_dump({"preferences": [
                {
                    "agent": "arkos", "task": "draft-architecture-testimonial",
                    "prefer": ["local"], "local_only_for": ["C2", "C3"],
                },
            ]}, fh)
        policy.reload()
        assert policy.local_only_for_classification("arkos", "draft-architecture-testimonial", "C2") is True
    finally:
        os.unlink(path)


TESTS = [
    test_declared_adapter_is_resolved,
    test_undeclared_agent_task_returns_none,
    test_empty_agent_or_task_returns_none,
    test_malformed_entry_is_skipped_not_a_crash,
    test_missing_file_degrades_to_no_adapters_ever,
    test_reload_picks_up_a_changed_file,
    test_default_classification_is_c1,
    test_preference_is_resolved_in_order,
    test_preference_absent_or_empty_key_returns_none,
    test_malformed_preference_is_skipped_valid_ones_load,
    test_preference_returns_a_copy_not_the_loaded_list,
    test_missing_file_degrades_to_no_preferences_either,
    test_reload_picks_up_preference_changes,
    test_strict_defaults_false,
    test_strict_true_is_resolved,
    test_strict_absent_agent_task_returns_false,
    test_preferred_and_fallback_concatenate_in_order,
    test_preferred_and_fallback_is_byte_identical_to_an_equivalent_flat_prefer,
    test_preferred_only_with_no_fallback_key,
    test_fallback_only_with_no_preferred_key,
    test_preferred_fallback_present_but_both_empty_is_malformed,
    test_prefer_key_still_works_unchanged_alongside_new_schema_entries,
    test_local_only_for_is_resolved_for_declared_classifications,
    test_local_only_for_absent_defaults_false,
    test_local_only_for_does_not_leak_to_other_agents_or_tasks,
    test_local_only_for_missing_file_or_agent_task_returns_false,
    test_local_only_for_empty_list_is_treated_as_absent,
    test_local_only_for_reload_picks_up_changes,
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
