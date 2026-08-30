"""ADR-0528 (WP-090) regression coverage: `zuno.project_id` is set on the
`model_call` span when a project is present, and absent when it is not, on
both the non-streaming and streaming paths.

Confirmed live against production Tempo on 2026-08-29 (wp-090's dated
note) but never asserted anywhere - a refactor of model_call_span's
`if project_id:` branch, or of app/main.py's two call sites, would drop the
attribute silently. This suite reads the actual exported span, not a mock.

Run from this directory:

    python3 tests/test_telemetry.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app import telemetry  # noqa: E402
from app import main as app_main  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402


def _recorded_span(run_fn):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    saved = telemetry._tracer
    telemetry._tracer = provider.get_tracer("test")
    try:
        run_fn()
    finally:
        telemetry._tracer = saved
    spans = exporter.get_finished_spans()
    assert len(spans) == 1, spans
    return spans[0]


def test_model_call_span_carries_project_id_when_present() -> None:
    def _run():
        with telemetry.model_call_span("local", "qwen3.5-9b", "C2", run_id="run-1", project_id="proj-uuid-1"):
            pass

    span = _recorded_span(_run)
    assert span.attributes.get("zuno.project_id") == "proj-uuid-1"
    assert span.attributes.get("zuno.run_id") == "run-1"


def test_model_call_span_omits_project_id_when_absent() -> None:
    def _run():
        with telemetry.model_call_span("local", "qwen3.5-9b", "C2", run_id="run-1"):
            pass

    span = _recorded_span(_run)
    assert "zuno.project_id" not in span.attributes


async def _fake_stream(candidates, request_id, project_id):
    class _FakeStreamingModel:
        async def astream(self, _messages):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content="hi")

    with mock.patch.object(app_main, "chat_model_for", return_value=_FakeStreamingModel()), \
         mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "test-model"}):
        async for _chunk in app_main._stream_completion(candidates, "C1", [], request_id, project_id=project_id):
            pass


def test_streaming_path_carries_project_id_when_present() -> None:
    candidates = [ProviderCandidate(name="local", kind="local")]

    def _run():
        asyncio.run(_fake_stream(candidates, "req-1", "proj-uuid-1"))

    span = _recorded_span(_run)
    assert span.attributes.get("zuno.project_id") == "proj-uuid-1"


def test_streaming_path_omits_project_id_when_absent() -> None:
    candidates = [ProviderCandidate(name="local", kind="local")]

    def _run():
        asyncio.run(_fake_stream(candidates, "req-1", None))

    span = _recorded_span(_run)
    assert "zuno.project_id" not in span.attributes


TESTS = [
    test_model_call_span_carries_project_id_when_present,
    test_model_call_span_omits_project_id_when_absent,
    test_streaming_path_carries_project_id_when_present,
    test_streaming_path_omits_project_id_when_absent,
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
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
