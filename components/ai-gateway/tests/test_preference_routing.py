"""ADR-0412 tests for app/routing.py's per-(agent,task) preference
reordering: a pure permutation of the candidates that SURVIVED
classification/local-only filtering - it must never resurrect a provider
those hard constraints removed (ADR-0021/0035), and no preference must
ever weaken the fail-closed posture. Pure in-memory config, no
cluster/network needed.

Run from this directory:

    python3 tests/test_preference_routing.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.routing import RoutingError, RoutingTable  # noqa: E402


class _StubTable(RoutingTable):
    """Same shape as tests/test_maas_adapter.py's stub: bypasses file
    loading, config injected directly."""

    def __init__(self, config):
        self._routing_path = "<stub>"
        self._config = config


_PROVIDERS = {
    "providers": [
        {"name": "local", "kind": "local", "eligible_for": ["C1", "C2", "C3"], "serves_adapters": True},
        {"name": "local-gpt-oss", "kind": "local", "eligible_for": ["C1", "C2", "C3"]},
        {"name": "openai", "kind": "saas", "eligible_for": ["C1", "C2"]},
        {"name": "gemini", "kind": "saas", "eligible_for": ["C1"]},
        {"name": "anthropic", "kind": "saas", "eligible_for": ["C1", "C2"]},
    ]
}


def test_preferred_survivors_move_to_front_in_given_order() -> None:
    table = _StubTable(_PROVIDERS)
    names = [c.name for c in table.candidates_for("C1", prefer=["local-gpt-oss", "local"])]
    assert names == ["local-gpt-oss", "local", "openai", "gemini", "anthropic"]


def test_unlisted_survivors_keep_relative_order_after_preferred() -> None:
    table = _StubTable(_PROVIDERS)
    names = [c.name for c in table.candidates_for("C1", prefer=["anthropic"])]
    assert names == ["anthropic", "local", "local-gpt-oss", "openai", "gemini"]


def test_unknown_provider_name_is_ignored() -> None:
    table = _StubTable(_PROVIDERS)
    names = [c.name for c in table.candidates_for("C2", prefer=["no-such-provider", "local-gpt-oss"])]
    assert names == ["local-gpt-oss", "local", "openai", "anthropic"]


def test_preference_never_resurrects_a_filtered_provider() -> None:
    """The security invariant: openai survived neither C3 eligibility nor
    the preference's wishes - listing it must not bring it back."""
    table = _StubTable(_PROVIDERS)
    candidates = table.candidates_for("C3", prefer=["openai", "local-gpt-oss"])
    assert [c.name for c in candidates] == ["local-gpt-oss", "local"]
    assert all(c.kind == "local" for c in candidates)


def test_local_only_with_preference_still_yields_only_local_kinds() -> None:
    table = _StubTable(_PROVIDERS)
    candidates = table.candidates_for("C1", local_only=True, prefer=["anthropic", "local-gpt-oss"])
    assert [c.name for c in candidates] == ["local-gpt-oss", "local"]
    assert all(c.kind == "local" for c in candidates)


def test_no_preference_is_byte_identical_to_todays_order() -> None:
    table = _StubTable(_PROVIDERS)
    assert [c.name for c in table.candidates_for("C2")] == [
        c.name for c in table.candidates_for("C2", prefer=None)
    ] == ["local", "local-gpt-oss", "openai", "anthropic"]


def test_duplicate_preference_names_are_deduped() -> None:
    table = _StubTable(_PROVIDERS)
    names = [c.name for c in table.candidates_for("C1", prefer=["local-gpt-oss", "local-gpt-oss", "local"])]
    assert names == ["local-gpt-oss", "local", "openai", "gemini", "anthropic"]


def test_fail_closed_still_raises_with_a_preference() -> None:
    """An empty post-filter set must still 422 upstream - a preference is
    applied after the fail-closed check, never instead of it."""
    table = _StubTable({"providers": [{"name": "openai", "kind": "saas", "eligible_for": ["C1"]}]})
    try:
        table.candidates_for("C3", prefer=["openai"])
    except RoutingError:
        pass
    else:
        raise AssertionError("expected RoutingError for C3 with no eligible provider, even with a preference")


def test_no_config_degraded_mode_is_unaffected() -> None:
    table = _StubTable({})
    candidates = table.candidates_for("C3", prefer=["local-gpt-oss"])
    assert [c.name for c in candidates] == ["local"]


