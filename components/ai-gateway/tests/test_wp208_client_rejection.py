"""WP-208 D8: a request the model refuses as malformed or too long (HTTP 400/413/422) is not replayed on the
sibling entry of the same model (`local-maas` and `local` are the same weights over two paths), is not a
provider outage, and ends as a 400 when nothing else could take it. A different model stays in the fallback
order, and a real failure still falls back as before.

Measured on demo333 2026-11-06: 20 Dify errors in 24 h, 10 per provider, all the same 400 ("maximum context
length is 32768 tokens ... prompt contains at least 24606 input tokens", "No user query found in messages").

Run from this directory:

    python3 tests/test_wp208_client_rejection.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402

from app import circuit_breaker, model_readiness  # noqa: E402
from app import main as app_main  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402
from app.schemas import ChatMessage  # noqa: E402

_ON = {"MODEL_READINESS_ENABLED": "false", "CIRCUIT_BREAKER_ENABLED": "true", "CIRCUIT_OPEN_SECONDS": "60"}


class _BadRequest(Exception):
    def __init__(self, code=400, text="maximum context length is 32768 tokens"):
        super().__init__(f"Error code: {code} - {text}")
        self.status_code = code


class _Model:
    def __init__(self, name, fail=None):
        self.name = name
        self.fail = fail
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        if self.fail is not None:
            raise self.fail

        class _Result:
            content = f"answer from {self.name}"
            usage_metadata = {"input_tokens": 1, "output_tokens": 1}

        return _Result()


_CFGS = {
    "local-maas": {"model": "qwen", "inference_service": "qwen36-27b-instruct", "via_maas": True},
    "local": {"model": "qwen", "inference_service": "qwen36-27b-instruct"},
    "local-gpt-oss-maas": {"model": "gpt-oss", "inference_service": "gpt-oss-20b", "via_maas": True},
    "local-gpt-oss": {"model": "gpt-oss", "inference_service": "gpt-oss-20b"},
}


def _run(names, models):
    candidates = [ProviderCandidate(name=n, kind="local") for n in names]

    def factory(candidate, *_a, **_k):
        return models[candidate.name]

    with mock.patch.dict(os.environ, _ON), \
         mock.patch.object(app_main, "chat_model_for", side_effect=factory), \
         mock.patch.object(app_main.routing_table, "provider_config", side_effect=lambda n: _CFGS[n]), \
         mock.patch.object(app_main, "_maas_call_kwargs", return_value={}), \
         mock.patch.object(app_main, "breaker", circuit_breaker.CircuitBreaker()), \
         mock.patch.object(app_main, "readiness", model_readiness.ModelReadiness()):
        return asyncio.run(app_main._invoke_with_fallback(
            candidates, "C1", [{"role": "user", "content": "hi"}],
            caller_sub="u-1", local_only=False, task_id="", requested_model="auto",
            raw_messages=[ChatMessage(role="user", content="hi")], request_id="req-1",
        ))


def test_the_model_family_ignores_the_maas_suffix() -> None:
    assert app_main._model_family("local-maas") == app_main._model_family("local") == "local"
    assert app_main._model_family("local-gpt-oss-maas") == "local-gpt-oss"
    assert app_main._model_family("local") != app_main._model_family("local-gpt-oss")


def test_only_the_models_own_refusals_count() -> None:
    assert app_main._client_rejection_status(_BadRequest(400)) == 400
    assert app_main._client_rejection_status(_BadRequest(413)) == 413
    assert app_main._client_rejection_status(_BadRequest(422)) == 422
    for code in (401, 404, 429, 500, 502, 503):
        assert app_main._client_rejection_status(_BadRequest(code)) is None, code
    assert app_main._client_rejection_status(ValueError("x")) is None


def test_a_400_is_not_replayed_on_the_same_model_and_ends_as_a_400() -> None:
    models = {"local-maas": _Model("local-maas", _BadRequest()), "local": _Model("local")}
    try:
        _run(["local-maas", "local"], models)
    except HTTPException as exc:
        assert exc.status_code == 400, exc.status_code
        assert "maximum context length" in exc.detail
    else:
        raise AssertionError("expected a 400")
    assert models["local-maas"].calls == 1 and models["local"].calls == 0


def test_a_different_model_still_takes_over() -> None:
    models = {
        "local-maas": _Model("local-maas", _BadRequest()), "local": _Model("local"),
        "local-gpt-oss-maas": _Model("local-gpt-oss-maas"), "local-gpt-oss": _Model("local-gpt-oss"),
    }
    result = _run(["local-maas", "local", "local-gpt-oss-maas", "local-gpt-oss"], models)
    assert result.zuno_provider == "local-gpt-oss-maas"
    assert models["local"].calls == 0 and models["local-gpt-oss"].calls == 0


def test_a_real_failure_still_falls_back_to_the_sibling() -> None:
    models = {"local-maas": _Model("local-maas", _BadRequest(503, "unavailable")), "local": _Model("local")}
    result = _run(["local-maas", "local"], models)
    assert result.zuno_provider == "local" and models["local-maas"].calls == 1


def test_a_400_then_a_real_failure_is_not_reported_as_a_400() -> None:
    models = {
        "local-maas": _Model("local-maas", _BadRequest()), "local": _Model("local"),
        "local-gpt-oss-maas": _Model("local-gpt-oss-maas", _BadRequest(503, "unavailable")),
        "local-gpt-oss": _Model("local-gpt-oss", _BadRequest(503, "unavailable")),
    }
    try:
        _run(["local-maas", "local", "local-gpt-oss-maas", "local-gpt-oss"], models)
    except HTTPException as exc:
        assert exc.status_code == 502, exc.status_code
    else:
        raise AssertionError("expected a 502")


def test_the_reply_cap_keeps_a_margin_under_the_window() -> None:
    """The 2026-11-06 case: window 32768, prompt estimated 24605 tokens, caller asked for more than the
    room. The cap used to be 32768 - 24605 = 8163, which vLLM refused for a prompt of 24606."""
    class _M:
        def __init__(self, n):
            self.content = "x" * (4 * n)

    messages = [_M(24604)]
    estimate = app_main._estimate_prompt_tokens(messages, None)
    assert estimate == 24605, estimate
    cap = app_main._candidate_max_tokens(16000, {"max_model_len": 32768}, messages, None)
    assert cap == 32768 - 24605 - 1230, cap
    assert 24606 + cap <= 32768
    # a small caller cap is untouched, a window that cannot be filled keeps the caller's cap as before
    assert app_main._candidate_max_tokens(1024, {"max_model_len": 32768}, messages, None) == 1024
    assert app_main._candidate_max_tokens(500, {}, messages, None) == 500
    assert app_main._candidate_max_tokens(None, {"max_model_len": 32768}, messages, None) is None


TESTS = [
    test_the_model_family_ignores_the_maas_suffix,
    test_only_the_models_own_refusals_count,
    test_a_400_is_not_replayed_on_the_same_model_and_ends_as_a_400,
    test_a_different_model_still_takes_over,
    test_a_real_failure_still_falls_back_to_the_sibling,
    test_a_400_then_a_real_failure_is_not_reported_as_a_400,
    test_the_reply_cap_keeps_a_margin_under_the_window,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc!r}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
