"""ADR-0326 (WP-31) tests: Arkos's delegated Drive/Docs write -
`drive.document.create`/`drive.document.update`, added to the existing
in-process `drive` handler module (app/handlers/drive.py) rather than a
new standalone server. Covers the real registry resolution (binding +
policy, mirroring tests/test_bindings.py's own pattern) and the handler
functions' own demo-mode behavior.

Run from the component directory:

    python3 tests/test_drive_write_capabilities.py
"""
from __future__ import annotations

import asyncio
import os
import sys

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(COMPONENT_DIR))
sys.path.insert(0, COMPONENT_DIR)

from app import downstream  # noqa: E402
from app.bindings import BindingRegistry  # noqa: E402
from app.handlers import drive  # noqa: E402
from app.policy import PolicyStore  # noqa: E402

REAL_BINDINGS_PATH = os.path.join(REPO_ROOT, "platform", "bindings", "tools", "tool-bindings.yaml")
REAL_POLICY_PATH = os.path.join(REPO_ROOT, "policies", "tools", "tool-policy.yaml")
REAL_CLASSIFICATION_PATH = os.path.join(
    REPO_ROOT, "policies", "data-classification", "classification.yaml"
)


def test_drive_write_capabilities_resolve_to_delegated_user_bindings() -> None:
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    assert registry.loaded, registry.load_error
    for capability, handler_name in (
        ("drive.document.create", "drive_create"),
        ("drive.document.update", "drive_update"),
    ):
        binding = registry.resolve(capability)
        assert binding is not None, capability
        assert binding.transport == "in-process"
        assert binding.handler == handler_name
        assert binding.auth_mode == "delegated-user"


def test_drive_write_capabilities_have_policy_entries() -> None:
    registry = BindingRegistry(path=REAL_BINDINGS_PATH)
    store = PolicyStore(tool_policy_path=REAL_POLICY_PATH, classification_path=REAL_CLASSIFICATION_PATH)
    assert store.loaded, store.load_error
    problems = registry.validate_policy_coverage(store.policy_names())
    assert problems == [], problems
    for capability in ("drive.document.create", "drive.document.update"):
        assert capability in store.policy_names(), capability


def test_downstream_dispatches_each_handler_name_to_its_own_function() -> None:
    assert downstream.IN_PROCESS_HANDLERS["drive"] is drive.handle
    assert downstream.IN_PROCESS_HANDLERS["drive_create"] is drive.handle_create
    assert downstream.IN_PROCESS_HANDLERS["drive_update"] is drive.handle_update


def test_handle_create_returns_a_url_and_echoes_the_title() -> None:
    result = asyncio.run(
        drive.handle_create({"title": "DAT - Example", "content": "body text"}, "alice", delegated_token="t")
    )
    assert result["demo_mode"] is True
    assert result["title"] == "DAT - Example"
    assert result["url"].startswith("https://docs.google.com/document/d/")
    assert result["content_length"] == len("body text")


def test_handle_create_defaults_an_empty_title() -> None:
    result = asyncio.run(drive.handle_create({}, "alice", delegated_token="t"))
    assert result["title"] == "Untitled document"


def test_handle_update_requires_a_document_id() -> None:
    result = asyncio.run(drive.handle_update({"content": "new body"}, "alice", delegated_token="t"))
    assert result["updated"] is False
    assert "document_id" in result["reason"]


def test_handle_update_succeeds_with_a_document_id() -> None:
    result = asyncio.run(
        drive.handle_update({"document_id": "abc123", "content": "new body"}, "alice", delegated_token="t")
    )
    assert result["updated"] is True
    assert result["id"] == "abc123"
    assert "abc123" in result["url"]


TESTS = [
    test_drive_write_capabilities_resolve_to_delegated_user_bindings,
    test_drive_write_capabilities_have_policy_entries,
    test_downstream_dispatches_each_handler_name_to_its_own_function,
    test_handle_create_returns_a_url_and_echoes_the_title,
    test_handle_create_defaults_an_empty_title,
    test_handle_update_requires_a_document_id,
    test_handle_update_succeeds_with_a_document_id,
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
