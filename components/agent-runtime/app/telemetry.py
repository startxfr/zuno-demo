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

ADR-0534/WP-113 adds this service's ONE metrics concern: guardrails
observation counters. Model-call metrics stay in ai-gateway per the split
above; the observe-only guardrails hook (app/clients/guardrails_client.py)
is agent-runtime's own boundary, so its counters live here.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Iterable, Iterator, Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("agent_runtime.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318",
)

_tracer: Optional[trace.Tracer] = None
_guardrails_eval_counter = None
_guardrails_detection_counter = None


def init_telemetry(service_name: str = "agent-runtime") -> None:
    global _tracer, _guardrails_eval_counter, _guardrails_detection_counter

    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)
    _tracer = trace.get_tracer(service_name)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{OTEL_ENDPOINT}/v1/metrics")
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter(service_name)
    _guardrails_eval_counter = meter.create_counter(
        "zuno.guardrails_evaluations",
        description="Observe-only guardrails evaluations of agent exchanges, "
        "by agent and outcome (clean/detected/unavailable) - ADR-0534/WP-113",
    )
    _guardrails_detection_counter = meter.create_counter(
        "zuno.guardrails_detections",
        description="Individual guardrails detections (observe-only, response "
        "never altered), by agent and detection name - ADR-0534/WP-113",
    )

    logger.info("telemetry initialized: service=%s otlp_endpoint=%s", service_name, OTEL_ENDPOINT)


def record_guardrails_evaluation(
    agent: str, outcome: str, detections: Iterable[str] = ()
) -> None:
    """`outcome` is one of "clean", "detected", "unavailable"; `detections`
    the detection names of a "detected" outcome ("email_address",
    "custom-regex", ...) - a bounded set, the detector's own vocabulary.
    Never raises: the observe-only contract extends to its own metrics."""
    try:
        if _guardrails_eval_counter is not None:
            _guardrails_eval_counter.add(1, {"agent": agent, "outcome": outcome})
        if _guardrails_detection_counter is not None:
            for name in detections:
                _guardrails_detection_counter.add(
                    1, {"agent": agent, "detection": name or "unknown"}
                )
    except Exception:  # noqa: BLE001 - metrics must never affect a response
        logger.debug("guardrails metric recording failed", exc_info=True)


class GraphRunRecorder:
    def __init__(self) -> None:
        self.source_mode = "none"
        self.live_read_trigger_reason: Optional[str] = None
        self.outcome = "unknown"

    def mark_error(self) -> None:
        """For a caller (e.g. _stream_chat) that handles its own errors
        internally - yielding a client-facing SSE error event rather than
        raising - so the span still reports what actually happened instead
        of defaulting to "ok" just because no exception crossed the `with`
        boundary. Mirrors ApiRequestRecorder.mark_error()'s same rationale.
        """
        self.outcome = "error"


@contextmanager
def graph_run_span(
    session_id: str,
    agent: Optional[str] = None,
    graph_shape: Optional[str] = None,
    run_id: Optional[str] = None,
    # ADR-0528: the engagement this run belonged to. Span attribute only,
    # never a metric label - projects are created ad hoc, so their
    # cardinality is unbounded, the same reasoning run_id already carries.
    project_id: Optional[str] = None,
) -> Iterator[GraphRunRecorder]:
    """WP-24 (ADR-0205): wraps one LangGraph run, recording the same
    no-silent-substitution signals the response body carries -
    zuno.source_mode ("indexed"/"live"/"both"/"none") and, when present,
    why a live-read was triggered this turn - so a trace answers the
    acceptance bullet without needing to correlate against the HTTP
    response body separately.

    WP-30/ADR-0342: also records which agent and which graph shape served
    this run - the Operational considerations requirement that "tracing
    must record which graph shape served a given request, alongside the
    existing agent/task identifiers."

    ADR-0517: run_id (distinct from session_id, the caller-supplied value
    above) is the LangGraph thread id - tagging it here is what lets the
    per-run resource dashboard find this span via TraceQL.
    """
    tracer = _tracer or trace.get_tracer("agent-runtime")
    start = time.monotonic()
    with tracer.start_as_current_span("agent_graph_run") as span:
        span.set_attribute("zuno.session_id", session_id)
        if agent:
            span.set_attribute("zuno.agent", agent)
        if graph_shape:
            span.set_attribute("zuno.graph_shape", graph_shape)
        if run_id:
            span.set_attribute("zuno.run_id", run_id)
        if project_id:
            span.set_attribute("zuno.project_id", project_id)  # ADR-0528
        recorder = GraphRunRecorder()
        try:
            yield recorder
            if recorder.outcome == "unknown":
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


class ApiRequestRecorder:
    def __init__(self) -> None:
        self.outcome = "unknown"

    def mark_error(self) -> None:
        """For a caller (e.g. _stream_chat) that handles its own errors
        internally - yielding a client-facing SSE error event rather than
        raising - so the span still reports what actually happened instead
        of defaulting to "ok" just because no exception crossed the `with`
        boundary.
        """
        self.outcome = "error"


@contextmanager
def api_request_span(
    run_id: str,
    agent: Optional[str] = None,
    request_id: Optional[str] = None,
    project_id: Optional[str] = None,  # ADR-0528
) -> Iterator[ApiRequestRecorder]:
    """ADR-0517: wraps the whole agent_chat handler body (from run_id
    resolution through the response), enclosing agent_graph_run on the
    non-streaming path and _stream_chat's execution on the streaming path.
    Distinguishes "time spent in agent-runtime's own request handling
    (auth, history load/compaction, response assembly)" from
    "time spent inside the LangGraph run itself" on the per-run resource
    dashboard - the two spans overlap in time by design.
    """
    tracer = _tracer or trace.get_tracer("agent-runtime")
    start = time.monotonic()
    with tracer.start_as_current_span("api_request") as span:
        span.set_attribute("zuno.run_id", run_id)
        if agent:
            span.set_attribute("zuno.agent", agent)
        if request_id:
            span.set_attribute("zuno.request_id", request_id)
        if project_id:
            span.set_attribute("zuno.project_id", project_id)  # ADR-0528
        recorder = ApiRequestRecorder()
        try:
            yield recorder
            if recorder.outcome == "unknown":
                recorder.outcome = "ok"
        except Exception as exc:
            recorder.outcome = "error"
            span.record_exception(exc)
            raise
        finally:
            span.set_attribute("zuno.latency_ms", (time.monotonic() - start) * 1000.0)
            span.set_attribute("zuno.outcome", recorder.outcome)
