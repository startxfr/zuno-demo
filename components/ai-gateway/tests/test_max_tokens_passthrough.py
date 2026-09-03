"""ADR-0544 tests for the ai-gateway half of the declarative max_tokens
mechanism: app/main.py's X-Zuno-Max-Tokens header parsing
(_parse_max_tokens) and app/providers.py's per-vendor forwarding
(chat_model_for), including the via_maas branch structure-demo's own
preferred candidate (local-maas) actually uses - that branch is the load-
bearing case, since app/maas_adapter.py builds a SEPARATE ChatOpenAI
client from app/providers.py's local branch and it is easy to wire one
without the other. Mocks the LangChain client construction (no network
calls), same pattern as tests/test_adapter_selection.py.

Run from this directory:

    python3 tests/test_max_tokens_passthrough.py
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main as app_main  # noqa: E402
from app import maas_adapter, providers  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402


def _reset_maas_env() -> None:
    for key in ("MAAS_ADAPTER_ENABLED", "MAAS_GATEWAY_ENDPOINT", "MAAS_GATEWAY_API_KEY_ENV", "MAAS_EXTERNAL_EGRESS_ENABLED"):
        os.environ.pop(key, None)
    maas_adapter.MAAS_ADAPTER_ENABLED = False
    maas_adapter.MAAS_GATEWAY_ENDPOINT = ""
    maas_adapter.MAAS_GATEWAY_API_KEY_ENV = "MAAS_GATEWAY_API_KEY"
    maas_adapter.MAAS_EXTERNAL_EGRESS_ENABLED = False


# --- _parse_max_tokens: never fails a turn on a malformed header ----------

def test_parse_max_tokens_accepts_a_plain_positive_integer() -> None:
    assert app_main._parse_max_tokens("1024") == 1024


def test_parse_max_tokens_rejects_empty() -> None:
    assert app_main._parse_max_tokens("") is None


def test_parse_max_tokens_rejects_non_numeric() -> None:
    assert app_main._parse_max_tokens("abc") is None


def test_parse_max_tokens_rejects_zero() -> None:
    assert app_main._parse_max_tokens("0") is None


def test_parse_max_tokens_rejects_negative() -> None:
    # "-5".isdigit() is False (the sign isn't a digit) - covered
    # defensively anyway since a future rewrite of the check could change that.
    assert app_main._parse_max_tokens("-5") is None


def test_parse_max_tokens_rejects_a_decimal() -> None:
    assert app_main._parse_max_tokens("1e3") is None


def test_parse_max_tokens_rejects_out_of_range() -> None:
    assert app_main._parse_max_tokens("99999") is None


def test_parse_max_tokens_accepts_the_upper_bound() -> None:
    assert app_main._parse_max_tokens("8192") == 8192


# --- providers.chat_model_for: per-vendor forwarding -----------------------

def test_local_candidate_forwards_max_tokens() -> None:
    _reset_maas_env()
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"model": "qwen3.6-27b-instruct"}, max_tokens=1536)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["max_tokens"] == 1536


def test_local_candidate_forwards_none_when_absent() -> None:
    """Today's exact behavior for every candidate that never declares
    max_tokens - this must stay a true no-op, not "0" or a surprise default."""
    _reset_maas_env()
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"model": "qwen3.6-27b-instruct"})
    (_, kwargs) = chat_openai.call_args
    assert kwargs["max_tokens"] is None


def test_gemini_uses_max_output_tokens_not_max_tokens() -> None:
    """The one real per-vendor translation this factory needs."""
    _reset_maas_env()
    candidate = ProviderCandidate(name="gemini", kind="saas")
    with mock.patch("langchain_google_genai.ChatGoogleGenerativeAI") as chat_gemini:
        providers.chat_model_for(candidate, {"model": "gemini-1.5-pro"}, max_tokens=800)
    (_, kwargs) = chat_gemini.call_args
    assert kwargs["max_output_tokens"] == 800
    assert "max_tokens" not in kwargs


def test_openai_candidate_forwards_max_tokens() -> None:
    _reset_maas_env()
    candidate = ProviderCandidate(name="openai", kind="saas")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"model": "gpt-4o-mini"}, max_tokens=500)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["max_tokens"] == 500


def test_ovhcloud_candidate_forwards_max_tokens() -> None:
    _reset_maas_env()
    candidate = ProviderCandidate(name="ovhcloud-gpt-oss-120b", kind="saas")
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, {"model": "gpt-oss-120b"}, max_tokens=500)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["max_tokens"] == 500


def test_mistral_and_codestral_forward_max_tokens() -> None:
    _reset_maas_env()
    for name, model_key in (("mistral", "mistral-large-latest"), ("mistral-codestral", "codestral-latest")):
        candidate = ProviderCandidate(name=name, kind="saas")
        with mock.patch("langchain_mistralai.ChatMistralAI") as chat_mistral:
            providers.chat_model_for(candidate, {"model": model_key}, max_tokens=700)
        (_, kwargs) = chat_mistral.call_args
        assert kwargs["max_tokens"] == 700, name


def test_anthropic_forwards_max_tokens() -> None:
    _reset_maas_env()
    candidate = ProviderCandidate(name="anthropic", kind="saas")
    with mock.patch("langchain_anthropic.ChatAnthropic") as chat_anthropic:
        providers.chat_model_for(candidate, {"model": "claude-3-5-sonnet-latest"}, max_tokens=700)
    (_, kwargs) = chat_anthropic.call_args
    assert kwargs["max_tokens"] == 700


def test_via_maas_branch_forwards_max_tokens() -> None:
    """The load-bearing regression guard: structure-demo's preferred
    candidate is local-maas (via_maas: true), built by
    app/maas_adapter.py, NOT app/providers.py's local branch above.
    Skipping this branch would make max_tokens a silent no-op on its
    first real usage."""
    _reset_maas_env()
    maas_adapter.MAAS_ADAPTER_ENABLED = True
    candidate = ProviderCandidate(name="local-maas", kind="local")
    cfg = {"model": "qwen3.6-27b-instruct", "via_maas": True, "endpoint": "https://maas.example/v1"}
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, cfg, max_tokens=1536)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["max_tokens"] == 1536
    _reset_maas_env()


TESTS = [
    test_parse_max_tokens_accepts_a_plain_positive_integer,
    test_parse_max_tokens_rejects_empty,
    test_parse_max_tokens_rejects_non_numeric,
    test_parse_max_tokens_rejects_zero,
    test_parse_max_tokens_rejects_negative,
    test_parse_max_tokens_rejects_a_decimal,
    test_parse_max_tokens_rejects_out_of_range,
    test_parse_max_tokens_accepts_the_upper_bound,
    test_local_candidate_forwards_max_tokens,
    test_local_candidate_forwards_none_when_absent,
    test_gemini_uses_max_output_tokens_not_max_tokens,
    test_openai_candidate_forwards_max_tokens,
    test_ovhcloud_candidate_forwards_max_tokens,
    test_mistral_and_codestral_forward_max_tokens,
    test_anthropic_forwards_max_tokens,
    test_via_maas_branch_forwards_max_tokens,
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
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
