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


TESTS = [
    test_declared_adapter_is_resolved,
    test_undeclared_agent_task_returns_none,
    test_empty_agent_or_task_returns_none,
    test_malformed_entry_is_skipped_not_a_crash,
    test_missing_file_degrades_to_no_adapters_ever,
    test_reload_picks_up_a_changed_file,
    test_default_classification_is_c1,
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
