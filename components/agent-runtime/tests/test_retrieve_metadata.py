#!/usr/bin/env python3
"""ADR-0046 acceptance tests: proves the question-level product/version
extraction, the soft French-language hint, and the classification
escalation across retrieved docs all behave as documented. Same
no-pytest/no-live-cluster style as tests/test_registry.py; importing
app.graph.nodes triggers the same real agents/tekos/ bundle load that
module does at import time (see that file), so this exercises the real
checked-in bundle, not a mock.

Run directly:

    cd components/agent-runtime && python3 tests/test_retrieve_metadata.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
# app.registry reads AGENTS_DIR as a module-level constant at import time
# (default /app/agents, the in-image path) - must be set before
# app.graph.nodes (which imports app.registry and eagerly constructs an
# AgentRegistry at its own module level) is ever imported in this process.
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
# Same timing constraint as AGENTS_DIR above - app.graph.nodes constructs a
# module-level KnowledgePolicyStore(KNOWLEDGE_POLICY_PATH) at import time
# (see that module), needed here so resolve_authorized_domains actually
# authorizes knowledge.tech instead of denying everything - same pattern
# tests/test_history.py and friends already use.
os.environ.setdefault("KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.graph import nodes as nodes_module  # noqa: E402
from app.graph.nodes import (  # noqa: E402
    _ANSWER_TASK,
    _TEKOS,
    _detect_language,
    _escalate,
    _extract_product_version,
    _make_retrieve_node,
)


def test_extracts_openshift_ai_version() -> None:
    """The exact ADR-0046 scenario: a user naming a specific product AND
    version must resolve to a deterministic (product, version) pair, not
    just a fuzzy match on "OpenShift".
    """
    product, version = _extract_product_version("How do I size GPUs for OpenShift AI 3.5?")
    assert (product, version) == ("openshift-ai", "3.5")


def test_extracts_openshift_ai_case_insensitively_and_rhoai_alias() -> None:
    assert _extract_product_version("what changed in RHOAI 2.16") == ("openshift-ai", "2.16")
    assert _extract_product_version("OPENSHIFT AI 3.5 servingruntime") == ("openshift-ai", "3.5")


def test_falls_back_to_bare_openshift_product() -> None:
    product, version = _extract_product_version("what's new in OpenShift 4.20 networking")
    assert (product, version) == ("openshift", "4.20")


def test_no_match_returns_none_none() -> None:
    assert _extract_product_version("how does pgvector hybrid search work") == (None, None)


def test_openshift_ai_pattern_takes_precedence_over_bare_openshift() -> None:
    """"OpenShift AI 3.5" must not be mistaken for a bare "OpenShift"
    mention with a stray version number nearby.
    """
    product, version = _extract_product_version("compare OpenShift AI 3.5 to OpenShift AI 2.16")
    assert product == "openshift-ai"
    assert version == "3.5"  # first match wins, deterministic


def test_retrieve_node_stops_filtering_by_the_broken_product_field() -> None:
    """Live-cluster-confirmed 2026-08-22 (tekos scenario 10 stuck at
    source_mode=none): rag_ingestion.py tags metadata.product with the raw
    per-source doc slug (e.g. "red-hat-openshift-ai-self-managed"), never
    the canonical value _extract_product_version returns - rag-service's
    product filter has no fallback for a miss (unlike technology's
    grandfather clause), so passing product= here silently zeroed every
    RAG result for any message this detection fires on. technology= (the
    same canonical value, the working, correct cross-source filter) must
    still be passed through unchanged."""
    captured: dict = {}

    async def fake_search(**kwargs):
        captured.update(kwargs)
        return []

    retrieve_node = _make_retrieve_node(_TEKOS, _ANSWER_TASK)
    saved_search = nodes_module.search
    nodes_module.search = fake_search
    try:
        asyncio.run(
            retrieve_node(
                {"message": "what's new in OpenShift 4.20 networking", "groups": ["consultant"], "errors": []}
            )
        )
    finally:
        nodes_module.search = saved_search

    assert captured.get("product") is None
    assert captured.get("technology") == "openshift"
    assert captured.get("version") == "4.20"


def test_detects_french_via_accented_characters() -> None:
    assert _detect_language("Comment configurer un ServingRuntime vLLM ?") == "fr"


def test_detects_french_via_stopword_without_accents() -> None:
    assert _detect_language("comment dimensionner un GPU") == "fr"


def test_english_returns_none_not_en() -> None:
    """None means "no preference" (a soft ranking boost is skipped
    entirely), not an explicit "en" hard-filter - see rag-service's
    app/search.py:_LANGUAGE_BOOST for why that distinction matters.
    """
    assert _detect_language("How do I configure a ServingRuntime for vLLM?") is None


def test_classification_escalates_to_the_highest_retrieved_doc() -> None:
    """ADR-0046 closing ADR-0034's documented gap: effective_classification
    must reflect the highest classification among retrieved docs, not a
    fixed C1 baseline - same escalate-never-downgrade rule
    app/graph/nodes.py:tool_call_node already used for Confluence.
    """
    classification = "C1"
    for doc_classification in ("C1", "C2", "C1"):
        classification = _escalate(classification, doc_classification)
    assert classification == "C2"

    # Never downgrades once escalated (mirrors tool_call_node's own rule).
    classification = _escalate(classification, "C1")
    assert classification == "C2"


TESTS = [
    test_extracts_openshift_ai_version,
    test_extracts_openshift_ai_case_insensitively_and_rhoai_alias,
    test_falls_back_to_bare_openshift_product,
    test_no_match_returns_none_none,
    test_openshift_ai_pattern_takes_precedence_over_bare_openshift,
    test_retrieve_node_stops_filtering_by_the_broken_product_field,
    test_detects_french_via_accented_characters,
    test_detects_french_via_stopword_without_accents,
    test_english_returns_none_not_en,
    test_classification_escalates_to_the_highest_retrieved_doc,
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
