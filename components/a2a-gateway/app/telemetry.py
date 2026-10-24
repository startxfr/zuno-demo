"""OpenTelemetry for the A2A gateway (ADR-0029): traces and metrics to the shared collector.

Same pattern as the other gateways (duplicated per service on purpose)."""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("a2a_gateway.telemetry")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318")


def init_telemetry(service_name: str = "a2a-gateway") -> None:
    resource = Resource.create({"service.name": service_name})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces")))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{OTEL_ENDPOINT}/v1/metrics"))],
        )
    )
    logger.info("telemetry initialised for %s", service_name)
