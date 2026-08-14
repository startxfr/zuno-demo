#!/usr/bin/env python3
"""ADR-0202/ADR-0203 acceptance tests for rag-service's domain/technology
filtering - the defense-in-depth layer under Agent Runtime's
evaluate_knowledge() (components/agent-runtime/app/knowledge.py). Same
no-live-database, plain-function style as tests/test_search_filters.py.

Covers ADR-0203's fifth acceptance bullet composed with the domain filter
this WP adds ("ACL-restricted chunks remain invisible ... " together with
domain scoping), and ADR-0202's "a technical query can filter one canonical
technology across both official web and Confluence chunks".

Run directly:

    cd components/rag-service && python3 tests/test_domain_filter.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.ogx_provider import _passes_filters, _row_to_result  # noqa: E402
from app.search import _filter_clause, _row_to_doc  # noqa: E402


def test_no_domains_applies_no_domain_clause() -> None:
    """Additive/optional: an absent domains list is legacy pre-ADR-0202
    behavior, not "match nothing"."""
    sql, params = _filter_clause(3, product=None, version=None, caller_groups=[], domains=None)
    assert "'domain'" not in sql
    assert params == [[]]


def test_domains_present_scopes_the_query_and_treats_untagged_rows_as_tech() -> None:
    sql, params = _filter_clause(3, product=None, version=None, caller_groups=["consultant"], domains=["knowledge.tech"])
    assert "metadata ->> 'domain' = ANY($3::text[])" in sql
    assert "NOT (metadata ? 'domain') AND 'knowledge.tech' = ANY($3::text[])" in sql
    assert "?| $4::text[]" in sql  # ACL clause moves to the next placeholder
    assert params == [["knowledge.tech"], ["consultant"]]


def test_technology_filter_is_a_hard_filter_like_product_version() -> None:
    sql, params = _filter_clause(3, product=None, version=None, caller_groups=[], technology="satellite")
    assert "metadata ->> 'technology' = $3" in sql
    assert params == ["satellite", []]


def test_domain_and_technology_and_acl_compose() -> None:
    sql, params = _filter_clause(
        3, product=None, version=None, caller_groups=["board"], domains=["knowledge.tech"], technology="openshift"
    )
    assert "metadata ->> 'technology' = $3" in sql
    assert "metadata ->> 'domain' = ANY($4::text[])" in sql
    assert "?| $5::text[]" in sql
    assert params == ["openshift", ["knowledge.tech"], ["board"]]


def test_row_to_doc_defaults_untagged_rows_to_knowledge_tech() -> None:
    doc = _row_to_doc({"id": 1, "source": "s", "title": "t", "content": "c", "metadata": {}})
    assert doc["domain"] == "knowledge.tech"


def test_row_to_doc_surfaces_explicit_domain() -> None:
    doc = _row_to_doc(
        {"id": 1, "source": "s", "title": "t", "content": "c", "metadata": {"domain": "knowledge.sales"}}
    )
    assert doc["domain"] == "knowledge.sales"


def test_ogx_passes_filters_domain_scoping_matches_sql_semantics() -> None:
    """The Python mirror in app/ogx_provider.py must agree with the SQL
    clause above: an untagged doc counts as knowledge.tech, a tagged doc
    outside the requested set is excluded."""
    untagged = {"acl_groups": []}
    assert _passes_filters(untagged, None, None, [], domains=["knowledge.tech"]) is True
    assert _passes_filters(untagged, None, None, [], domains=["knowledge.sales"]) is False

    tagged_sales = {"domain": "knowledge.sales", "acl_groups": []}
    assert _passes_filters(tagged_sales, None, None, [], domains=["knowledge.sales"]) is True
    assert _passes_filters(tagged_sales, None, None, [], domains=["knowledge.tech"]) is False


def test_ogx_row_to_result_defaults_untagged_rows_to_knowledge_tech() -> None:
    doc = _row_to_result({"file_id": "1", "content": [], "attributes": {}})
    assert doc["domain"] == "knowledge.tech"


TESTS = [
    test_no_domains_applies_no_domain_clause,
    test_domains_present_scopes_the_query_and_treats_untagged_rows_as_tech,
    test_technology_filter_is_a_hard_filter_like_product_version,
    test_domain_and_technology_and_acl_compose,
    test_row_to_doc_defaults_untagged_rows_to_knowledge_tech,
    test_row_to_doc_surfaces_explicit_domain,
    test_ogx_passes_filters_domain_scoping_matches_sql_semantics,
    test_ogx_row_to_result_defaults_untagged_rows_to_knowledge_tech,
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
