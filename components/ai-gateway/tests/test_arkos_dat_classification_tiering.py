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
_MODEL_ROUTING_POLICY_PATH = str(_REPO_ROOT / "policies" / "model-routing" / "model-routing-policy.yaml")


def _candidates(agent: str, task: str, classification: str, header_local_only: bool = False):
    routing_table = RoutingTable(_PROVIDER_ROUTING_PATH)
    policy = ModelRoutingPolicy(_MODEL_ROUTING_POLICY_PATH)
    local_only = header_local_only or policy.local_only_for_classification(agent, task, classification)
    prefer = policy.preference_for(agent, task)
    strict = policy.strict_for(agent, task)
    return routing_table.candidates_for(classification, local_only=local_only, prefer=prefer, strict=strict)


def test_dat_c1_reaches_ovhcloud_first() -> None:
    names = [c.name for c in _candidates("arkos", "draft-architecture-testimonial", "C1")]
    assert names[0] == "ovhcloud-gpt-oss-120b", names


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


def test_workshop_presentation_is_unaffected_at_c2() -> None:
    """ADR-0550 is scoped to the DAT task only - workshop-presentation's
    own preference entry must not carry local_only_for, so a C2 workshop
    turn (reachable only via its own C3 agent seed + fixed C2 reflect
    ceiling, never the DAT baseline) still reaches ovhcloud-gpt-oss-120b."""
    names = [c.name for c in _candidates("arkos", "workshop-presentation", "C2")]
    assert "ovhcloud-gpt-oss-120b" in names, names


def test_comage_compare_historical_deals_is_unaffected_at_c2() -> None:
    """Regression guard: Comage's own, unrelated C2 use of
    ovhcloud-gpt-oss-120b (its own preference entry, no local_only_for)
    must be completely untouched by Arkos DAT's new field."""
    names = [c.name for c in _candidates("comage", "compare-historical-deals", "C2")]
    assert "ovhcloud-gpt-oss-120b" in names, names


TESTS = [
    test_dat_c1_reaches_ovhcloud_first,
    test_dat_c2_never_reaches_an_external_provider,
    test_dat_c3_never_reaches_an_external_provider,
    test_dat_c2_still_prefers_local_gpt_oss_first,
    test_dat_c2_c3_local_loss_fails_closed_rather_than_externalizing,
    test_workshop_presentation_is_unaffected_at_c2,
    test_comage_compare_historical_deals_is_unaffected_at_c2,
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
