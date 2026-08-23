"""OpenTelemetry instrumentation (ADR-0029) - sends OTLP traces/metrics to
the shared Collector installed by ansible/roles/observability
(`zuno-otel-collector-collector.zuno-monitoring.svc`).

Same pattern as components/agent-runtime/app/telemetry.py and
components/mcp-gateway/app/telemetry.py (duplicated per-service rather than
shared across independently-deployed images - see agent-runtime's
docstring); this one records search latency/result-count instead of model
tokens or tool-authorization outcomes.
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

logger = logging.getLogger("rag_service.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318",
)

_tracer: Optional[trace.Tracer] = None
_search_counter = None
_result_count_histogram = None
_freshness_lag_histogram = None


def init_telemetry(service_name: str = "rag-service") -> None:
    global _tracer, _search_counter, _result_count_histogram, _freshness_lag_histogram

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
    _search_counter = meter.create_counter(
        "zuno.rag_searches", description="RAG searches by outcome (ok/error)"
    )
    _result_count_histogram = meter.create_histogram(
        "zuno.rag_result_count", description="Number of hybrid-search results returned per query"
    )
    # ADR-0109/WP-24: "metrics expose now - indexed_at ... with alerting
    # against domain objectives" - one histogram, sliced by the `domain`
    # attribute at record time (see app/search.py:record_freshness_lag),
    # rather than one metric per domain - domains are data, not a fixed
    # set this module should know about.
    _freshness_lag_histogram = meter.create_histogram(
        "zuno.rag_freshness_lag_seconds",
        unit="s",
        description="Age (now - metadata.indexed_at) of each returned chunk, labeled by domain",
    )

    logger.info("telemetry initialized: service=%s otlp_endpoint=%s", service_name, OTEL_ENDPOINT)


def record_freshness_lag(domain: str, lag_seconds: float) -> None:
    if _freshness_lag_histogram is not None:
        _freshness_lag_histogram.record(lag_seconds, {"domain": domain})


@contextmanager
def search_span(
    query: str, top_k: int, run_id: Optional[str] = None
) -> Iterator["SearchRecorder"]:
    """ADR-0517: run_id (the calling chat turn's id, forwarded by
    agent-runtime's rag_client as X-Zuno-Run-Id) is a span attribute only,
    never added to the zuno.rag_searches counter - unbounded cardinality.
    """
    tracer = _tracer or trace.get_tracer("rag-service")
    start = time.monotonic()
    with tracer.start_as_current_span("rag_search") as span:
        span.set_attribute("zuno.query_length", len(query))
        span.set_attribute("zuno.top_k", top_k)
        if run_id:
            span.set_attribute("zuno.run_id", run_id)
        recorder = SearchRecorder()
        try:
            yield recorder
            recorder.outcome = "ok"
        except Exception as exc:
            recorder.outcome = "error"
            span.record_exception(exc)
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            span.set_attribute("zuno.latency_ms", latency_ms)
            span.set_attribute("zuno.outcome", recorder.outcome)
            span.set_attribute("zuno.result_count", recorder.result_count)
            # ADR-0322 Operational considerations: "Provider selection must
            # be observable so traces identify whether a request used
            # native pgvector retrieval or OGX-backed retrieval."
            span.set_attribute("zuno.provider", recorder.provider)
            if _search_counter is not None:
                _search_counter.add(1, {"outcome": recorder.outcome, "provider": recorder.provider})
            if _result_count_histogram is not None and recorder.outcome == "ok":
                _result_count_histogram.record(recorder.result_count)


class SearchRecorder:
    def __init__(self) -> None:
        self.outcome = "unknown"
        self.result_count = 0
        self.provider = "pgvector"
