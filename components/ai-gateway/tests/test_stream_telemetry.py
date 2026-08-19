"""ADR-0029 tests for streaming token/cost telemetry parity.

Verified live 2026-08-18: since agent-runtime (the only real caller) always
sets `stream: true`, `_stream_completion` was the ONLY path any real chat
turn took, and it never called `record_usage()` - zuno.model_tokens/
zuno.model_cost_usd had zero series in Grafana regardless of traffic
volume. This file pins down the fix: `stream_usage=True` on the ChatOpenAI
construction sites (app/providers.py), and `_stream_completion` (app/
main.py) accumulating chunks via AIMessageChunk.__add__ to read
usage_metadata off the merged result, same as the non-streaming path.

Run from this directory:

    python3 tests/test_stream_telemetry.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessageChunk  # noqa: E402

from app import providers  # noqa: E402
from app import telemetry  # noqa: E402
from app import main as app_main  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402

_QWEN_URL = "http://qwen25-7b-instruct-predictor.zuno-ai-run.svc:8080/v1"


# --- stream_usage=True at construction ---------------------------------


def test_local_candidate_enables_stream_usage() -> None:
    candidate = ProviderCandidate(name="local", kind="local")
    cfg = {"model": "qwen2.5-7b-instruct", "endpoint": _QWEN_URL}
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, cfg)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["stream_usage"] is True


def test_openai_candidate_enables_stream_usage() -> None:
    candidate = ProviderCandidate(name="openai", kind="remote")
    cfg = {"model": "gpt-4o-mini"}
    with mock.patch("langchain_openai.ChatOpenAI") as chat_openai:
        providers.chat_model_for(candidate, cfg)
    (_, kwargs) = chat_openai.call_args
    assert kwargs["stream_usage"] is True


# --- _stream_completion accumulation ------------------------------------


class _FakeStreamingModel:
    """Models an OpenAI/vLLM stream with `stream_options.include_usage`:
    content chunks, then (when configured) one terminal contentless chunk
    carrying usage_metadata - the exact shape `stream_usage=True` produces."""

    def __init__(self, tokens, usage=None, raise_after=None):
        self._tokens = tokens
        self._usage = usage
        self._raise_after = raise_after

    async def astream(self, _messages):
        for i, tok in enumerate(self._tokens):
            if self._raise_after is not None and i == self._raise_after:
                raise RuntimeError("provider dropped mid-stream")
            yield AIMessageChunk(content=tok)
        if self._usage is not None:
            yield AIMessageChunk(content="", usage_metadata=self._usage)


def _run_stream(fake_model, candidates=None):
    """Drains `_stream_completion` while spying on every
    ModelCallRecorder.record_usage call, returning (sse_chunks, recorded)."""
    candidates = candidates or [ProviderCandidate(name="local", kind="local")]
    recorded = []
    original = telemetry.ModelCallRecorder.record_usage

    def _spy(self, prompt_tokens, completion_tokens):
        recorded.append((prompt_tokens, completion_tokens))
        return original(self, prompt_tokens, completion_tokens)

    async def _drain():
        chunks = []
        async for c in app_main._stream_completion(candidates, "C1", [], "req-1"):
            chunks.append(c)
        return chunks

    with mock.patch.object(telemetry.ModelCallRecorder, "record_usage", _spy), \
         mock.patch.object(app_main, "chat_model_for", return_value=fake_model), \
         mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "test-model"}):
        chunks = asyncio.run(_drain())
    return chunks, recorded


def test_streaming_records_usage_from_terminal_chunk() -> None:
    fake = _FakeStreamingModel(
        ["Hello", ", ", "world"],
        usage={"input_tokens": 7, "output_tokens": 2, "total_tokens": 9},
    )
    chunks, recorded = _run_stream(fake)
    assert recorded == [(7, 2)]
    forwarded = "".join(
        json_chunk["choices"][0]["delta"].get("content", "")
        for json_chunk in _parse_sse_chunks(chunks)
    )
    assert forwarded == "Hello, world", "accumulation must never alter/duplicate what's forwarded to the client"


def test_streaming_without_usage_metadata_records_zero() -> None:
    """gemini/anthropic/mistral (no stream_usage field) or any remote
    candidate that never emits a usage chunk: recorded but gated off by
    model_call_span's `if has_token_usage`, same degrade-safe posture as
    today - no exception, no cost metric. Must use an explicit remote
    candidate here: since the local-cost-estimation change, a local
    candidate bills by call duration regardless of token usage, so it no
    longer demonstrates the "no metric" case (see
    tests/test_local_cost_estimation.py for local's own gating)."""
    fake = _FakeStreamingModel(["partial", "answer"], usage=None)
    _chunks, recorded = _run_stream(fake, candidates=[ProviderCandidate(name="gemini", kind="saas")])
    assert recorded == [(0, 0)]


def test_streaming_error_mid_stream_never_records_usage() -> None:
    fake = _FakeStreamingModel(
        ["a", "b", "c"],
        usage={"input_tokens": 9, "output_tokens": 9, "total_tokens": 18},
        raise_after=1,
    )
    _chunks, recorded = _run_stream(fake)
    assert recorded == [], "a call that failed mid-stream must never be recorded as having produced usage"


def _parse_sse_chunks(sse_chunks):
    import json as _json

    for raw in sse_chunks:
        for line in raw.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                yield _json.loads(line[len("data: "):])


TESTS = [
    test_local_candidate_enables_stream_usage,
    test_openai_candidate_enables_stream_usage,
    test_streaming_records_usage_from_terminal_chunk,
    test_streaming_without_usage_metadata_records_zero,
    test_streaming_error_mid_stream_never_records_usage,
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
