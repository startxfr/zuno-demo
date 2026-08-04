"""OpenTelemetry instrumentation for model usage, cost and traces (ADR-0029).

Sends OTLP traces/metrics to the shared Collector installed by
ansible/roles/observability (`zuno-otel-collector-collector.zuno-platform.svc`).
Reference implementation for this repo — `components/mcp-gateway` and
`components/rag-service` should adopt the same pattern (init_telemetry() at
startup, a span per externally-billed or notable operation); that wiring is
not yet done in those two services (see ansible/roles/observability/README.md).

Cost estimates are approximate, demo-grade USD-per-1K-token rates, not a
billing-accurate figure — good enough to demonstrate ADR-0029's "cost"
dimension is wired through, not a finance-grade cost model.
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

logger = logging.getLogger("agent_runtime.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-platform.svc:4318",
)

# USD per 1,000 tokens (input, output). Approximate public pricing at time of
# writing; update as needed — this is a demo cost signal, not a billing feed.
_COST_PER_1K_TOKENS = {
    "local": (0.0, 0.0),  # runs on already-provisioned GPU capacity
    "openai": (0.00015, 0.0006),
    "gemini": (0.00125, 0.005),
    "anthropic": (0.003, 0.015),
    "mistral": (0.002, 0.006),
}

_tracer: Optional[trace.Tracer] = None
_model_call_counter = None
_token_counter = None
_cost_counter = None


def init_telemetry(service_name: str = "agent-runtime") -> None:
    global _tracer, _model_call_counter, _token_counter, _cost_counter

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
    _model_call_counter = meter.create_counter(
        "zuno.model_calls", description="Number of model calls, by provider and outcome"
    )
    _token_counter = meter.create_counter(
        "zuno.model_tokens", description="Prompt/completion tokens consumed, by provider"
    )
    _cost_counter = meter.create_counter(
        "zuno.model_cost_usd", description="Estimated USD cost of model calls, by provider"
    )

    logger.info("telemetry initialized: service=%s otlp_endpoint=%s", service_name, OTEL_ENDPOINT)


def _estimate_cost_usd(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_rate, out_rate = _COST_PER_1K_TOKENS.get(provider, (0.0, 0.0))
    return (prompt_tokens / 1000.0) * in_rate + (completion_tokens / 1000.0) * out_rate


@contextmanager
def model_call_span(provider: str, model: str, classification: str) -> Iterator["ModelCallRecorder"]:
    """Wraps one model invocation: records a span plus the
    zuno.model_calls / zuno.model_tokens / zuno.model_cost_usd metrics
    (ADR-0029) once `.record_usage()` is called on the yielded recorder, or
    just the outcome/latency if the caller never has token counts (e.g. a
    failed call).
    """
    tracer = _tracer or trace.get_tracer("agent-runtime")
    start = time.monotonic()
    with tracer.start_as_current_span("model_call") as span:
        span.set_attribute("zuno.provider", provider)
        span.set_attribute("zuno.model", model)
        span.set_attribute("zuno.classification", classification)
        recorder = ModelCallRecorder(provider=provider)
        try:
            yield recorder
            outcome = "success"
        except Exception as exc:
            outcome = "error"
            span.record_exception(exc)
            span.set_attribute("zuno.error", str(exc))
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            span.set_attribute("zuno.latency_ms", latency_ms)
            span.set_attribute("zuno.outcome", outcome)
            attrs = {"provider": provider, "model": model, "outcome": outcome}
            if _model_call_counter is not None:
                _model_call_counter.add(1, attrs)
            if recorder.prompt_tokens or recorder.completion_tokens:
                span.set_attribute("zuno.prompt_tokens", recorder.prompt_tokens)
                span.set_attribute("zuno.completion_tokens", recorder.completion_tokens)
                cost = _estimate_cost_usd(provider, recorder.prompt_tokens, recorder.completion_tokens)
                span.set_attribute("zuno.estimated_cost_usd", cost)
                if _token_counter is not None:
                    _token_counter.add(recorder.prompt_tokens, {**attrs, "kind": "prompt"})
                    _token_counter.add(recorder.completion_tokens, {**attrs, "kind": "completion"})
                if _cost_counter is not None:
                    _cost_counter.add(cost, attrs)


class ModelCallRecorder:
    def __init__(self, provider: str):
        self.provider = provider
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
