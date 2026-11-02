"""ADR-0591 (WP-188): the ai-gateway skips a local model its controller reports
not ready and a provider whose breaker is open, answers 503 at once when nothing
is left, runs every model client without SDK retries, and warms NeMo up.

Measured on demo333 2026-11-02: every `*-maas` candidate of a `Ready=False`
LLMInferenceService waited 180 s; a C1 chat reached openai after ~10 minutes.

Run from this directory:

    python3 tests/test_wp188_availability.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402

from app import circuit_breaker, guardrails, model_readiness  # noqa: E402
from app import main as app_main  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402
from app.schemas import ChatMessage  # noqa: E402

_ON = {"MODEL_READINESS_ENABLED": "true", "CIRCUIT_BREAKER_ENABLED": "true",
       "MODEL_READINESS_POLL_SECONDS": "10", "CIRCUIT_OPEN_SECONDS": "60"}


def _llmisvc(name, ready):
    return {"metadata": {"name": name},
            "status": {"conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}}


class _Status(Exception):
    def __init__(self, code):
        super().__init__(f"status {code}")
        self.status_code = code


class APITimeoutError(Exception):
    """Same class name as the openai SDK's, which is what is_outage keys on."""


class APIConnectionError(Exception):
    pass


# -- readiness -----------------------------------------------------------------

def test_ready_condition_is_read_from_status() -> None:
    assert model_readiness.ready_from_status(_llmisvc("m", True)) is True
    assert model_readiness.ready_from_status(_llmisvc("m", False)) is False
    assert model_readiness.ready_from_status({"status": {}}) is None


def test_readiness_fails_open() -> None:
    r = model_readiness.ModelReadiness()
    with mock.patch.dict(os.environ, _ON):
        assert r.is_ready("gpt-oss-20b", now=100.0)            # never polled
        r.update([_llmisvc("gpt-oss-20b", False)], now=100.0)
        assert not r.is_ready("gpt-oss-20b", now=105.0)        # known not ready
        assert r.is_ready("unknown-model", now=105.0)          # never seen
        assert r.is_ready(None, now=105.0)                     # provider names none
        assert r.is_ready("gpt-oss-20b", now=100.0 + 31.0)     # stale after 3 polls
    with mock.patch.dict(os.environ, {"MODEL_READINESS_ENABLED": "false"}):
        assert r.is_ready("gpt-oss-20b", now=105.0)            # switched off


# -- breaker -------------------------------------------------------------------

def test_what_counts_as_an_outage() -> None:
    assert circuit_breaker.is_outage(APITimeoutError())
    assert circuit_breaker.is_outage(APIConnectionError())
    assert circuit_breaker.is_outage(_Status(503))
    assert not circuit_breaker.is_outage(_Status(429))
    assert not circuit_breaker.is_outage(_Status(400))
    assert not circuit_breaker.is_outage(ValueError("bad payload"))


def test_breaker_opens_half_opens_once_and_closes() -> None:
    b = circuit_breaker.CircuitBreaker()
    with mock.patch.dict(os.environ, _ON):
        assert not b.is_open("p", now=0.0)
        assert b.record_failure("p", APITimeoutError(), now=0.0)
        assert b.is_open("p", now=30.0) and b.peek_open("p", now=30.0)
        assert not b.peek_open("p", now=61.0)                  # peek claims nothing
        assert not b.is_open("p", now=61.0)                    # the half-open trial
        assert b.is_open("p", now=62.0)                        # only one trial
        assert not b.is_open("p", now=122.0)                   # a lost trial expires
        b.record_success("p")
        assert not b.is_open("p", now=123.0)


def test_quota_and_client_errors_never_open_the_breaker() -> None:
    b = circuit_breaker.CircuitBreaker()
    with mock.patch.dict(os.environ, _ON):
        assert not b.record_failure("p", _Status(429), now=0.0)
        assert not b.record_failure("p", _Status(404), now=0.0)
        assert not b.is_open("p", now=1.0)
        b.record_failure("p", _Status(502), now=0.0)
        b.record_failure("p", _Status(429), now=1.0)            # reachable again
        assert not b.is_open("p", now=2.0)


