#!/usr/bin/env python3
"""ADR-0204 tests for app/bindings.py's KnowledgeBindingRegistry: mirrors
components/mcp-gateway/tests/test_bindings.py's real-registry-plus-malformed
pattern for the tool-binding registry, applied to knowledge domains.

Run directly:

    cd components/rag-service && python3 tests/test_bindings.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.bindings import KnowledgeBindingRegistry  # noqa: E402

REAL_BINDINGS_PATH = _REPO_ROOT / "platform" / "bindings" / "knowledge" / "bindings.yaml"


def _registry_from(text: str) -> KnowledgeBindingRegistry:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        return KnowledgeBindingRegistry(path=path)
    finally:
        os.unlink(path)


def test_real_bindings_load_and_cover_every_repo_domain() -> None:
    registry = KnowledgeBindingRegistry(path=str(REAL_BINDINGS_PATH))
    assert registry.loaded, registry.load_error
    for domain in ("knowledge.tech", "knowledge.sales", "knowledge.sxa-legacy", "knowledge.adv"):
        binding = registry.resolve(domain)
        assert binding is not None, f"no binding for {domain}"
        assert binding.database_name
        assert binding.schema
        assert binding.credential_env_prefix


def test_real_tech_binding_points_at_rag_tech() -> None:
    """WP-21's specific cutover decision: knowledge.tech moves off the
    legacy shared 'zuno' database onto its own rag-tech database."""
    registry = KnowledgeBindingRegistry(path=str(REAL_BINDINGS_PATH))
    binding = registry.resolve("knowledge.tech")
    assert binding.database_name == "rag-tech"


def test_missing_bindings_file_fails_closed() -> None:
    registry = KnowledgeBindingRegistry(path="/no/such/file.yaml")
    assert not registry.loaded
    assert "not found" in (registry.load_error or "")
    assert registry.resolve("knowledge.tech") is None


def test_duplicate_domain_rejected_at_load() -> None:
    registry = _registry_from(
        "bindings:\n"
        "  - domain: knowledge.tech\n"
        "    database: {name: a, schema: rag, credential_env_prefix: A}\n"
        "  - domain: knowledge.tech\n"
        "    database: {name: b, schema: rag, credential_env_prefix: B}\n"
    )
    assert not registry.loaded
    assert "duplicate" in (registry.load_error or "")


def test_malformed_entry_missing_field_rejected_at_load() -> None:
    registry = _registry_from(
        "bindings:\n"
        "  - domain: knowledge.tech\n"
        "    database: {name: a, schema: rag}\n"  # missing credential_env_prefix
    )
    assert not registry.loaded
    assert "credential_env_prefix" in (registry.load_error or "")


def test_binding_exposes_credential_env_var_names() -> None:
    registry = _registry_from(
        "bindings:\n"
        "  - domain: knowledge.tech\n"
        "    database: {name: rag-tech, schema: rag, credential_env_prefix: RAGTECH}\n"
    )
    binding = registry.resolve("knowledge.tech")
    assert binding.pguser_env == "RAGTECH_PGUSER"
    assert binding.pgpassword_env == "RAGTECH_PGPASSWORD"


TESTS = [
    test_real_bindings_load_and_cover_every_repo_domain,
    test_real_tech_binding_points_at_rag_tech,
    test_missing_bindings_file_fails_closed,
    test_duplicate_domain_rejected_at_load,
    test_malformed_entry_missing_field_rejected_at_load,
    test_binding_exposes_credential_env_var_names,
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
