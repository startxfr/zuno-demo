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
from typing import Iterator, List, Optional

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
        "zuno.rag_searches",
        description="RAG searches by outcome (ok/error), provider and requested domain set",
    )
    _result_count_histogram = meter.create_histogram(
        "zuno.rag_result_count",
        description="Number of hybrid-search results returned per query, by requested domain set",
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
    query: str,
    top_k: int,
    run_id: Optional[str] = None,
    domains: Optional[List[str]] = None,
) -> Iterator["SearchRecorder"]:
    """ADR-0543: run_id (the calling chat turn's id, forwarded by
    agent-runtime's rag_client as X-Zuno-Run-Id) is a span attribute only,
    never added to the zuno.rag_searches counter - unbounded cardinality.

    `domains` is the set the search will actually query, and becomes ONE
    label holding the sorted set joined by commas - never one point per
    domain. A search fans out across its domains and RRF-fuses them into a
    single result set, so there is no single domain to attribute a result
    count to, and emitting one point per domain would inflate the counter
    by the size of the request's domain list. That is precisely the defect
    zuno_bff_requests_total carries by recording one point per Keycloak
    group, and reproducing it here would be a poor way to fix it there.

    Cardinality is bounded by the domain COMBINATIONS callers request, not
    by their power set: each agent has a fixed authorized domain list, so
    this is a handful of values. The common case reads as a single domain
    name, because an empty request means knowledge.tech only.

    Without this label a zero result count is unreadable: knowledge.sales
    is deliberately empty until Salesforce ingestion lands in v0.7
    (ADR-0218), so "returned nothing" is correct there and alarming
    anywhere else, and the fleet-wide number cannot tell the two apart.
    """
    tracer = _tracer or trace.get_tracer("rag-service")
    start = time.monotonic()
    domain_label = ",".join(sorted(domains)) if domains else "unknown"
    with tracer.start_as_current_span("rag_search") as span:
        span.set_attribute("zuno.query_length", len(query))
        span.set_attribute("zuno.top_k", top_k)
        span.set_attribute("zuno.domains", domain_label)
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
                _search_counter.add(1, {
                    "outcome": recorder.outcome,
                    "provider": recorder.provider,
                    "domains": domain_label,
                })
            if _result_count_histogram is not None and recorder.outcome == "ok":
                _result_count_histogram.record(
                    recorder.result_count, {"domains": domain_label}
                )


class SearchRecorder:
    def __init__(self) -> None:
        self.outcome = "unknown"
        self.result_count = 0
        self.provider = "pgvector"
