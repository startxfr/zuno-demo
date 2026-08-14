"""ADR-0114 tests for the MaaS adapter prototype: app/maas_adapter.py and
its wiring into app/providers.py's chat_model_for(). Mocks the LangChain
client construction (no network calls) - proves the *selection* and
*eligibility* logic, not a live MaaS call.

Security-negative focus (ADR-0114 Security considerations: "MaaS
authorization must not be treated as sufficient permission to externalize
C2/C3 data"): the adapter can only ever change which client class builds
an already-eligible candidate. It must never be reachable for a candidate
app/routing.py's classification-eligibility filter already rejected -
proven here by exercising RoutingTable.candidates_for() with the adapter
enabled and confirming the candidate set for a local-only/C3 request is
unchanged (still local-only), before chat_model_for() is ever called.

Run from this directory:

    python3 tests/test_maas_adapter.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock  # noqa: E402

from app import maas_adapter, providers  # noqa: E402
from app.routing import ProviderCandidate, RoutingTable  # noqa: E402


def _reset_adapter_env(**overrides: str) -> None:
    for key in ("MAAS_ADAPTER_ENABLED", "MAAS_GATEWAY_ENDPOINT", "MAAS_GATEWAY_API_KEY_ENV"):
        os.environ.pop(key, None)
    os.environ.update(overrides)
    maas_adapter.MAAS_ADAPTER_ENABLED = (
        os.getenv("MAAS_ADAPTER_ENABLED", "false").strip().lower() == "true"
    )
    maas_adapter.MAAS_GATEWAY_ENDPOINT = os.getenv("MAAS_GATEWAY_ENDPOINT", "")
    maas_adapter.MAAS_GATEWAY_API_KEY_ENV = os.getenv("MAAS_GATEWAY_API_KEY_ENV", "MAAS_GATEWAY_API_KEY")


def test_adapter_disabled_by_default() -> None:
    _reset_adapter_env()
    assert maas_adapter.enabled() is False
    assert maas_adapter.should_use_maas({"via_maas": True}) is False


def test_provider_must_opt_in_even_when_globally_enabled() -> None:
    _reset_adapter_env(MAAS_ADAPTER_ENABLED="true", MAAS_GATEWAY_ENDPOINT="http://maas.example/v1")
    assert maas_adapter.should_use_maas({}) is False, "no via_maas -> adapter must not apply"
    assert maas_adapter.should_use_maas({"via_maas": False}) is False
    assert maas_adapter.should_use_maas({"via_maas": True}) is True


def test_global_switch_off_wins_even_if_provider_opted_in() -> None:
    _reset_adapter_env(MAAS_ADAPTER_ENABLED="false")
    assert maas_adapter.should_use_maas({"via_maas": True}) is False


def test_chat_model_for_uses_direct_client_when_adapter_disabled() -> None:
    _reset_adapter_env()
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"via_maas": True, "model": "qwen2.5-7b-instruct"})
    (_, kwargs) = chat_openai.call_args
    assert "qwen25-7b-instruct-predictor" in kwargs["base_url"] or kwargs["model"] == "qwen2.5-7b-instruct"


def test_chat_model_for_uses_maas_client_when_opted_in_and_enabled() -> None:
    _reset_adapter_env(MAAS_ADAPTER_ENABLED="true", MAAS_GATEWAY_ENDPOINT="http://maas.example/v1")
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(
            candidate, {"via_maas": True, "model": "qwen2.5-7b-instruct", "maas_model_ref": "maas/qwen2.5-7b"}
        )
    (_, kwargs) = chat_openai.call_args
    assert kwargs["base_url"] == "http://maas.example/v1"
    assert kwargs["model"] == "maas/qwen2.5-7b"


def test_maas_adapter_without_endpoint_fails_loudly() -> None:
    _reset_adapter_env(MAAS_ADAPTER_ENABLED="true")
    try:
        maas_adapter.chat_model_via_maas({"model": "qwen2.5-7b-instruct"})
        raise AssertionError("expected MaasAdapterError")
    except maas_adapter.MaasAdapterError as exc:
        assert "MAAS_GATEWAY_ENDPOINT" in str(exc)


def test_maas_adapter_never_widens_c3_local_only_eligibility() -> None:
    """Security-negative: with the adapter globally enabled, a C3/local-only
    request's candidate set is unchanged - still exactly the local
    candidate. Eligibility filtering happens in RoutingTable, entirely
    before chat_model_for()/the adapter are ever consulted, so enabling the
    adapter cannot surface an external candidate for a request that was
    never eligible for one."""
    _reset_adapter_env(MAAS_ADAPTER_ENABLED="true", MAAS_GATEWAY_ENDPOINT="http://maas.example/v1")

    class _StubTable(RoutingTable):
        def __init__(self) -> None:  # noqa: super not called - avoid file I/O
            self._config = {
                "providers": [
                    {"name": "local", "kind": "local", "eligible_for": ["C1", "C2", "C3"]},
                    {"name": "openai", "kind": "saas", "eligible_for": ["C1", "C2"], "via_maas": True},
                ]
            }

    table = _StubTable()
    candidates = table.candidates_for("C3", local_only=True)
    assert [c.name for c in candidates] == ["local"], (
        "MaaS adapter being enabled must never change which candidates a "
        "C3/local-only request is offered"
    )


TESTS = [
    test_adapter_disabled_by_default,
    test_provider_must_opt_in_even_when_globally_enabled,
    test_global_switch_off_wins_even_if_provider_opted_in,
    test_chat_model_for_uses_direct_client_when_adapter_disabled,
    test_chat_model_for_uses_maas_client_when_opted_in_and_enabled,
    test_maas_adapter_without_endpoint_fails_loudly,
    test_maas_adapter_never_widens_c3_local_only_eligibility,
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
    _reset_adapter_env()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
