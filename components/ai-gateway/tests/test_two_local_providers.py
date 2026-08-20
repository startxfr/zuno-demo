"""ADR-0412 tests for app/providers.py with TWO local providers: each
local candidate builds its client from its OWN provider entry's
endpoint/model (env vars are only the config-less fallback), and a LoRA
adapter is honored only on the entry that declares `serves_adapters:
true` (the qwen runtime) - never sent to the gpt-oss runtime, which has
no --enable-lora. Mocks the LangChain client construction (no network),
same pattern as tests/test_adapter_selection.py.

Run from this directory:

    python3 tests/test_two_local_providers.py
"""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import providers  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402

_QWEN_URL = "http://qwen25-7b-instruct-predictor.zuno-ai-run.svc:8080/v1"
# ADR-0414: gpt-oss-20b is now an LLMInferenceService, reached via its own
# -kserve-workload-svc Service (port 8000), not a classic predictor.
_GPTOSS_URL = "http://gpt-oss-20b-kserve-workload-svc.zuno-ai-run.svc:8000/v1"


def test_second_local_uses_its_own_endpoint_and_model_over_env() -> None:
    """LOCAL_MODEL_ENDPOINT/NAME point at qwen (chart env) - the gpt-oss
    candidate must still build from its own cfg fields."""
    candidate = ProviderCandidate(name="local-gpt-oss", kind="local")
    cfg = {"model": "gpt-oss-20b", "endpoint": _GPTOSS_URL}
    with mock.patch.dict(os.environ, {"LOCAL_MODEL_ENDPOINT": _QWEN_URL, "LOCAL_MODEL_NAME": "qwen2.5-7b-instruct"}):
        with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
            providers.chat_model_for(candidate, cfg)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["base_url"] == _GPTOSS_URL
    assert kwargs["model"] == "gpt-oss-20b"


def test_configless_local_still_falls_back_to_env() -> None:
    """Backward compat: the degraded no-config mode (empty cfg) keeps
    resolving from the env vars exactly as before ADR-0412."""
    candidate = ProviderCandidate(name="local", kind="local")
    with mock.patch.dict(os.environ, {"LOCAL_MODEL_ENDPOINT": _QWEN_URL, "LOCAL_MODEL_NAME": "qwen2.5-7b-instruct"}):
        with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
            providers.chat_model_for(candidate, {})
    (_, kwargs) = chat_openai.call_args
    assert kwargs["base_url"] == _QWEN_URL
    assert kwargs["model"] == "qwen2.5-7b-instruct"


def test_adapter_honored_on_the_serves_adapters_local() -> None:
    candidate = ProviderCandidate(name="local", kind="local")
    cfg = {"model": "qwen2.5-7b-instruct", "endpoint": _QWEN_URL, "serves_adapters": True}
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, cfg, adapter="comage-lora")
    (_, kwargs) = chat_openai.call_args
    assert kwargs["model"] == "comage-lora"


def test_adapter_dropped_on_a_local_without_serves_adapters() -> None:
    """The ADR-0412 negative: sending a qwen LoRA module name to the
    gpt-oss runtime would 404 every request - chat_model_for() itself
    drops it, keeping the base model, regardless of caller discipline."""
    candidate = ProviderCandidate(name="local-gpt-oss", kind="local")
    cfg = {"model": "gpt-oss-20b", "endpoint": _GPTOSS_URL}
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, cfg, adapter="comage-lora")
    (_, kwargs) = chat_openai.call_args
    assert kwargs["model"] == "gpt-oss-20b", "a runtime without serves_adapters must never receive an adapter name"


TESTS = [
    test_second_local_uses_its_own_endpoint_and_model_over_env,
    test_configless_local_still_falls_back_to_env,
    test_adapter_honored_on_the_serves_adapters_local,
    test_adapter_dropped_on_a_local_without_serves_adapters,
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
