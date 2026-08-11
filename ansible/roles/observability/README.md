# observability

Installs the Red Hat build of the OpenTelemetry Operator and a shared OTLP
`OpenTelemetryCollector` (`zuno-otel-collector`, `zuno-monitoring` namespace)
every service sends traces/metrics to (ADR-0029), via
`gitops/apps/observability/application-d0.yaml` (operator) and
`application-d1.yaml` (Collector) - see `gitops/apps/README.md` and
`gitops/charts/observability/README.md`. A Day 0 component (ADR-0056) -
application-level instrumentation lives in each service's own code, not
here.

The Collector's exporter is `debug` (logs spans/metrics to its own pod) -
enough to prove the pipeline end-to-end for a demo
(`oc logs deploy/zuno-otel-collector-collector`) without provisioning a
long-term backend. Swapping in a real backend (Tempo, an APM vendor) only
touches this role's Collector `spec.config.exporters` - every instrumented
service already points at the Collector by its stable in-cluster name and
needs no changes.

Every one of the three Python services instruments itself the same way -
`init_telemetry()` at startup plus a span around its notable operation -
each with its own `app/telemetry.py` (duplicated per-service rather than
shared across independently-deployed images, per
`components/agent-runtime/app/telemetry.py`'s docstring):

| Service | Span | What it records |
|---|---|---|
| `agent-runtime` | `model_call` | provider/model, latency, outcome, token usage, estimated cost |
| `mcp-gateway` | `tool_invoke` | tool, classification, latency, precise outcome (allowed/denied/unknown_tool/...) |
| `rag-service` | `rag_search` | query length, `top_k`, latency, result count |
