"""OpenTelemetry service registration for the Agent Runtime (ADR-0029).

Model-call-level telemetry (per-provider spans, token/cost metrics) moved
to components/ai-gateway/app/telemetry.py as part of ADR-0009's split —
that service is now the one that actually knows the provider and makes the
call, so it's the correct owner of that detail (see its README's
"Observability" section). This module only initializes the OTel SDK so
this service's own future spans (e.g. around the LangGraph workflow itself)
have a resource/exporter to attach to — nothing calls a span helper from
here today.
"""
from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("agent_runtime.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-platform.svc:4318",
)


def init_telemetry(service_name: str = "agent-runtime") -> None:
    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    logger.info("telemetry initialized: service=%s otlp_endpoint=%s", service_name, OTEL_ENDPOINT)
