# ADR-0543: Propagate a per-run id across every service span

- **Status:** Implemented
- **Target:** v0.5
- **Date:** 2026-09-03 (documenting work implemented 2026-08-23)
- **Decision owners:** Zuno Demo architecture team

## Context

A single chat turn fans out across five services: agent-bff proxies it,
agent-runtime runs the graph, and that graph calls mcp-gateway, rag-service
and ai-gateway. Each already emitted spans, but nothing tied them to *one
turn*. Answering "what did this run cost, and where did the latency go?"
meant correlating by timestamp and hoping.

`session_id` could not do it: it identifies a whole conversation, so every
turn in a session shares one. `request_id` could not either: it identifies a
single HTTP call, so one turn has many. The missing identifier is the turn
itself.

Prometheus cannot answer the question at all. Filtering by run id means a
label with one value per chat turn, i.e. unbounded cardinality — the classic
way to destroy a Prometheus instance.

This decision was implemented on 2026-08-23 in commits `58a5fcc7` and
`d8afa466`, but **its ADR was never written**. The first of those commits is
titled "Add ADR-0517: per-run resource trace" and touches zero files under
`docs/adr/`. ADR-0517 was then authored a day later, 2026-08-24, for an
entirely unrelated decision — redeploying the platform from scratch on a
`demo333` cluster — by an author who reasonably took the next free number
after ADR-0516. Twenty-odd citations across thirteen source files have
pointed at the wrong ADR ever since, and any reader following them landed on
a document about cluster provisioning. This ADR is written retroactively to
carry the decision the code actually implements, and the citations are
recabled to it.

## Decision

1. Every chat turn carries a `run_id`, distinct from `session_id` (the
   conversation) and `request_id` (one HTTP call). agent-bff mints or
   recovers it — including by peeking the first few reads of an SSE stream
   when a resumed conversation already knows its own.
2. Every service stamps it on its spans as the attribute `zuno.run_id`:
   agent-runtime's `api_request` and `agent_graph_run`, mcp-gateway's
   `tool_invoke`, rag-service's `rag_search`, ai-gateway's `model_call`, and
   agent-bff's `bff_request`. agent-bff had metrics only before this and
   gained an OTel tracer for it.
3. agent-runtime forwards it to mcp-gateway, rag-service and ai-gateway on
   every outbound call, threaded through the graph state so graph nodes see
   it too. rag-service treats it as optional, since agent-runtime's
   `rag_client` is its only sender today.
4. The per-run drill-down dashboard
   (`gitops/charts/grafana/templates/dashboard-run-trace.yaml`) is
   Tempo-only by design, plus one Prometheus sanity stat. Every panel is a
   TraceQL query against `zuno.run_id`, because Prometheus cannot filter on
   an unbounded-cardinality label.
5. Tempo's Jaeger UI read path is exposed externally behind the operator's
   own oauth-proxy, so the dashboard's trace links open a real trace page.
   This is deliberately narrower than exposing the ingest/query ports, which
   stay in-cluster. Kiali keeps its own in-cluster Tempo connection for its
   mesh-scoped tracing tab; that view is app-scoped and cannot serve a
   generic "open trace X" link.

## Acceptance criteria

- A chat turn's `run_id` appears as `zuno.run_id` on spans from all five
  services, and one TraceQL query returns every hop of that turn.
- The drill-down dashboard resolves an agent plus a pasted `run_id` into the
  MCP tool calls, RAG searches, model calls and BFF hops that run made, with
  cost, tokens, latency and outcome.
- Trace links from that dashboard open the Jaeger UI through its oauth-proxy
  rather than failing or bypassing authentication.
- No Prometheus series is labelled by `run_id`.

## Implementation notes

- `d8afa466` fixed two defects the first pass shipped: `run_id` never
  reached graph nodes, and the Tempo trace links were broken.
- Panels needing a span attribute outside Tempo's fixed search-result
  columns use TraceQL `select()` to project it as a real field.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Consequences, Security/Operational considerations, Migration/evolution and
Review evidence.

## Related ADRs

- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0517](0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md)
  — unrelated in substance; named here only because this decision's
  citations pointed at it until 2026-09-03.