# -- the candidate loop --------------------------------------------------------

class _FakeModel:
    def __init__(self, name):
        self.name = name
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1

        class _Result:
            content = f"answer from {self.name}"
            usage_metadata = {"input_tokens": 1, "output_tokens": 1}

        return _Result()


_CFGS = {
    "local-maas": {"model": "qwen", "inference_service": "qwen36-27b-instruct", "via_maas": True},
    "local": {"model": "qwen", "inference_service": "qwen36-27b-instruct"},
    "openai": {"model": "gpt-4o-mini"},
}


def _run(candidates, models, local_only=False):
    def factory(candidate, *_a, **_k):
        return models[candidate.name]

    with mock.patch.object(app_main, "chat_model_for", side_effect=factory), \
         mock.patch.object(app_main.routing_table, "provider_config", side_effect=lambda n: _CFGS[n]), \
         mock.patch.object(app_main, "_maas_call_kwargs", return_value={}):
        return asyncio.run(app_main._invoke_with_fallback(
            candidates, "C1", [{"role": "user", "content": "hi"}],
            caller_sub="u-1", local_only=local_only, task_id="", requested_model="auto",
            raw_messages=[ChatMessage(role="user", content="hi")], request_id="req-1",
        ))


def _candidates(*names):
    return [ProviderCandidate(name=n, kind="saas" if n == "openai" else "local") for n in names]


def _not_ready_pair():
    r = model_readiness.ModelReadiness()
    r.update([_llmisvc("qwen36-27b-instruct", False)])
    return r


def test_a_not_ready_pair_is_skipped_and_saas_serves() -> None:
    models = {n: _FakeModel(n) for n in ("local-maas", "local", "openai")}
    with mock.patch.dict(os.environ, _ON), mock.patch.object(app_main, "readiness", _not_ready_pair()):
        result = _run(_candidates("local-maas", "local", "openai"), models)
    assert result.zuno_provider == "openai"
    assert models["local-maas"].calls == 0 and models["local"].calls == 0


def test_local_only_with_no_ready_model_fails_and_never_falls_back() -> None:
    """local_only_for tasks (zuno-demo-agents model-routing policy): the
    eligible list holds local candidates only; skipping them all must end in
    a 503, never in an external provider."""
    models = {n: _FakeModel(n) for n in ("local-maas", "local", "openai")}
    with mock.patch.dict(os.environ, _ON), mock.patch.object(app_main, "readiness", _not_ready_pair()):
        try:
            _run(_candidates("local-maas", "local"), models, local_only=True)
        except HTTPException as exc:
            assert exc.status_code == 503, exc.status_code
        else:
            raise AssertionError("expected a 503")
    assert models["openai"].calls == 0


def test_an_open_breaker_skips_the_provider() -> None:
    models = {n: _FakeModel(n) for n in ("local-maas", "local", "openai")}
    b = circuit_breaker.CircuitBreaker()
    with mock.patch.dict(os.environ, _ON), mock.patch.object(app_main, "breaker", b), \
         mock.patch.object(app_main, "readiness", model_readiness.ModelReadiness()):
        b.record_failure("local-maas", APITimeoutError())
        result = _run(_candidates("local-maas", "local", "openai"), models)
    assert result.zuno_provider == "local" and models["local-maas"].calls == 0


def test_a_real_failure_opens_the_breaker_and_stays_a_502() -> None:
    class _Boom(_FakeModel):
        async def ainvoke(self, _messages):
            self.calls += 1
            raise APITimeoutError("Request timed out.")

    models = {"local": _Boom("local")}
    b = circuit_breaker.CircuitBreaker()
    with mock.patch.dict(os.environ, _ON), mock.patch.object(app_main, "breaker", b), \
         mock.patch.object(app_main, "readiness", model_readiness.ModelReadiness()):
        try:
            _run(_candidates("local"), models)
        except HTTPException as exc:
            assert exc.status_code == 502, exc.status_code
        else:
            raise AssertionError("expected a 502")
        assert b.peek_open("local")


