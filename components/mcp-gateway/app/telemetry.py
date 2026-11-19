"""OpenTelemetry instrumentation (ADR-0029) - sends OTLP traces/metrics to
the shared Collector installed by ansible/roles/observability
(`zuno-otel-collector-collector.zuno-monitoring.svc`).

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
from contextvars import ContextVar
from typing import Iterable, Iterator, List, Optional

from fastapi import Request
from opentelemetry import context as otel_context
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("mcp_gateway.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318",
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


# WP-313 step 5: the OTel counter exists only from its first event, so after a restart rate()/increase() miss the first
# invocations of each label set. The known sets are created at 0 at startup: one per tool of the tool policy and per outcome
# the code emits. Bounded: tools, their capability and server come from the loaded files, nothing from a caller.
ZERO_INIT_ENV = "TELEMETRY_ZERO_INIT"
INVOKE_OUTCOMES = ("allowed", "denied", "error")


def zero_init_enabled() -> bool:
    return os.getenv(ZERO_INIT_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def zero_label_sets(tools: Iterable[tuple]) -> List[dict]:
    """The label sets to create at 0 for `tools`, an iterable of (tool, capability, mcp_server). Pure, so a test can bound it."""
    out = []
    for tool, capability, mcp_server in sorted(set(tools)):
        for outcome in INVOKE_OUTCOMES:
            out.append({"tool": tool, "capability": capability or "unknown", "mcp_server": mcp_server or "unknown", "outcome": outcome})
    return out


def prime_zero_counters(tools: Iterable[tuple]) -> int:
    """Creates the known tool-invocation label sets at 0 (TELEMETRY_ZERO_INIT=0 turns it off); returns how many. Never raises."""
    if not zero_init_enabled() or _invoke_counter is None:
        return 0
    n = 0
    try:
        for labels in zero_label_sets(tools):
            _invoke_counter.add(0, labels)
            n += 1
    except Exception:  # noqa: BLE001
        logger.debug("zero-initialising the counter failed", exc_info=True)
    logger.info("telemetry: %d tool-invocation series created at 0", n)
    return n


# ADR-0566 (WP-147): the W3C trace context an agent platform (UnifAI) sent with
# the request, so `tool_invoke` joins the caller's trace instead of starting a
# new root. A ContextVar because the span is opened several frames below the
# handler, shared by the REST contract and the /mcp front-door.
_incoming_trace_context: ContextVar[Optional[otel_context.Context]] = ContextVar(
    "zuno_incoming_trace_context", default=None
)


# WP-306 (ADR-0624): stress traffic is tagged by the optional request header X-Zuno-Traffic and recorded on the SPANS
# only (`zuno.traffic`), never as a metric label. Only the values below are kept: any other text is dropped, so a caller
# cannot put arbitrary content on a span. Query it in Tempo with { span.zuno.traffic = "stresstest" }.
_ALLOWED_TRAFFIC = frozenset({"stresstest"})
_caller_traffic: ContextVar[str] = ContextVar("zuno_caller_traffic", default="")


def traffic_label(value: Optional[str]) -> str:
    """The allow-listed traffic tag of a header value, or "" (untagged)."""
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in _ALLOWED_TRAFFIC else ""


def set_caller_traffic(value: Optional[str]) -> None:
    """Remember this request's traffic tag for the spans. Set by adopt_incoming_trace_context, so one place covers every
    endpoint and a request without the header resets it."""
    _caller_traffic.set(traffic_label(value))


async def adopt_incoming_trace_context(request: Request) -> None:
    """FastAPI dependency: remember the caller's `traceparent`/`tracestate`.

    `async` on purpose: a plain `def` dependency runs in a worker thread on a
    copy of the context, so the ContextVar it sets would never reach the handler.

    Nothing else is read. A request without a valid `traceparent` leaves the
    variable empty, which keeps the previous behaviour (own trace root).
    """
    set_caller_traffic(request.headers.get("x-zuno-traffic"))  # WP-306: the span-only stress tag
    carrier = {k: v for k, v in request.headers.items() if k.lower() in ("traceparent", "tracestate")}
    ctx = extract(carrier) if carrier else None
    if ctx is not None and trace.get_current_span(ctx).get_span_context().is_valid:
        _incoming_trace_context.set(ctx)
    else:
        _incoming_trace_context.set(None)


@contextmanager
def tool_invoke_span(
    tool_name: str,
    classification: str,
    run_id: Optional[str] = None,
    caller_sub: Optional[str] = None,
    delegated_by: Optional[str] = None,
    delegation_depth: Optional[int] = None,
) -> Iterator["ToolInvokeRecorder"]:
    """Wraps one tool invocation end to end (policy decision + downstream
    call): records a `tool_invoke` span and the zuno.tool_invocations
    counter once the caller sets `.outcome`/`.mcp_server` on the recorder.

    ADR-0543: run_id (the calling chat turn's id, forwarded by
    agent-runtime's mcp_client as X-Zuno-Run-Id) is a span attribute only,
    never added to the zuno.tool_invocations counter - unbounded
    cardinality on a Prometheus counter.
    """
    tracer = _tracer or trace.get_tracer("mcp-gateway")
    start = time.monotonic()
    with tracer.start_as_current_span("tool_invoke", context=_incoming_trace_context.get()) as span:
        span.set_attribute("zuno.tool", tool_name)
        span.set_attribute("zuno.classification", classification)
        if run_id:
            span.set_attribute("zuno.run_id", run_id)
        traffic = _caller_traffic.get()
        if traffic:
            span.set_attribute("zuno.traffic", traffic)
        # ADR-0403 clause 6: the initiating user and, for a delegated call, the
        # chain. Span attributes only: neither belongs on a low-cardinality counter.
        if caller_sub:
            span.set_attribute("zuno.user_sub", caller_sub)
        if delegated_by:
            span.set_attribute("zuno.delegated_by", delegated_by)
            span.set_attribute("zuno.delegation_depth", delegation_depth or 0)
        recorder = ToolInvokeRecorder()
        try:
            yield recorder
        except Exception as exc:
            # Only fall back to the generic "error" outcome if the caller
            # hasn't already classified it more precisely (e.g. "denied",
            # "unknown_tool") before raising - an HTTPException for a policy
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
            # ADR-0116 Operational considerations: traces record both the
            # logical capability and the resolved backend binding.
            if recorder.capability:
                span.set_attribute("zuno.capability", recorder.capability)
            if recorder.binding:
                span.set_attribute("zuno.binding", recorder.binding)
            # ADR-0208 (WP-26): audit records carry the auth_mode a
            # binding declared alongside the existing subject/capability/
            # binding fields - never token material (that never reaches
            # this recorder at all; see app/delegation.py).
            if recorder.auth_mode:
                span.set_attribute("zuno.auth_mode", recorder.auth_mode)
            if recorder.reason:
                span.set_attribute("zuno.reason", recorder.reason)
            if _invoke_counter is not None:
                _invoke_counter.add(
                    1,
                    {
                        "tool": tool_name,
                        "capability": recorder.capability or "unknown",
                        "mcp_server": recorder.mcp_server or "unknown",
                        "outcome": recorder.outcome,
                    },
                )


class ToolInvokeRecorder:
    def __init__(self) -> None:
        self.outcome = "unknown"
        self.mcp_server: Optional[str] = None
        self.reason: Optional[str] = None
        # ADR-0116: logical capability ID + resolved backend name.
        self.capability: Optional[str] = None
        self.binding: Optional[str] = None
        # ADR-0208 (WP-26): the binding's declared auth_mode - never a
        # token/credential value.
        self.auth_mode: Optional[str] = None
