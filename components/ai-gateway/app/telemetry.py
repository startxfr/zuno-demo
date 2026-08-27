"""OpenTelemetry instrumentation for model usage, cost and traces (ADR-0029).

Moved here from components/agent-runtime/app/telemetry.py as part of
ADR-0009's split: this service is now the one that actually knows the
downstream provider and makes the call, so it's the correct owner of this
telemetry (agent-runtime's own copy was removed, not duplicated - see its
README's "Observability" section).

Sends OTLP traces/metrics to the shared Collector installed by
ansible/roles/observability (`zuno-otel-collector-collector.zuno-monitoring.svc`).

Cost estimates are approximate and demo-grade, not a billing-accurate
figure - good enough to demonstrate ADR-0029's "cost" dimension is wired
through, not a finance-grade cost model. Remote/SaaS providers are priced
per-1K-token (`_COST_PER_1K_TOKENS`); local providers have no per-token
meter, so they're priced per-second of call duration
(`_COST_PER_SECOND_LOCAL`), apportioned from this cluster's actual GPU
node economics (ADR-0351) - see that table's comment for the derivation.
Budgets/quotas (also named in ADR-0009's decision text) are NOT
implemented - this only *measures* cost, it doesn't enforce a ceiling.
See README.md.
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

logger = logging.getLogger("ai_gateway.telemetry")

OTEL_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://zuno-otel-collector-collector.zuno-monitoring.svc:4318",
)

# USD per 1,000 tokens (input, output), for remote/SaaS providers billed
# by token. Approximate public pricing at time of writing; update as
# needed - this is a demo cost signal, not a billing feed. Local
# providers ("local", "local-gpt-oss") are NOT priced here - they have no
# per-token meter, only GPU time. See _COST_PER_SECOND_LOCAL below.
_COST_PER_1K_TOKENS = {
    "openai": (0.00015, 0.0006),
    "gemini": (0.00125, 0.005),
    "anthropic": (0.003, 0.015),
    "mistral": (0.002, 0.006),
}

# Indicative us-east-1 on-demand $/hour by node type, from ADR-0351's cost
# table - kept separate from the per-second rates below so the MIG-share
# derivation stays legible/updatable without redoing the arithmetic by hand.
_NODE_USD_PER_HOUR = {
    "g7e.4xlarge": 4.00,  # shared MIG host: "local" gets a 2g.48gb slice = 50% of the 96GB card
    "g7e.2xlarge": 3.36,  # dedicated whole-GPU host for "local-gpt-oss" (unmanaged, not MIG-shared)
}

# USD per SECOND of call duration, for local providers. One float per
# provider (not an (in, out) tuple like _COST_PER_1K_TOKENS) - there's no
# per-token meter to split; the GPU is billed by wall clock regardless of
# tokens produced. Every `kind: local` entry in
# platform/ai-gateway/provider-routing.yaml MUST have a row here or it
# silently prices as $0 (see _estimate_cost_usd's fallback) - exactly the
# bug this table fixes for "local-gpt-oss", which used to fall through
# _COST_PER_1K_TOKENS's default by accident, not by design.
#
# Caveat: policies/model-routing/model-routing-policy.yaml's
# `cost_ceiling_usd_per_1k` doc comment assumes zuno.model_cost_usd is
# token-proportional. That's no longer true for local providers priced
# from this table - not a live bug today (that policy's `objectives:` is
# empty), but a trap for whoever adds the first local-preferring ceiling.
_COST_PER_SECOND_LOCAL = {
    "local": (_NODE_USD_PER_HOUR["g7e.4xlarge"] * 0.5) / 3600.0,  # ~$0.000556/s (qwen3.6-27b-instruct, half the shared card)
    "local-gpt-oss": _NODE_USD_PER_HOUR["g7e.2xlarge"] / 3600.0,   # ~$0.000933/s (gpt-oss-20b, whole card)
    # ADR-0521 (WP-076): the MaaS-transport siblings burn the exact same
    # GPU seconds on the exact same cards - transport never changes the
    # economics. Keyed separately because this table is keyed by PROVIDER
    # name (candidate.name), and a via_maas call reports under its own
    # entry name - without these rows every MaaS-routed local call
    # silently fell through to zero cost.
    "local-maas": (_NODE_USD_PER_HOUR["g7e.4xlarge"] * 0.5) / 3600.0,
    "local-gpt-oss-maas": _NODE_USD_PER_HOUR["g7e.2xlarge"] / 3600.0,
    # ADR-0526 (WP-087): the French urban-register variant and its own
    # unmodified base, on the same shared MIG host as "local" - priced
    # from their slice sizes, not from a node type of their own. The
    # variant takes a 2g.48gb slice (50% of the 96GB card, same share and
    # therefore same rate as "local"); the base takes a 1g.24gb slice
    # (25%). Each carries its -maas sibling at the identical rate:
    # transport never changes the economics, and this table is keyed by
    # PROVIDER name (candidate.name), so a via_maas call that reports
    # under its own entry name would meter at $0 without its own row.
    "local-wesh": (_NODE_USD_PER_HOUR["g7e.4xlarge"] * 0.5) / 3600.0,
    "local-wesh-maas": (_NODE_USD_PER_HOUR["g7e.4xlarge"] * 0.5) / 3600.0,
    "local-qwen35": (_NODE_USD_PER_HOUR["g7e.4xlarge"] * 0.25) / 3600.0,
    "local-qwen35-maas": (_NODE_USD_PER_HOUR["g7e.4xlarge"] * 0.25) / 3600.0,
}

_tracer: Optional[trace.Tracer] = None
_model_call_counter = None
_token_counter = None
_cost_counter = None
_cache_lookup_counter = None
_model_call_duration_histogram = None


def init_telemetry(service_name: str = "ai-gateway") -> None:
    global _tracer, _model_call_counter, _token_counter, _cost_counter, _cache_lookup_counter
    global _model_call_duration_histogram

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
    _cache_lookup_counter = meter.create_counter(
        "zuno.semantic_cache_lookups",
        description="ADR-0104 semantic cache lookups, by outcome (hit/miss/unavailable)",
    )
    _model_call_duration_histogram = meter.create_histogram(
        "zuno.model_call_duration_ms",
        unit="ms",
        description="Model call latency, by provider/model/outcome - same attrs as zuno.model_calls",
    )

    logger.info("telemetry initialized: service=%s otlp_endpoint=%s", service_name, OTEL_ENDPOINT)


def record_cache_outcome(outcome: str, model: str) -> None:
    """ADR-0104: `outcome` is one of "hit", "miss" (cache reachable, no
    entry), or "unavailable" (cache infrastructure itself failed - see
    app/semantic_cache.py's CacheUnavailable). Also stamps the current
    span, if one is active, so a single request's trace shows whether it
    was served from cache."""
    span = trace.get_current_span()
    if span is not None:
        span.set_attribute("zuno.cache_outcome", outcome)
    if _cache_lookup_counter is not None:
        _cache_lookup_counter.add(1, {"outcome": outcome, "model": model})


def _estimate_cost_usd(provider: str, prompt_tokens: int, completion_tokens: int, latency_ms: float) -> float:
    if provider in _COST_PER_SECOND_LOCAL:
        return _COST_PER_SECOND_LOCAL[provider] * (latency_ms / 1000.0)
    in_rate, out_rate = _COST_PER_1K_TOKENS.get(provider, (0.0, 0.0))
    return (prompt_tokens / 1000.0) * in_rate + (completion_tokens / 1000.0) * out_rate


@contextmanager
def model_call_span(
    provider: str,
    model: str,
    classification: str,
    request_id: Optional[str] = None,
    adapter: Optional[str] = None,
    caller_sub: Optional[str] = None,
    groups: Optional[List[str]] = None,
    agent: Optional[str] = None,
    run_id: Optional[str] = None,
    model_kind: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Iterator["ModelCallRecorder"]:
    """Wraps one model invocation: records a span plus the zuno.model_calls
    / zuno.model_call_duration_ms metrics (ADR-0029) unconditionally, for
    every outcome. zuno.model_tokens additionally requires
    `.record_usage()` to have been called on the yielded recorder (e.g. not
    on a failed call, or a candidate whose usage_metadata never populates -
    see app/main.py's `_stream_completion`, which now calls `record_usage`
    too for `stream_usage=True` candidates).
    zuno.model_cost_usd follows that same `.record_usage()` gating for
    remote/SaaS providers (billed by token, so no usage means no known
    cost), but is unconditional for local providers (billed by this call's
    own duration - see _COST_PER_SECOND_LOCAL - so GPU time is charged
    whether the call succeeded or errored).

    ADR-0201 (WP-27): `request_id` is the same X-Zuno-Request-Id
    agent-runtime mints per chat turn (app/main.py's `_request_id`,
    components/agent-runtime/app/telemetry.py's `graph_run_span`) -
    stamping it here is what lets this span (and, when the MaaS adapter
    is in use, MaaS's own usage/token metrics - see app/maas_adapter.py)
    be correlated back to the originating Zuno request trace.

    ADR-0303 (WP-39): `adapter`, when a request was routed to a declared
    LoRA adapter, discharges that ADR's "selection is recorded in traces
    and usage metering" acceptance bullet - `model` itself is already the
    adapter's served name by the time this is called (app/main.py passes
    the resolved name, not the base model, whenever an adapter applied),
    so this attribute exists to make that fact unambiguous in a trace
    query without needing app/providers.py's own resolution logic.

    `caller_sub`/`groups` (ADR-0029's "by user" bullet, never wired until
    now): the validated Keycloak identity, already resolved by
    app/main.py's `validate_token` dependency at every call site. A
    Keycloak group membership is a list, but Prometheus/OTel metric labels
    are scalar - one metric point is recorded per group (attributed
    double-counting across a `sum by (group)` rollup for a multi-group
    user is an accepted demo-scope trade-off, same class as this file's
    other approximations; a user with zero groups still gets one point
    with `group=""`).

    `agent` (ADR-0029's "by user, agent, task, model and provider" bullet,
    also never wired until now): the X-Zuno-Agent header agent-runtime
    already sends on every call (app/main.py's `x_zuno_agent`) - previously
    only used for routing/adapter lookups, never attached to these
    counters, so `zuno_model_calls_total`/`zuno_model_tokens_total`/
    `zuno_model_cost_usd_total` had no reliable per-agent dimension (the
    `group` label sometimes held an `agent_<name>` placeholder for
    service-account callers, but that's a different, unrelated fallback).

    ADR-0517: `run_id` (distinct from request_id - the whole conversation
    turn, not just this one HTTP call) and `model_kind` (candidate.kind,
    "local"/"saas" - app/routing.py) are span attributes only, never added
    to the Prometheus counters above (run_id is unbounded cardinality;
    model_kind is redundant with the existing provider/model labels for
    aggregate dashboards, but is what lets the per-run resource dashboard
    group local-vs-distant without hardcoding provider names).

    ADR-0528: `project_id` is the ZUNO project this turn belonged to - the
    engagement dimension that reached the quota ledger but no trace until
    now. It is a SPAN attribute only, never added to the counters above,
    for exactly the reason run_id is not: projects are created ad hoc at
    runtime, so their cardinality is unbounded. Per-engagement cost and
    latency views are built from traces (joined on zuno.run_id), never from
    counters. It is never the Salesforce opportunity id, which stays in the
    database.
    """
    tracer = _tracer or trace.get_tracer("ai-gateway")
    start = time.monotonic()
    with tracer.start_as_current_span("model_call") as span:
        span.set_attribute("zuno.provider", provider)
        span.set_attribute("zuno.model", model)
        span.set_attribute("zuno.classification", classification)
        if request_id:
            span.set_attribute("zuno.request_id", request_id)
        if adapter:
            span.set_attribute("zuno.adapter", adapter)
        if caller_sub:
            span.set_attribute("zuno.user_sub", caller_sub)
        if groups:
            span.set_attribute("zuno.groups", groups)
        if agent:
            span.set_attribute("zuno.agent", agent)
        if run_id:
            span.set_attribute("zuno.run_id", run_id)
        if model_kind:
            span.set_attribute("zuno.model_kind", model_kind)
        if project_id:
            span.set_attribute("zuno.project_id", project_id)
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
            attrs = {"provider": provider, "model": model, "outcome": outcome, "user": caller_sub or "", "agent": agent or ""}
            group_list = groups or [""]
            for attrs_per_group in ({**attrs, "group": g} for g in group_list):
                if _model_call_counter is not None:
                    _model_call_counter.add(1, attrs_per_group)
                if _model_call_duration_histogram is not None:
                    _model_call_duration_histogram.record(latency_ms, attrs_per_group)
            has_token_usage = bool(recorder.prompt_tokens or recorder.completion_tokens)
            if has_token_usage:
                span.set_attribute("zuno.prompt_tokens", recorder.prompt_tokens)
                span.set_attribute("zuno.completion_tokens", recorder.completion_tokens)
                for attrs_per_group in ({**attrs, "group": g} for g in group_list):
                    if _token_counter is not None:
                        _token_counter.add(recorder.prompt_tokens, {**attrs_per_group, "kind": "prompt"})
                        _token_counter.add(recorder.completion_tokens, {**attrs_per_group, "kind": "completion"})

            # Local GPU time is billed whether the call succeeded or
            # errored - the GPU was occupied for `latency_ms` either way
            # (mirrors zuno.model_call_duration_ms's own always-record
            # posture above). Remote/SaaS cost stays gated on token usage:
            # no usage_metadata means no known token count, and SaaS bills
            # by token, so a token-less remote call genuinely cost $0.
            if has_token_usage or provider in _COST_PER_SECOND_LOCAL:
                cost = _estimate_cost_usd(provider, recorder.prompt_tokens, recorder.completion_tokens, latency_ms)
                span.set_attribute("zuno.estimated_cost_usd", cost)
                for attrs_per_group in ({**attrs, "group": g} for g in group_list):
                    if _cost_counter is not None:
                        _cost_counter.add(cost, attrs_per_group)


class ModelCallRecorder:
    def __init__(self, provider: str):
        self.provider = provider
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