def test_nothing_available_is_detected_before_a_stream_starts() -> None:
    with mock.patch.dict(os.environ, _ON), mock.patch.object(app_main, "readiness", _not_ready_pair()), \
         mock.patch.object(app_main.routing_table, "provider_config", side_effect=lambda n: _CFGS[n]):
        assert "local-maas: not ready" in app_main._nothing_available(_candidates("local-maas", "local"))
        assert app_main._nothing_available(_candidates("local-maas", "local", "openai")) is None


# -- no SDK retries ------------------------------------------------------------

def test_every_model_client_runs_without_sdk_retries() -> None:
    from app import maas_adapter, providers

    for name, kind in (("local", "local"), ("openai", "saas"), ("anthropic", "saas"),
                       ("mistral", "saas"), ("ovhcloud-gpt-oss-120b", "saas")):
        with mock.patch("langchain_openai.ChatOpenAI") as oai, \
             mock.patch("langchain_anthropic.ChatAnthropic") as ant, \
             mock.patch("langchain_mistralai.ChatMistralAI") as mis, \
             mock.patch("app.reasoning.with_reasoning", side_effect=lambda cls: cls):
            providers.chat_model_for(ProviderCandidate(name=name, kind=kind), {"model": "m"})
            called = [c for c in (oai, ant, mis) if c.called]
            assert called and called[0].call_args.kwargs.get("max_retries") == 0, name
    with mock.patch("langchain_openai.ChatOpenAI") as oai:
        maas_adapter.chat_model_via_maas({"endpoint": "https://maas/v1", "model": "q"}, request_id="r",
                                         caller_bearer_token="t")
        assert oai.call_args.kwargs["max_retries"] == 0


# -- NeMo warm-up --------------------------------------------------------------

def test_warm_up_uses_the_longer_timeout_and_records_nothing() -> None:
    seen = {}

    async def fake_detect(contents, timeout=None):
        seen["timeout"] = timeout
        return []

    with mock.patch.object(guardrails, "GUARDRAILS_BACKEND", "nemo"), \
         mock.patch.object(guardrails, "GUARDRAILS_NEMO_URL", "http://nemo"), \
         mock.patch.object(guardrails, "_detect_nemo", side_effect=fake_detect), \
         mock.patch.object(guardrails, "record_guardrails_evaluation") as record:
        assert asyncio.run(guardrails.warm_up()) is True
        assert not record.called
    assert seen["timeout"] == guardrails.GUARDRAILS_WARMUP_TIMEOUT_SECONDS


def test_keep_warm_repeats_on_its_interval() -> None:
    calls = []

    async def fake_warm_up():
        calls.append(1)
        if len(calls) == 3:
            raise asyncio.CancelledError()
        return True

    async def no_sleep(_seconds):
        return None

    with mock.patch.object(guardrails, "warm_up", side_effect=fake_warm_up), \
         mock.patch.object(guardrails, "GUARDRAILS_WARMUP_INTERVAL_SECONDS", 60.0), \
         mock.patch.object(guardrails.asyncio, "sleep", side_effect=no_sleep):
        try:
            asyncio.run(guardrails.keep_warm())
        except asyncio.CancelledError:
            pass
    assert len(calls) == 3


def test_keep_warm_runs_once_when_the_interval_is_zero() -> None:
    calls = []

    async def fake_warm_up():
        calls.append(1)
        return True

    with mock.patch.object(guardrails, "warm_up", side_effect=fake_warm_up), \
         mock.patch.object(guardrails, "GUARDRAILS_WARMUP_INTERVAL_SECONDS", 0.0):
        asyncio.run(guardrails.keep_warm())
    assert len(calls) == 1


def test_warm_up_is_a_no_op_without_nemo() -> None:
    with mock.patch.object(guardrails, "GUARDRAILS_BACKEND", "builtin"):
        assert asyncio.run(guardrails.warm_up()) is False


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


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
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
