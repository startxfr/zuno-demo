"""OpenTelemetry service registration for the Agent Runtime (ADR-0029).

Model-call-level telemetry (per-provider spans, token/cost metrics) moved
to components/ai-gateway/app/telemetry.py as part of ADR-0009's split -
that service is now the one that actually knows the provider and makes the
call, so it's the correct owner of that detail (see its README's
"Observability" section). This module initializes the OTel SDK, plus one
span helper (graph_run_span, WP-24) around the LangGraph workflow itself -
ADR-0205's acceptance bullet "traces show whether a response used indexed
knowledge, live verification, or both" needs a span attribute the
non-streaming chat handler can set once the graph run completes.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("agent_runtime.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318",
)

_tracer: Optional[trace.Tracer] = None


def init_telemetry(service_name: str = "agent-runtime") -> None:
    global _tracer

    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)
    _tracer = trace.get_tracer(service_name)

    logger.info("telemetry initialized: service=%s otlp_endpoint=%s", service_name, OTEL_ENDPOINT)


class GraphRunRecorder:
    def __init__(self) -> None:
        self.source_mode = "none"
        self.live_read_trigger_reason: Optional[str] = None
        self.outcome = "unknown"


@contextmanager
def graph_run_span(session_id: str) -> Iterator[GraphRunRecorder]:
    """WP-24 (ADR-0205): wraps one LangGraph run, recording the same
    no-silent-substitution signals the response body carries -
    zuno.source_mode ("indexed"/"live"/"both"/"none") and, when present,
    why a live-read was triggered this turn - so a trace answers the
    acceptance bullet without needing to correlate against the HTTP
    response body separately."""
    tracer = _tracer or trace.get_tracer("agent-runtime")
    start = time.monotonic()
    with tracer.start_as_current_span("agent_graph_run") as span:
        span.set_attribute("zuno.session_id", session_id)
        recorder = GraphRunRecorder()
        try:
            yield recorder
            recorder.outcome = "ok"
        except Exception as exc:
            recorder.outcome = "error"
            span.record_exception(exc)
            raise
        finally:
            span.set_attribute("zuno.latency_ms", (time.monotonic() - start) * 1000.0)
            span.set_attribute("zuno.outcome", recorder.outcome)
            span.set_attribute("zuno.source_mode", recorder.source_mode)
            if recorder.live_read_trigger_reason:
                span.set_attribute("zuno.live_read_trigger_reason", recorder.live_read_trigger_reason)
