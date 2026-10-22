"""ADR-0566 (WP-147): tool_invoke joins the caller's trace.

A UnifAI run sends a W3C `traceparent` with each tool call; the gateway span
must continue that trace on both entry points (REST contract and /mcp) and keep
starting its own trace when the header is missing or malformed.

Run from the component directory:

    cd components/mcp-gateway && python3 tests/test_trace_context.py
"""
from __future__ import annotations

import os
import sys

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, COMPONENT_DIR)

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app import telemetry  # noqa: E402

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
TRACEPARENT = f"00-{TRACE_ID}-b7ad6b7169203331-01"


def _span(headers):
    """Drive the real dependency through FastAPI: a plain `def` dependency runs
    in a worker thread on a copy of the context, so its ContextVar would never
    reach the handler (found live on 2026-10-22)."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    api = FastAPI()

    @api.post("/probe", dependencies=[Depends(telemetry.adopt_incoming_trace_context)])
    async def probe():
        with telemetry.tool_invoke_span("confluence.page.search", "C2"):
            return {"ok": True}

    saved = telemetry._tracer
    telemetry._tracer = provider.get_tracer("test")
    try:
        assert TestClient(api).post("/probe", headers=headers).status_code == 200
    finally:
        telemetry._tracer = saved
    spans = exporter.get_finished_spans()
    assert len(spans) == 1, spans
    return spans[0]


def test_tool_invoke_joins_the_callers_trace() -> None:
    span = _span({"traceparent": TRACEPARENT})
    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert format(span.parent.span_id, "016x") == "b7ad6b7169203331"


def test_without_traceparent_the_span_is_its_own_root() -> None:
    span = _span({})
    assert span.parent is None
    assert format(span.context.trace_id, "032x") != TRACE_ID


def test_a_malformed_traceparent_is_ignored() -> None:
    assert _span({"traceparent": "00-not-a-trace-id-01"}).parent is None


TESTS = [
    test_tool_invoke_joins_the_callers_trace,
    test_without_traceparent_the_span_is_its_own_root,
    test_a_malformed_traceparent_is_ignored,
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
