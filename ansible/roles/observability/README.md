# observability

Installs the Red Hat build of the OpenTelemetry Operator and a shared OTLP
`OpenTelemetryCollector` (`zuno-otel-collector`, `zuno-platform` namespace)
every service sends traces/metrics to (ADR-0029). PREP_COMPONENT only — no
CONFIG_SCOPE; application-level instrumentation lives in each service's own
code, not here.

The Collector's exporter is `debug` (logs spans/metrics to its own pod) —
enough to prove the pipeline end-to-end for a demo
(`oc logs deploy/zuno-otel-collector-collector`) without provisioning a
long-term backend. Swapping in a real backend (Tempo, an APM vendor) only
touches this role's Collector `spec.config.exporters` — every instrumented
service already points at the Collector by its stable in-cluster name and
needs no changes.

See `components/agent-runtime/app/telemetry.py` for the reference
instrumentation pattern (token usage, estimated cost, and a span per model
call, per ADR-0029) — `mcp-gateway` and `rag-service` should adopt the same
pattern; that wiring is not yet done in those two services (flagged here
rather than silently left unmentioned).
