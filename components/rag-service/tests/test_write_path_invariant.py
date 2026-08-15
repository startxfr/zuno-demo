#!/usr/bin/env python3
"""WP-24 (ADR-0205) write-path invariant: "RAG stays write-free - every
mutation of a source system goes through a live tool capability, never
through indexed retrieval." A static check, not a live-database
assertion: this service's two retrieval providers (app/search.py,
app/ogx_provider.py) must never contain a SQL/HTTP write verb - if a
future change ever adds one, this test catches it at review time rather
than depending on a live database inspection to notice.

Deliberately excludes app/db.py (connection lifecycle, no queries) and
the schema-apply path (data/rag/schema/*.sql, gitops/charts/rag-service/
templates/job-schema-apply.yaml) - DDL/index maintenance against Zuno's
OWN index is not what this invariant is about; it is about never
mutating a SOURCE system (Confluence, Salesforce, ...) from a read path.

Run directly:

    cd components/rag-service && python3 tests/test_write_path_invariant.py
"""
from __future__ import annotations

import pathlib
import re

_APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"

_RETRIEVAL_ONLY_FILES = ("search.py", "ogx_provider.py")

# Whole-word, case-insensitive: SQL/HTTP mutation verbs that would
# indicate a write against whatever this file queries.
_WRITE_VERB_RE = re.compile(r"\b(insert|update|delete|drop|truncate|alter|create_page|update_page)\b", re.IGNORECASE)


def test_retrieval_providers_contain_no_write_verb() -> None:
    for filename in _RETRIEVAL_ONLY_FILES:
        path = _APP_DIR / filename
        text = path.read_text(encoding="utf-8")
        match = _WRITE_VERB_RE.search(text)
        assert match is None, (
            f"{path} contains a write verb ({match.group(0)!r}) - RAG retrieval must stay "
            "read-only (ADR-0205); mutations belong behind a live tool capability, never here"
        )


TESTS = [
    test_retrieval_providers_contain_no_write_verb,
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
    import sys

    sys.exit(main())
