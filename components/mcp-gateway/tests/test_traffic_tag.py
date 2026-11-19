"""WP-306 (ADR-0624): X-Zuno-Traffic: stresstest is a span attribute (zuno.traffic) on tool_invoke, on both entry points'
shared dependency, and never a metric label. Any other value is dropped so a caller cannot put arbitrary text on a span.

Run from the component directory (OTel SDK enabled, exporter at a closed port so it fails fast):

    cd components/mcp-gateway && OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:9 python3 tests/test_traffic_tag.py
"""
from __future__ import annotations

import inspect
import os
import sys

COMPONENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, COMPONENT_DIR)

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app import telemetry  # noqa: E402


def _span(headers):
    """Drive the real dependency through FastAPI, as test_trace_context.py does."""
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


def test_the_stresstest_tag_is_on_the_tool_invoke_span() -> None:
    assert _span({"X-Zuno-Traffic": "stresstest"}).attributes.get("zuno.traffic") == "stresstest"


def test_the_tag_is_normalised() -> None:
    assert _span({"X-Zuno-Traffic": " StressTest "}).attributes.get("zuno.traffic") == "stresstest"


def test_an_unknown_value_or_no_header_leaves_no_attribute() -> None:
    for headers in ({"X-Zuno-Traffic": "production"}, {"X-Zuno-Traffic": "<script>"}, {"X-Zuno-Traffic": ""}, {}):
        assert "zuno.traffic" not in _span(headers).attributes, headers


def test_the_tag_is_never_a_metric_label() -> None:
    for line in inspect.getsource(telemetry).splitlines():
        if "traffic" in line and ("add(1" in line or "record(" in line or '"outcome"' in line):
            raise AssertionError(f"the traffic tag reached a metric call: {line.strip()}")


TESTS = [obj for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]


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
