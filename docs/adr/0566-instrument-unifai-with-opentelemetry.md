# ADR-0566: Instrument UnifAI with OpenTelemetry

- **Status:** Partially implemented
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md) (instrument model usage, costs and distributed traces), [ADR-0543](0543-propagate-a-per-run-id-across-every-service-span.md) (propagate a per-run id across every service span)
- **Related:** [ADR-0523](0523-dual-export-traces-into-the-rhoai-monitoring-stack.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

ADR-0029 requires tokens, cost, latency and decisions to be measurable by
user, agent, task, model and provider through OpenTelemetry. ADR-0543 made
one `run_id` the join key of a chat turn: every zuno service stamps it as the
span attribute `zuno.run_id`, and the per-run drill-down dashboard
(`gitops/charts/grafana/templates/dashboard-run-trace.yaml`) is built on
TraceQL queries naming specific spans: `bff_request` (agent-bff),
`api_request` (agent-runtime), `tool_invoke` (mcp-gateway), `rag_search`
(rag-service) and `model_call` (ai-gateway). ADR-0523 fans every span out of
the platform collector (`zuno-otel-collector-collector.zuno-monitoring:4317`)
into RHOAI's Tempo as well.

ADR-0561 replaces agent-bff and agent-runtime with UnifAI. Two of those five
spans disappear with them, and nothing in UnifAI emits a replacement. UnifAI
has no OpenTelemetry instrumentation: no Python module in the fork imports
`opentelemetry`. Its only observability hook is optional Langfuse tracing in
the multi-agent service (`multi-agent/pyproject.toml` extra
`tracing = ["langfuse>=3.0.0"]`, `langfuse_enabled: bool = False` in
`multi-agent/config/app_config.py`, adapter under
`multi-agent/adapters/outbound/langfuse/`). Langfuse is a separate SaaS or
self-hosted product the zuno platform does not run, and it exports nothing to
Prometheus or Tempo. `UnifaiStack.spec.integrations` offers `slack`, `umami`,
`langfuse` and a GCP key, and no telemetry endpoint
(`fork/unifai-operator/api/v1alpha1/unifaistack_types.go`).

Without instrumentation, a turn handled by UnifAI shows up only as an
orphan `model_call` span in the ai-gateway and an orphan `tool_invoke` span in
the mcp-gateway, with no parent and no way to tell which agent, workflow
node or user produced it. The model-usage metrics (`zuno.model_*`, emitted by
`components/ai-gateway/app/telemetry.py`) survive, because they are produced
by the gateway that ADR-0560 keeps, but the agent-side half of ADR-0029
(decisions, node latency, tool selection) is lost.

There is a second, smaller gap on the zuno side. `components/ai-gateway/app`
does not extract an inbound W3C `traceparent` (no propagator or framework
instrumentor is wired; the grep finds none), so even an instrumented caller
would not become the parent of `model_call`. Today the two are joined only
through `zuno.run_id`.

## Decision

**The fork gains OpenTelemetry traces and metrics in the multi-agent service
(Flask API and its LangGraph and Temporal executors), the RAG service (Flask
API and Celery workers) and the backend.** This is generic work, written for
upstream under ADR-0575: it uses the OpenTelemetry Python SDK, the standard
Flask, Celery, HTTP-client and Pymongo instrumentations, and the GenAI
semantic conventions for model calls, and it emits no `zuno.*` attribute.

The spans that matter, at minimum:

- one span per workflow run and one per node execution, carrying the agent,
  workflow and session identifiers UnifAI already has, and a run identifier;
- one span per LLM element call, with model, provider type and token usage
  as GenAI attributes;
- one span per MCP tool call and per retriever call;
- one span per RAG ingestion task in the Celery workers.

The minimal metric set: model-call count and duration, token usage, workflow
and node duration with outcome, tool-call count with outcome, and ingestion
document and chunk counts. **No metric carries a run, session or user
identifier as a label**; those live on spans only, as ADR-0543 clause 4
already requires.

**Context crosses every hop.** The W3C `traceparent` is injected on every
outbound HTTP call, including the `openai_compatible` LLM element (so the
ai-gateway receives it) and the MCP client (so the mcp-gateway receives it).
Across Temporal, context is carried from workflow to activity with Temporal's
OpenTelemetry interceptor; across Celery, with the Celery instrumentation.
The zuno-side counterpart is part of this decision: the ai-gateway and the
mcp-gateway extract inbound `traceparent`, so their spans become children of
UnifAI's spans instead of new roots.

**Export is configured on the stack, not baked into images.**
`UnifaiStack.spec.integrations` gains an `openTelemetry` block (OTLP
endpoint, protocol, sampling ratio, extra resource attributes, optional
headers from a Secret). The operator renders it into the standard
`OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` and
`OTEL_TRACES_SAMPLER*` environment variables on every UnifAI workload. When
the block is absent, nothing is exported, which keeps upstream behaviour
unchanged. On zuno clusters the endpoint is the platform collector, so
ADR-0523's fan-out to RHOAI's Tempo applies with no further work.

**Langfuse stays optional and must coexist.** The fork does not remove the
Langfuse adapter. Langfuse's v3 SDK is itself built on OpenTelemetry
(per its own documentation; not verified in this fork), so the two must not
fight over the global tracer provider; WP-147 proves both enabled at once
before merging.

**`zuno.run_id` is mapped, not emitted.** UnifAI stamps its own generic run
identifier, and ADR-0563 forwards it to the gateways as `X-Zuno-Run-Id`. The
zuno collector's pipeline copies UnifAI's run attribute into `zuno.run_id`
with an attributes/transform processor, so the run-trace dashboard keeps one
join key while upstream code stays free of zuno names.

**The run-trace dashboard is adapted at cutover.** Its `bff_request` and
`api_request` panels are replaced by UnifAI's workflow-run and node spans;
the `tool_invoke`, `rag_search` (or its UnifAI retriever successor, ADR-0568)
and `model_call` panels stay.

## Consequences

A UnifAI turn becomes one trace from workflow start to model and tool calls,
visible in both Tempo stacks, and the agent-side half of ADR-0029 is restored.
The dashboard keeps working across the cutover with two panels swapped.

The instrumentation is a sizeable upstream contribution touching three
services and both executors. Until upstream accepts it, it is the largest
piece of fork delta in Python code, with the rebase cost ADR-0575 describes.

The ai-gateway and mcp-gateway gain context extraction. This is small, but it
changes their span parentage: dashboards or alerts that count root spans per
service will see fewer roots once callers are instrumented.

## Security considerations

Prompts, completions, retrieved chunks and tool arguments are **not**
recorded on spans or metrics by default; GenAI content capture stays off.
Turning it on would copy C2/C3 content into Tempo, a store with a wider
audience than the conversation, which ADR-0035 does not allow. Access tokens,
the `Authorization` header and the `X-Authenticated-User` header are never
recorded as attributes.

The OTLP endpoint is in-cluster. The zuno charts that export to the platform
collector set an endpoint and no credentials (for example
`gitops/charts/models/values.yaml`), and UnifAI exports the same way; the
UnifAI namespace's egress NetworkPolicy must allow that one port. If headers are
needed for another backend, they come from a Secret selector on the stack,
never from plain spec fields.

## Operational considerations

Verify against a dead mechanism, not a green run: with the `openTelemetry`
block removed, no UnifAI span may reach Tempo; with it present, one chat turn
must yield a single trace whose root is a UnifAI workflow span and whose
descendants include an ai-gateway `model_call`. A trace with a `model_call`
root proves that propagation is broken, whatever the span count says.

Sampling defaults to a ratio set on the stack; the demo clusters run at
full sampling, as the zuno services do today.

WP-147 carries the fork work; the dashboard swap happens in WP-154 on
`demo333`, which is powered off at the time of writing and must be powered
on by the user first. Every `oc` command passes `--context`.
