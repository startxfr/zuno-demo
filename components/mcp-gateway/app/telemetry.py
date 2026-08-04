"""OpenTelemetry instrumentation (ADR-0029) — sends OTLP traces/metrics to
the shared Collector installed by ansible/roles/observability
(`zuno-otel-collector-collector.zuno-platform.svc`).

Same pattern as components/agent-runtime/app/telemetry.py (that file's
docstring explains why this is duplicated per-service rather than shared
across independently-deployed images); this one records tool-invocation
counts/latency/outcome instead of model token usage/cost, since the
gateway's own billable/notable operation is authorizing+proxying a tool
call, not a model call.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("mcp_gateway.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-platform.svc:4318",
)

_tracer: Optional[trace.Tracer] = None
_invoke_counter = None


def init_telemetry(service_name: str = "mcp-gateway") -> None:
    global _tracer, _invoke_counter

    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{OTEL_ENDPOINT}/v1/metrics")
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    _tracer = trace.get_tracer(service_name)
    meter = metrics.get_meter(service_name)
    _invoke_counter = meter.create_counter(
        "zuno.tool_invocations",
        description="MCP tool invocations by tool, mcp_server and outcome (allowed/denied/error)",
    )

    logger.info("telemetry initialized: service=%s otlp_endpoint=%s", service_name, OTEL_ENDPOINT)


@contextmanager
def tool_invoke_span(tool_name: str, classification: str) -> Iterator["ToolInvokeRecorder"]:
    """Wraps one tool invocation end to end (policy decision + downstream
    call): records a `tool_invoke` span and the zuno.tool_invocations
    counter once the caller sets `.outcome`/`.mcp_server` on the recorder.
    """
    tracer = _tracer or trace.get_tracer("mcp-gateway")
    start = time.monotonic()
    with tracer.start_as_current_span("tool_invoke") as span:
        span.set_attribute("zuno.tool", tool_name)
        span.set_attribute("zuno.classification", classification)
        recorder = ToolInvokeRecorder()
        try:
            yield recorder
        except Exception as exc:
            # Only fall back to the generic "error" outcome if the caller
            # hasn't already classified it more precisely (e.g. "denied",
            # "unknown_tool") before raising — an HTTPException for a policy
            # denial is expected control flow, not an unhandled error.
            if recorder.outcome == "unknown":
                recorder.outcome = "error"
            span.record_exception(exc)
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            span.set_attribute("zuno.latency_ms", latency_ms)
            span.set_attribute("zuno.outcome", recorder.outcome)
            if recorder.mcp_server:
                span.set_attribute("zuno.mcp_server", recorder.mcp_server)
            if recorder.reason:
                span.set_attribute("zuno.reason", recorder.reason)
            if _invoke_counter is not None:
                _invoke_counter.add(
                    1,
                    {
                        "tool": tool_name,
                        "mcp_server": recorder.mcp_server or "unknown",
                        "outcome": recorder.outcome,
                    },
                )


class ToolInvokeRecorder:
    def __init__(self) -> None:
        self.outcome = "unknown"
        self.mcp_server: Optional[str] = None
        self.reason: Optional[str] = None
