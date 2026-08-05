#!/usr/bin/env python3
"""ADR-0046 acceptance tests for rag-service's pure retrieval-metadata
logic: the deterministic product/version/ACL filter clause builder, the
staleness check, and the post-fusion language-boost/staleness-penalty
adjustment. These don't need a live database (unlike hybrid_search itself,
which does) - same "no live cluster" constraint and same
plain-function/no-pytest style as components/agent-runtime/tests/test_registry.py.

Run directly:

    cd components/rag-service && python3 tests/test_search_filters.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.search import (  # noqa: E402
    _LANGUAGE_BOOST,
    _STALE_PENALTY_FACTOR,
    _apply_soft_adjustments,
    _filter_clause,
    _is_stale,
)


def test_filter_clause_with_no_filters_still_enforces_acl() -> None:
    """ADR-0046 Security considerations: ACL enforcement is not optional -
    even with no product/version filter and no caller groups, the ACL
    clause must still be present (fail closed).
    """
    sql, params = _filter_clause(3, product=None, version=None, caller_groups=[])
    assert "acl_groups" in sql
    assert "metadata ->> 'product'" not in sql
    assert "metadata ->> 'version'" not in sql
    assert params == [[]]


def test_filter_clause_with_product_and_version_uses_sequential_placeholders() -> None:
    sql, params = _filter_clause(3, product="openshift-ai", version="3.5", caller_groups=["consultant"])
    assert "metadata ->> 'product' = $3" in sql
    assert "metadata ->> 'version' = $4" in sql
    assert "?| $5::text[]" in sql
    assert params == ["openshift-ai", "3.5", ["consultant"]]


def test_is_stale() -> None:
    assert _is_stale({"stale_after": "2020-01-01"}) is True
    assert _is_stale({"stale_after": "2999-01-01"}) is False
    assert _is_stale({}) is False
    assert _is_stale({"stale_after": "not-a-date"}) is False  # logs a warning, doesn't raise


def test_language_boost_reorders_a_near_tie() -> None:
    """ADR-0046: language is a soft preference. Two docs fused to the same
    score, one in the requested language - it must end up strictly ahead.
    """
    fused = {"en-doc": 0.05, "fr-doc": 0.05}
    docs_by_id = {
        "en-doc": {"language": "en", "stale": False},
        "fr-doc": {"language": "fr", "stale": False},
    }
    _apply_soft_adjustments(fused, docs_by_id, language="fr")
    assert fused["fr-doc"] == 0.05 + _LANGUAGE_BOOST
    assert fused["fr-doc"] > fused["en-doc"]


def test_stale_penalty_demotes_without_zeroing() -> None:
    fused = {"fresh": 0.05, "stale": 0.05}
    docs_by_id = {
        "fresh": {"language": None, "stale": False},
        "stale": {"language": None, "stale": True},
    }
    _apply_soft_adjustments(fused, docs_by_id, language=None)
    assert fused["stale"] == 0.05 * _STALE_PENALTY_FACTOR
    assert 0 < fused["stale"] < fused["fresh"]


TESTS = [
    test_filter_clause_with_no_filters_still_enforces_acl,
    test_filter_clause_with_product_and_version_uses_sequential_placeholders,
    test_is_stale,
    test_language_boost_reorders_a_near_tie,
    test_stale_penalty_demotes_without_zeroing,
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
