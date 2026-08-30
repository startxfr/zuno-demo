"""ADR-0528 (WP-090) regression coverage: `zuno.project_id` is set on both
`graph_run_span` and `api_request_span` when a project is present, and
absent when it is not.

The attribute was confirmed live against production Tempo on 2026-08-29
(see wp-090's dated note) but had no automated assertion anywhere - a
refactor could silently drop `app/telemetry.py`'s `if project_id:` branches
and CI would stay green. This suite closes that gap by reading the actual
exported span attributes, not by mocking the telemetry module away.

Run from this directory:

    python3 tests/test_telemetry.py
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app import telemetry  # noqa: E402


def _recorded_span(run_fn):
    """Installs a fresh in-memory exporter as telemetry._tracer, runs
    `run_fn`, and returns the single span it exported."""
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


def test_graph_run_span_carries_project_id_when_present() -> None:
    def _run():
        with telemetry.graph_run_span("session-1", run_id="run-1", project_id="proj-uuid-1"):
            pass

    span = _recorded_span(_run)
    assert span.attributes.get("zuno.project_id") == "proj-uuid-1"
    assert span.attributes.get("zuno.run_id") == "run-1"


def test_graph_run_span_omits_project_id_when_absent() -> None:
    def _run():
        with telemetry.graph_run_span("session-1", run_id="run-1"):
            pass

    span = _recorded_span(_run)
    assert "zuno.project_id" not in span.attributes


def test_api_request_span_carries_project_id_when_present() -> None:
    def _run():
        with telemetry.api_request_span("run-1", project_id="proj-uuid-1"):
            pass

    span = _recorded_span(_run)
    assert span.attributes.get("zuno.project_id") == "proj-uuid-1"


def test_api_request_span_omits_project_id_when_absent() -> None:
    def _run():
        with telemetry.api_request_span("run-1"):
            pass

    span = _recorded_span(_run)
    assert "zuno.project_id" not in span.attributes


TESTS = [
    test_graph_run_span_carries_project_id_when_present,
    test_graph_run_span_omits_project_id_when_absent,
    test_api_request_span_carries_project_id_when_present,
    test_api_request_span_omits_project_id_when_absent,
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
