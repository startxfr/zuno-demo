# WP-147: UnifAI OpenTelemetry instrumentation

- **State:** Not started
- **ADRs:** [ADR-0566](../../adr/0566-instrument-unifai-with-opentelemetry.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)
- **Depends on:** none
- **Related:** [ADR-0029](../../adr/0029-instrument-model-usage-costs-and-distributed-traces.md), [WP-151](wp-151-deploy-unifai-on-zuno-via-argocd.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)
- **Target:** v0.11
- **Estimated files touched:** ~15 in `startx-unifai` — tracing/metrics bootstrap in multi-agent, rag and backend, LLM/node spans, `UnifaiStack.spec.integrations` and the stack renderer, tests; ~2 in `zuno-demo` (run-trace dashboards).

> UnifAI's only observability today is optional Langfuse. The platform's
> trace and cost views (Tempo, Prometheus, the run-trace dashboard) would lose
> everything upstream of the ai-gateway at cutover without this.

## Goal

MAS, RAG and backend emit OTel traces and metrics over OTLP to an endpoint
configured in `UnifaiStack.spec.integrations`, and every outbound model call
carries `traceparent`, so a single Tempo trace runs UnifAI -> ai-gateway ->
model.

## Steps

Work in `/home/cl/ClaudeCode/startx-unifai`. Python changes are generic: start
from `main` (`make feature-start BRANCH=feat/opentelemetry`), merge into `devel`
(`make feature-to-devel`). Operator changes are fork-only (they live under
`fork/`) and go straight to `devel`.

1. **Bootstrap.** Add an optional OTel bootstrap module used by
   `multi-agent/bootstrap/`, `rag/bootstrap/` and `backend/` app factories.
   It is inert unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Instrument Flask
   and outbound HTTP (`requests`/`httpx`, whichever each service uses — grep
   first) with the standard OTel instrumentation packages; add them to each
   service's `pyproject.toml`.

2. **Domain spans and metrics in MAS.** Add a span per node execution and per
   LLM call (attributes: agent, workflow, node, model name, token counts when
   returned). Hook the LLM call in
   `multi-agent/lib/mas/elements/llms/openai_compatible/openai_compatible.py`
   and the node execution in `multi-agent/lib/mas/engine/distributed/node_executor.py`.
   Emit counters/histograms for node duration, LLM latency and tokens. Do not
   reuse the `zuno.model_*` metric names — those belong to the ai-gateway
   (`components/ai-gateway/app/telemetry.py` in zuno-demo).

3. **Propagation.** Ensure `traceparent` is injected on the LLM and MCP
   outbound calls (the HTTP instrumentation of step 1 does it if the clients
   are instrumented; verify with a test). For Temporal, propagate the context
   through activity headers, not through workflow inputs.

4. **RAG.** Spans for ingestion stages (Celery tasks in
   `rag/infrastructure/celery/`) and for retrieval
   (`rag/infrastructure/qdrant/qdrant_vector_repository.py`).

5. **Operator surface.** Add `OpenTelemetrySpec` (`endpoint`, `protocol`
   grpc|http, optional `headers` SecretKeySelector, `serviceNamePrefix`) to
   `IntegrationsSpec` in `fork/unifai-operator/api/v1alpha1/unifaistack_types.go`,
   run `make generate manifests`, and render the `OTEL_*` env vars in
   `fork/unifai-operator/internal/stack/` (find where Langfuse env is rendered
   and mirror it). Add a render test in `internal/stack/render_test.go`.

6. **Tests.** Python: unit tests asserting bootstrap is a no-op without the
   env var and that a mocked outbound call carries `traceparent`
   (`multi-agent/tests/unit/`, `rag/tests/unit/`). Operator: `make test`
   (envtest) in `fork/unifai-operator`.

7. **Release.** `make images-devel` for the Python images. For the operator:
   `make test` first, bump `VERSION` in `fork/unifai-operator/Makefile`,
   coordinate with the startx-unifai session before running the release
   chain documented in the fork's `MEMORY.md` — OLM on demo333 rolls it out to
   both `unifai-devel` and `unifai-olm`.

8. **zuno-demo dashboards (prepared offline, verified live in WP-154).**
   Adapt `gitops/charts/grafana/templates/dashboard-run-trace.yaml` and
   `gitops/charts/perses/templates/dashboard-run-trace.yaml` to show UnifAI
   spans next to the agent-runtime ones (both sources coexist until
   [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)).

## Acceptance

Unit and envtest suites green; with no OTLP endpoint configured, no exporter
starts. The live proof — one continuous Tempo trace UnifAI -> ai-gateway ->
model, checked in raw Tempo, not only in the dashboard — happens in
[WP-154](wp-154-tekos-pilot-on-demo333.md) once demo333 is powered on (it is
powered off; ask the user).

## Open questions

- Does the ai-gateway already continue an incoming `traceparent`
  (`components/ai-gateway/app/telemetry.py`)? Unverified; read it before
  WP-154 and fix there if not.
- Should Langfuse and OTel coexist, or should Langfuse be fed from OTel?
  Out of scope; keep Langfuse untouched.
