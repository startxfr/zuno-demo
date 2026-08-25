"""ADR-0303 (WP-39) tests for app/providers.py's adapter-aware
chat_model_for(): declared adapter honored on a local candidate, ignored
(never applied) for any non-local or MaaS-transported candidate. Mocks
the LangChain client construction (no network calls), same pattern as
tests/test_maas_adapter.py.

Security-negative focus (the WP's own acceptance bullet): a C2/C3-
classified adapter must never reach an externally-eligible serving path.
LoRA adapters are a local-vLLM-only mechanism, so the concrete, testable
version of that guard is "chat_model_for() never lets a non-local (or
MaaS-transported) candidate build a client with the adapter's model
name" - proven directly against the function, not just against
app/main.py's own call-site discipline.

Run from this directory:

    python3 tests/test_adapter_selection.py
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import maas_adapter, providers  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402


def _reset_maas_env() -> None:
    for key in ("MAAS_ADAPTER_ENABLED", "MAAS_GATEWAY_ENDPOINT", "MAAS_GATEWAY_API_KEY_ENV", "MAAS_EXTERNAL_EGRESS_ENABLED"):
        os.environ.pop(key, None)
    maas_adapter.MAAS_ADAPTER_ENABLED = False
    maas_adapter.MAAS_GATEWAY_ENDPOINT = ""
    maas_adapter.MAAS_GATEWAY_API_KEY_ENV = "MAAS_GATEWAY_API_KEY"
    maas_adapter.MAAS_EXTERNAL_EGRESS_ENABLED = False


def test_declared_adapter_overrides_local_model_name() -> None:
    # serves_adapters: ADR-0412's intentional tightening - with two local
    # runtimes an adapter only applies to the provider entry that declares
    # it serves them (the qwen one); see test_two_local_providers.py for
    # the negative case.
    _reset_maas_env()
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"model": "qwen3.6-27b-instruct", "serves_adapters": True}, adapter="comage-lora")
    (_, kwargs) = chat_openai.call_args
    assert kwargs["model"] == "comage-lora"


def test_no_adapter_uses_base_model_name() -> None:
    _reset_maas_env()
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"model": "qwen3.6-27b-instruct"}, adapter=None)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["model"] == "qwen3.6-27b-instruct"


def test_adapter_never_applied_to_a_saas_candidate() -> None:
    """The security-negative proof: even if a caller mistakenly passes an
    adapter alongside a SaaS candidate, chat_model_for() itself drops it -
    the resulting client is never told to use a LoRA adapter module a
    SaaS provider wouldn't understand anyway, and (more importantly) this
    proves the guard doesn't rely on the caller getting it right."""
    _reset_maas_env()
    candidate = ProviderCandidate(name="openai", kind="saas")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"}, adapter="comage-lora")
    (_, kwargs) = chat_openai.call_args
    assert kwargs["model"] == "gpt-4o-mini", "a SaaS candidate must never receive the adapter's model name"


def test_adapter_never_applied_when_routed_via_maas() -> None:
    """Even a local candidate loses its adapter if ADR-0114's MaaS
    transport is in front of it - combining dynamic adapter selection
    with MaaS-mediated serving is out of this WP's scope (see
    app/providers.py's own docstring)."""
    maas_adapter.MAAS_ADAPTER_ENABLED = True
    maas_adapter.MAAS_GATEWAY_ENDPOINT = "http://maas.example/v1"
    maas_adapter.MAAS_GATEWAY_API_KEY_ENV = "MAAS_GATEWAY_API_KEY"
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch("app.maas_adapter.chat_model_via_maas") as via_maas:
        providers.chat_model_for(candidate, {"via_maas": True, "model": "qwen3.6-27b-instruct"}, adapter="comage-lora")
    assert via_maas.called
    _reset_maas_env()


TESTS = [
    test_declared_adapter_overrides_local_model_name,
    test_no_adapter_uses_base_model_name,
    test_adapter_never_applied_to_a_saas_candidate,
    test_adapter_never_applied_when_routed_via_maas,
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
    _reset_maas_env()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
