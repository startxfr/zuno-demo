#!/usr/bin/env python3
"""ADR-0203 acceptance tests for app/knowledge.py: KnowledgePolicyStore's
fail-closed loading and evaluate_knowledge()'s intersection, mirroring
components/mcp-gateway/tests/test_bindings.py's real-registry-plus-malformed
pattern for the analogous ADR-0011 tool intersection.

Maps to ADR-0203's acceptance criteria (docs/adr/0203-enforce-knowledge-
authorization-as-policy-intersection.md):

  1. "An OKF task can declare allowed_knowledge independently from
     allowed_tools." -> test_allowed_knowledge_is_declared_independently_of_allowed_tools
  2. "A task that declares knowledge.sales cannot retrieve
     knowledge.sxa-legacy unless both the agent ceiling and platform/user
     policy also allow it." -> test_domain_outside_agent_ceiling_is_denied_even_if_task_requests_it,
     test_multiple_domains_are_evaluated_independently
  3. "A user with agent entitlement but without the required business role
     is denied." -> test_caller_without_required_group_is_denied
  4. "A user with the business role but without agent entitlement remains
     denied by the existing BFF/agent boundary." This is the ADR-0040
     agent-entitlement check (components/agent-bff/main.go,
     components/agent-frontend/internal/okf/okf.go matching the
     `agent_tekos` group) - unrelated to and unchanged by this module, so
     it is not retested here; evaluate_knowledge only ever sees callers who
     already cleared that boundary.
  5. "ACL-restricted chunks remain invisible to callers whose groups do not
     intersect acl_groups." -> unchanged rag-service mechanism, covered by
     components/rag-service/tests/test_search_filters.py and (composed with
     the domain filter this WP adds) test_domain_filter.py.

Run directly:

    cd components/agent-runtime && python3 tests/test_knowledge_policy.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.knowledge import KnowledgePolicyStore, evaluate_knowledge  # noqa: E402

REAL_KNOWLEDGE_POLICY_PATH = _REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml"


def _store_from(text: str) -> KnowledgePolicyStore:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        return KnowledgePolicyStore(path=path)
    finally:
        os.unlink(path)


def test_real_knowledge_policy_loads_and_covers_every_repo_domain() -> None:
    """Sanity check against the actual checked-in policy - every domain
    declared under knowledge/ (ADR-0202) must have a policy entry."""
    store = KnowledgePolicyStore(path=str(REAL_KNOWLEDGE_POLICY_PATH))
    assert store.loaded, store.load_error
    for domain in ("knowledge.tech", "knowledge.sales", "knowledge.sxa-legacy", "knowledge.adv"):
        entry = store.get(domain)
        assert entry is not None, f"no knowledge-policy.yaml entry for {domain}"
        assert entry.allowed_groups, f"{domain} has no allowed_groups"


def test_missing_policy_file_fails_closed() -> None:
    store = KnowledgePolicyStore(path="/no/such/file.yaml")
    assert not store.loaded
    assert "not found" in (store.load_error or "")

    decision = evaluate_knowledge(
        store=store,
        agent_declared=["knowledge.tech"],
        task_allowed=["knowledge.tech"],
        caller_groups=["consultant"],
    )
    assert decision.authorized_domains == []
    assert "knowledge policy unavailable" in decision.denied["knowledge.tech"]


def test_malformed_domains_shape_fails_closed() -> None:
    """`domains:` must be a mapping (matches
    platform/supply-chain/validate_okf_bundle.py's _known_knowledge_domains(),
    which reads it the same way) - a list is rejected at load, not silently
    misread as zero domains.
    """
    store = _store_from("domains:\n  - knowledge.tech\n  - knowledge.sales\n")
    assert not store.loaded
    assert "mapping" in (store.load_error or "")


def test_allowed_knowledge_is_declared_independently_of_allowed_tools() -> None:
    """ADR-0203 acceptance bullet 1: allowed_knowledge and allowed_tools are
    two separate fields evaluated by two separate intersections
    (evaluate_knowledge here, app/policy... - actually mcp-gateway's
    evaluate() - for tools). A task with tools but no knowledge domains (or
    vice versa) proves neither implies the other.
    """
    store = _store_from(
        "domains:\n"
        "  knowledge.tech:\n"
        "    allowed_groups: [consultant]\n"
    )
    # A task that declares knowledge but happens to have no tool-independent
    # bearing here - evaluate_knowledge never looks at allowed_tools at all.
    decision = evaluate_knowledge(
        store=store,
        agent_declared=["knowledge.tech"],
        task_allowed=["knowledge.tech"],
        caller_groups=["consultant"],
    )
    assert decision.authorized_domains == ["knowledge.tech"]

    # A task that declares no knowledge domains at all still evaluates
    # cleanly to "nothing authorized", independent of whatever allowed_tools
    # it might carry.
    empty_decision = evaluate_knowledge(
        store=store, agent_declared=["knowledge.tech"], task_allowed=[], caller_groups=["consultant"]
    )
    assert empty_decision.authorized_domains == []
    assert empty_decision.denied == {}


def test_domain_outside_agent_ceiling_is_denied_even_if_task_requests_it() -> None:
    """ADR-0203 acceptance bullet 2: a task cannot widen the agent's
    declared-knowledge ceiling, even when the domain would otherwise be
    policy-allowed for the caller's groups.
    """
    store = _store_from(
        "domains:\n"
        "  knowledge.sales:\n"
        "    allowed_groups: [sales]\n"
        "  knowledge.sxa-legacy:\n"
        "    allowed_groups: [sales, board]\n"
    )
    decision = evaluate_knowledge(
        store=store,
        agent_declared=["knowledge.sales"],  # ceiling narrower than the task below
        task_allowed=["knowledge.sales", "knowledge.sxa-legacy"],
        caller_groups=["sales", "board"],  # would pass policy for both
    )
    assert decision.authorized_domains == ["knowledge.sales"]
    assert "not in the agent's declared knowledge ceiling" in decision.denied["knowledge.sxa-legacy"]


def test_caller_without_required_group_is_denied() -> None:
    """ADR-0203 acceptance bullet 3: agent entitlement (ceiling) is not
    enough on its own - the caller's business-role group must also
    intersect the domain's allowed_groups.
    """
    store = _store_from(
        "domains:\n"
        "  knowledge.sxa-legacy:\n"
        "    allowed_groups: [sales, board]\n"
    )
    decision = evaluate_knowledge(
        store=store,
        agent_declared=["knowledge.sxa-legacy"],
        task_allowed=["knowledge.sxa-legacy"],
        caller_groups=["consultant"],  # entitled to the agent, wrong business role
    )
    assert decision.authorized_domains == []
    assert "do not intersect" in decision.denied["knowledge.sxa-legacy"]


def test_unknown_domain_fails_closed() -> None:
    store = _store_from("domains:\n  knowledge.tech:\n    allowed_groups: [consultant]\n")
    decision = evaluate_knowledge(
        store=store, agent_declared=["knowledge.bogus"], task_allowed=["knowledge.bogus"], caller_groups=["consultant"]
    )
    assert decision.authorized_domains == []
    assert "unknown domain" in decision.denied["knowledge.bogus"]


def test_multiple_domains_are_evaluated_independently() -> None:
    """ADR-0203 acceptance bullet 2, restated: one call can authorize some
    requested domains while denying others - not an all-or-nothing verdict.
    """
    store = _store_from(
        "domains:\n"
        "  knowledge.sales:\n"
        "    allowed_groups: [sales]\n"
        "  knowledge.adv:\n"
        "    allowed_groups: [adv]\n"
    )
    decision = evaluate_knowledge(
        store=store,
        agent_declared=["knowledge.sales", "knowledge.adv"],
        task_allowed=["knowledge.sales", "knowledge.adv"],
        caller_groups=["sales"],  # only satisfies knowledge.sales
    )
    assert decision.authorized_domains == ["knowledge.sales"]
    assert "knowledge.adv" in decision.denied
    assert "knowledge.sales" not in decision.denied


TESTS = [
    test_real_knowledge_policy_loads_and_covers_every_repo_domain,
    test_missing_policy_file_fails_closed,
    test_malformed_domains_shape_fails_closed,
    test_allowed_knowledge_is_declared_independently_of_allowed_tools,
    test_domain_outside_agent_ceiling_is_denied_even_if_task_requests_it,
    test_caller_without_required_group_is_denied,
    test_unknown_domain_fails_closed,
    test_multiple_domains_are_evaluated_independently,
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
