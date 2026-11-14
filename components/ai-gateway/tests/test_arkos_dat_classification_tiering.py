"""ADR-0550/WP-137 integration tests: the REAL committed
platform/ai-gateway/provider-routing.yaml and
policies/model-routing/model-routing-policy.yaml files, loaded together
exactly as app/main.py's chat_completions handler composes them
(`local_only = header flag OR model_routing_policy.local_only_for_
classification(...)`, then `routing_table.candidates_for(...)`), for
Arkos's draft-architecture-testimonial task.

Unlike tests/test_model_routing_policy.py (policy parsing, temp files)
and tests/test_preference_routing.py (routing.py mechanics, stub
provider config), this file is the one place proving the two shipped
YAML files actually combine into ADR-0550's decision 3 table for the
real DAT entry - and that Comage/Cognos's own, unrelated C2 use of
ovhcloud-gpt-oss-120b is untouched. No cluster/network needed - both
files are read straight off disk.

Run from this directory:

    python3 tests/test_arkos_dat_classification_tiering.py
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.model_routing_policy import ModelRoutingPolicy  # noqa: E402
from app.routing import RoutingError, RoutingTable  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_PROVIDER_ROUTING_PATH = str(_REPO_ROOT / "platform" / "ai-gateway" / "provider-routing.yaml")
# WP-165: the model-routing policy is a corp policy of the admitted agents
# release (platform/okf/release_cache.py), the one this gateway's image bakes.
sys.path.insert(0, str(_REPO_ROOT / "platform" / "okf"))
import release_cache  # noqa: E402

_MODEL_ROUTING_POLICY_PATH = str(release_cache.release_dir() / "policies" / "model-routing" / "model-routing-policy.yaml")


def _candidates(agent: str, task: str, classification: str, header_local_only: bool = False):
    routing_table = RoutingTable(_PROVIDER_ROUTING_PATH)
    policy = ModelRoutingPolicy(_MODEL_ROUTING_POLICY_PATH)
    local_only = header_local_only or policy.local_only_for_classification(agent, task, classification)
    prefer = policy.preference_for(agent, task)
    strict = policy.strict_for(agent, task)
    return routing_table.candidates_for(classification, local_only=local_only, prefer=prefer, strict=strict)


def test_dat_c1_never_reaches_an_external_provider() -> None:
    """Agents release v0.8.1 (zuno-demo WP-187): the DAT task reads Confluence and the technical docs, and
    UnifAI sets the turn level from the declaration, not from what was retrieved, so ADR-0550's C1 external
    tier is closed. C1 is local only like C2 and C3."""
    names = [c.name for c in _candidates("arkos", "draft-architecture-testimonial", "C1")]
    assert "ovhcloud-gpt-oss-120b" not in names, names
    assert names, "a C1 DAT turn must still have at least one local candidate"


def test_dat_c2_never_reaches_an_external_provider() -> None:
    names = [c.name for c in _candidates("arkos", "draft-architecture-testimonial", "C2")]
    assert "ovhcloud-gpt-oss-120b" not in names, names
    assert names, "a C2 DAT turn must still have at least one local candidate"


def test_dat_c3_never_reaches_an_external_provider() -> None:
    names = [c.name for c in _candidates("arkos", "draft-architecture-testimonial", "C3")]
    assert "ovhcloud-gpt-oss-120b" not in names, names
    assert names


def test_dat_c2_still_prefers_local_gpt_oss_first() -> None:
    """local_only_for only ever ADDS the local_only filter - the existing
    prefer ordering (local-gpt-oss-maas/local-gpt-oss ahead of the qwen
    fleet default) must survive unchanged once ovhcloud-gpt-oss-120b is
    filtered out."""
    names = [c.name for c in _candidates("arkos", "draft-architecture-testimonial", "C2")]
    assert names[0] in ("local-gpt-oss-maas", "local-gpt-oss"), names


def test_dat_c2_c3_local_loss_fails_closed_rather_than_externalizing() -> None:
    """ADR-0550 acceptance #6: loss of every authorized local candidate at
    C2/C3 must raise (the caller returns an explicit failure), never fall
    back to an external provider. Simulated by forcing local_only True at
    a classification where, if local_only_for_classification's gate were
    absent, ovhcloud-gpt-oss-120b would otherwise be reachable."""
    try:
        RoutingTable(_PROVIDER_ROUTING_PATH).candidates_for(
            "C2", local_only=True, prefer=["ovhcloud-gpt-oss-120b"], strict=True
        )
    except RoutingError:
        pass
    else:
        raise AssertionError("a strict preference naming only an ineligible-at-local-only provider must raise")


def test_workshop_presentation_is_local_only_at_every_level() -> None:
    """Agents release v0.8.1 (zuno-demo WP-187): workshop-presentation allows knowledge.tech, so it is local
    only at every level. It used to reach ovhcloud-gpt-oss-120b through its fixed C2 reflect ceiling
    (ADR-0514); that exception is closed."""
    for level in ("C1", "C2", "C3"):
        names = [c.name for c in _candidates("arkos", "workshop-presentation", level)]
        assert "ovhcloud-gpt-oss-120b" not in names, (level, names)
        assert names, level


def test_confluence_reading_tasks_are_local_only_at_every_level() -> None:
    """Zuno-demo WP-187: every task that allows search_confluence or knowledge.tech reaches no external
    provider at C1, C2 or C3 (the rule is enforced by the agents repository's own test too)."""
    external = {c.name for c in RoutingTable(_PROVIDER_ROUTING_PATH).candidates_for("C1") if getattr(c, "kind", "") == "saas"}
    assert external, "the provider table must hold at least one external provider for this test to mean anything"
    for agent, task in (("tekos", "answer-technical-question"), ("tekos", "find-relevant-docs"),
                        ("arkos", "draft-architecture-testimonial"), ("arkos", "workshop-presentation"),
                        ("naveo", "answer-onboarding-question")):
        for level in ("C1", "C2", "C3"):
            names = {c.name for c in _candidates(agent, task, level)}
            assert not (names & external), (agent, task, level, names & external)


def test_tasks_that_do_not_read_confluence_keep_their_external_providers() -> None:
    """The local-only rule is scoped to the tasks that read Confluence or the technical docs (WP-187). A
    task that does not (tekos check-my-drive-docs, tekos write-code) keeps the external providers of its own
    preference entry, so the rule is not applied wider than intended. (This replaces the guard on Comage's
    compare-historical-deals, removed from the agents release with knowledge.sxa-legacy, WP-185.)"""
    drive = [c.name for c in _candidates("tekos", "check-my-drive-docs", "C1")]
    assert "ovhcloud-gpt-oss-120b" in drive, drive
    code = [c.name for c in _candidates("tekos", "write-code", "C1")]
    assert code and code[0] == "mistral-codestral", code


def test_arkos_write_code_is_served_locally_at_every_level() -> None:
    """Agents v1.0.1: arkos write-code was pinned strictly to mistral-codestral (ADR-0417), which is C1/C2 only,
    while Arkos is floored at C3 (ADR-0565), so every call failed closed. Its chain is now local only, at every
    level, and must hold at least one candidate at C3, the level every Arkos call carries."""
    external = {c.name for c in RoutingTable(_PROVIDER_ROUTING_PATH).candidates_for("C1") if getattr(c, "kind", "") == "saas"}
    for level in ("C1", "C2", "C3"):
        names = [c.name for c in _candidates("arkos", "write-code", level)]
        assert names, level
        assert not (set(names) & external), (level, set(names) & external)


TESTS = [
    test_dat_c1_never_reaches_an_external_provider,
    test_dat_c2_never_reaches_an_external_provider,
    test_dat_c3_never_reaches_an_external_provider,
    test_dat_c2_still_prefers_local_gpt_oss_first,
    test_dat_c2_c3_local_loss_fails_closed_rather_than_externalizing,
    test_workshop_presentation_is_local_only_at_every_level,
    test_confluence_reading_tasks_are_local_only_at_every_level,
    test_tasks_that_do_not_read_confluence_keep_their_external_providers,
    test_arkos_write_code_is_served_locally_at_every_level,
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
