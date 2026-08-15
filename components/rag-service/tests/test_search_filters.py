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

import datetime as _dt

from app.search import (  # noqa: E402
    _FRESHNESS_UNTRUSTED_PENALTY_FACTOR,
    _LANGUAGE_BOOST,
    _PROVENANCE_UNVERIFIABLE_WEIGHT,
    _STALE_PENALTY_FACTOR,
    _apply_soft_adjustments,
    _filter_clause,
    _freshness_decay_factor,
    _is_freshness_untrusted,
    _is_stale,
    _row_to_doc,
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


def _row(metadata: dict, doc_id: str = "1") -> dict:
    return {
        "id": doc_id, "source": f"https://example.test/{doc_id}", "title": "Doc",
        "content": "some content", "metadata": metadata,
    }


def test_fresh_beats_stale_at_equal_similarity() -> None:
    """WP-24/ADR-0205 acceptance: two chunks fused to the same base score,
    one past its stale_after and one not - the fresh one must rank
    strictly ahead once trust scoring is applied, real metadata this time
    (not the flag-only synthetic fixtures above)."""
    fresh = _row_to_doc(_row({"stale_after": "2999-01-01", "indexed_at": "2026-08-01T00:00:00Z"}, "fresh"))
    stale = _row_to_doc(_row({"stale_after": "2020-01-01", "indexed_at": "2026-08-01T00:00:00Z"}, "stale"))
    fused = {"fresh": 0.05, "stale": 0.05}
    docs_by_id = {"fresh": fresh, "stale": stale}
    _apply_soft_adjustments(fused, docs_by_id, language=None)
    assert fused["stale"] < fused["fresh"]
    assert fused["stale"] > 0


def test_missing_freshness_metadata_ranks_last_and_flags() -> None:
    """A chunk in an operational domain with neither indexed_at nor
    stale_after (pre-dates WP-24's ingestion enforcement) must be flagged
    freshness_untrusted and ranked well below an equally-scored chunk that
    does carry freshness metadata - never dropped, just de-prioritized."""
    known = _row_to_doc(_row({"indexed_at": "2026-08-01T00:00:00Z"}, "known"))
    unknown = _row_to_doc(_row({}, "unknown"))
    assert unknown["freshness_untrusted"] is True
    assert known["freshness_untrusted"] is False
    fused = {"known": 0.05, "unknown": 0.05}
    docs_by_id = {"known": known, "unknown": unknown}
    _apply_soft_adjustments(fused, docs_by_id, language=None)
    assert fused["unknown"] < fused["known"]
    assert fused["unknown"] == 0.05 * _FRESHNESS_UNTRUSTED_PENALTY_FACTOR


def test_sxa_legacy_is_exempt_from_the_freshness_untrusted_flag() -> None:
    assert _is_freshness_untrusted("knowledge.sxa-legacy", {}) is False
    assert _is_freshness_untrusted("knowledge.tech", {}) is True
    assert _is_freshness_untrusted("knowledge.tech", {"stale_after": "2999-01-01"}) is False


def test_freshness_decay_worsens_the_longer_a_chunk_has_been_stale() -> None:
    today = _dt.date.today()
    just_stale = (today - _dt.timedelta(days=1)).isoformat()
    long_stale = (today - _dt.timedelta(days=365)).isoformat()
    just_factor = _freshness_decay_factor(True, {"stale_after": just_stale})
    long_factor = _freshness_decay_factor(True, {"stale_after": long_stale})
    assert 0 < long_factor < just_factor <= _STALE_PENALTY_FACTOR


def test_provenance_weight_prefers_a_real_url_over_a_fixture_marker() -> None:
    # indexed_at set on both so neither trips the freshness_untrusted
    # penalty - isolating the provenance-weight effect being tested here.
    url_doc = _row_to_doc(_row(
        {"provenance": "https://docs.example.test/page", "indexed_at": "2026-08-01T00:00:00Z"}, "url"
    ))
    fixture_doc = _row_to_doc(_row(
        {"provenance": "zuno-demo-fixture", "indexed_at": "2026-08-01T00:00:00Z"}, "fixture"
    ))
    fused = {"url": 0.05, "fixture": 0.05}
    docs_by_id = {"url": url_doc, "fixture": fixture_doc}
    _apply_soft_adjustments(fused, docs_by_id, language=None)
    assert fused["fixture"] == 0.05 * _PROVENANCE_UNVERIFIABLE_WEIGHT
    assert fused["fixture"] < fused["url"]


TESTS = [
    test_filter_clause_with_no_filters_still_enforces_acl,
    test_filter_clause_with_product_and_version_uses_sequential_placeholders,
    test_is_stale,
    test_language_boost_reorders_a_near_tie,
    test_stale_penalty_demotes_without_zeroing,
    test_fresh_beats_stale_at_equal_similarity,
    test_missing_freshness_metadata_ranks_last_and_flags,
    test_sxa_legacy_is_exempt_from_the_freshness_untrusted_flag,
    test_freshness_decay_worsens_the_longer_a_chunk_has_been_stale,
    test_provenance_weight_prefers_a_real_url_over_a_fixture_marker,
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