# ADR-0416: gpt-oss-120b via OVHcloud - same saas eligibility shape as
# openai/anthropic above (eligible_for: [C1, C2], never C3), exercised
# with its own provider set so the assertions above stay untouched.
_PROVIDERS_WITH_OVHCLOUD_GPT_OSS = {
    "providers": [
        {"name": "local", "kind": "local", "eligible_for": ["C1", "C2", "C3"], "serves_adapters": True},
        {"name": "local-gpt-oss", "kind": "local", "eligible_for": ["C1", "C2", "C3"]},
        {"name": "ovhcloud-gpt-oss-120b", "kind": "saas", "eligible_for": ["C1", "C2"]},
    ]
}


def test_ovhcloud_gpt_oss_120b_is_excluded_at_c3() -> None:
    """Security-negative, mirrors test_maas_adapter_never_widens_c3_local_only_eligibility:
    a C3 request must never see the new OVH provider, preference or not."""
    table = _StubTable(_PROVIDERS_WITH_OVHCLOUD_GPT_OSS)
    candidates = table.candidates_for("C3", prefer=["ovhcloud-gpt-oss-120b", "local-gpt-oss"])
    assert [c.name for c in candidates] == ["local-gpt-oss", "local"]
    assert all(c.kind == "local" for c in candidates)


def test_ovhcloud_gpt_oss_120b_eligible_and_preferred_at_c2() -> None:
    table = _StubTable(_PROVIDERS_WITH_OVHCLOUD_GPT_OSS)
    names = [c.name for c in table.candidates_for("C2", prefer=["ovhcloud-gpt-oss-120b", "local-gpt-oss", "local"])]
    assert names == ["ovhcloud-gpt-oss-120b", "local-gpt-oss", "local"]


def test_ovhcloud_gpt_oss_120b_eligible_without_preference_at_c1() -> None:
    table = _StubTable(_PROVIDERS_WITH_OVHCLOUD_GPT_OSS)
    names = [c.name for c in table.candidates_for("C1")]
    assert "ovhcloud-gpt-oss-120b" in names


# ADR-0417: mistral-codestral - same saas eligibility shape as
# ovhcloud-gpt-oss-120b above (eligible_for: [C1, C2], never C3).
_PROVIDERS_WITH_MISTRAL_CODESTRAL = {
    "providers": [
        {"name": "local", "kind": "local", "eligible_for": ["C1", "C2", "C3"], "serves_adapters": True},
        {"name": "local-gpt-oss", "kind": "local", "eligible_for": ["C1", "C2", "C3"]},
        {"name": "mistral-codestral", "kind": "saas", "eligible_for": ["C1", "C2"]},
    ]
}


def test_mistral_codestral_is_excluded_at_c3() -> None:
    table = _StubTable(_PROVIDERS_WITH_MISTRAL_CODESTRAL)
    candidates = table.candidates_for("C3", prefer=["mistral-codestral", "local-gpt-oss"])
    assert [c.name for c in candidates] == ["local-gpt-oss", "local"]
    assert all(c.kind == "local" for c in candidates)


def test_mistral_codestral_eligible_and_preferred_at_c2() -> None:
    table = _StubTable(_PROVIDERS_WITH_MISTRAL_CODESTRAL)
    names = [c.name for c in table.candidates_for("C2", prefer=["mistral-codestral", "local-gpt-oss", "local"])]
    assert names == ["mistral-codestral", "local-gpt-oss", "local"]


def test_mistral_codestral_eligible_without_preference_at_c1() -> None:
    table = _StubTable(_PROVIDERS_WITH_MISTRAL_CODESTRAL)
    names = [c.name for c in table.candidates_for("C1")]
    assert "mistral-codestral" in names


TESTS = [
    test_preferred_survivors_move_to_front_in_given_order,
    test_unlisted_survivors_keep_relative_order_after_preferred,
    test_unknown_provider_name_is_ignored,
    test_preference_never_resurrects_a_filtered_provider,
    test_local_only_with_preference_still_yields_only_local_kinds,
    test_no_preference_is_byte_identical_to_todays_order,
    test_duplicate_preference_names_are_deduped,
    test_fail_closed_still_raises_with_a_preference,
    test_no_config_degraded_mode_is_unaffected,
    test_ovhcloud_gpt_oss_120b_is_excluded_at_c3,
    test_ovhcloud_gpt_oss_120b_eligible_and_preferred_at_c2,
    test_ovhcloud_gpt_oss_120b_eligible_without_preference_at_c1,
    test_mistral_codestral_is_excluded_at_c3,
    test_mistral_codestral_eligible_and_preferred_at_c2,
    test_mistral_codestral_eligible_without_preference_at_c1,
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
