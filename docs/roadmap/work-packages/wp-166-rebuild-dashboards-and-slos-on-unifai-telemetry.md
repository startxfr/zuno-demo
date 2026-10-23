# WP-166: Rebuild dashboards and SLOs on the ai-gateway and UnifAI telemetry

- **State:** Not started
- **ADRs:** [ADR-0566](../../adr/0566-instrument-unifai-with-opentelemetry.md), [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md)
- **Depends on:** [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)
- **Related:** [WP-147](wp-147-unifai-opentelemetry-instrumentation.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)
- **Target:** v0.11
- **Estimated files touched:** ~15 in `zuno-demo` — `gitops/charts/grafana/templates/dashboard-*.yaml`, `gitops/charts/perses/templates/dashboard-*.yaml`, `gitops/charts/observability/templates/prometheusrule-{slo,freshness-lag}.yaml`.

> Split out of WP-156 by user decision (2026-10-23): retiring the old stack
> removes the panels and rules that read its metrics; rebuilding them is
> this work package, so WP-156 is not blocked on observability design.

## Goal

The overview, run-trace, usage-cost and agents/tools/RAG dashboards (Grafana
and Perses) and the availability SLO and RAG freshness rules read metrics the
platform still emits after WP-156: the ai-gateway's `zuno_*` metrics
(routing, tokens, guardrails, quota) and UnifAI's OpenTelemetry signals
(traces and metrics through the zuno collector, ADR-0566), instead of
`zuno_bff_*` and `zuno_rag_*`.

## Steps

1. Inventory every panel and rule on `zuno_bff_*` or `zuno_rag_*`
   (listed in `docs/roadmap/evidence/wp-156-retirement-inventory.md`).
2. For each, name the replacement signal (ai-gateway metric, UnifAI OTel
   metric or span-derived metric) or drop it with a reason.
3. Rebuild the panels, then the SLO: availability of agent turns measured
   at the ai-gateway or UnifAI multiagent, not at the BFF.
4. RAG freshness from UnifAI's incremental source sync (ADR-0568), if it
   exposes one; otherwise drop the rule with that reason.
5. Live: a demo333 run with real traffic shows every rebuilt panel
   populated and the SLO rule evaluating.

## Acceptance

No dashboard panel or rule references `zuno_bff_*` or `zuno_rag_*`; every
rebuilt panel shows data on demo333; the SLO rule evaluates.

## Open questions

- Which UnifAI OTel metrics reach Prometheus today (WP-147 wired traces;
  metrics export may need collector rules)?
