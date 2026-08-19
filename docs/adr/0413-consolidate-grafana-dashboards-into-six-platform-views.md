# ADR-0413: Consolidate Grafana dashboards into six platform views

- **Status:** Implemented
- **Target:** v0.4
- **Date:** 2026-08-19
- **Decision owners:** Zuno Demo architecture team

## Context

`gitops/charts/grafana` shipped five dashboards
([ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)'s
model-consumption/user-consumption, plus infra/network-mesh/api-gateway
added afterward). All five had accumulated real gaps by 2026-08-19:

- **No template variables at all** — not one of the five had a
  `templating` block, so every filter (namespace, provider, model, user,
  agent...) was a hardcoded regex baked into each PromQL expression.
- **The `tempo` datasource
  ([ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)'s
  own distributed-tracing half) was wired up but used by zero panels.**
- Several metric families were already flowing but on no dashboard at
  all — VERIFIED live 2026-08-19: `zuno_tool_invocations_total` (8
  series), `zuno_rag_searches_total` (2), `zuno_rag_result_count_bucket`
  (32) and `zuno_rag_freshness_lag_seconds_count` (2) all had real data,
  simply never visualized. The
  [ADR-0102](0102-target-99-9-percent-platform-availability.md)
  SLO and its burn-rate alerts
  (`gitops/charts/observability/templates/prometheusrule-slo.yaml`) had no
  dashboard either, despite `docs/platform/slo.md` defining the exact
  measurement query.
- vLLM's own `/metrics` (the `vllm:*` series — queue depth, time-to-first-
  token, KV-cache usage, token throughput) was scraped for none of the
  three classic InferenceServices `gitops/charts/models` owns (only the
  separate MaaS `LLMInferenceService` backend had independent scraping via
  RHOAI's own controller). GPU (DCGM) metrics were already live but
  undashboarded. Database exporters (PostgreSQL/MariaDB/Redis) were all
  disabled by default.

Five narrow, unfiltered dashboards with no drill-down path between them
and several known-populated metric families invisible was a worse
operator experience than a smaller number of richer, filterable ones with
cross-links.

## Decision

**Close the scrape gaps, then replace the five dashboards with six
consolidated views**, each carrying template-variable filters
appropriate to its own context and a `dashlist`/dashboard-links panel
back to the other five:

1. **Scrape fixes** (prerequisite, no dashboard changes): a
   `ServiceMonitor` for the three classic vLLM predictors plus matching
   `NetworkPolicy` ingress rules (`gitops/charts/models`); PGO's
   `crunchy-postgres-exporter` sidecar + a `PodMonitor`
   (`gitops/charts/postgresql`); `mariadb-operator`'s built-in
   `spec.metrics` (self-provisions its own `ServiceMonitor`,
   `gitops/charts/mariadb`); bitnami redis's exporter + `ServiceMonitor`
   (`gitops/charts/redis`) — each paired with a precise
   openshift-monitoring/openshift-user-workload-monitoring
   `NetworkPolicy` allowance so the scrape isn't dead on arrival behind
   the zuno-data/zuno-auth default-deny baseline. All
   `monitoring.coreos.com/v1`, never `monitoring.rhobs/v1` — a documented
   landmine on this cluster
   (`gitops/charts/observability/templates/servicemonitor-otel-collector.yaml`):
   that CRD group renders fine but is never scraped by the Prometheus
   that backs Grafana/Thanos.
2. **Six dashboards** in `gitops/charts/grafana/templates/`, retiring the
   five old `uid`s (`zuno-model-consumption`, `zuno-user-consumption`,
   `zuno-infra`, `zuno-network-mesh`, `zuno-api-gateway`) in the same
   change that adds the new ones, so ArgoCD prunes and creates in one
   sync:

   | Dashboard | uid | Filters |
   |---|---|---|
   | Zuno overview | `zuno-overview` | none (landing page) |
   | AI models & serving | `zuno-ai-models` | provider, model, outcome, served_model |
   | Usage & cost | `zuno-usage-cost` | user, group, agent, model, provider |
   | Agents, tools & RAG | `zuno-agents-tools-rag` | agent, tool, mcp_server, domain |
   | Infrastructure & data | `zuno-infra-data` | namespace, node, pod |
   | Mesh & gateway | `zuno-mesh-gateway` | dest_service, source_workload, mesh_namespace |

   Every panel the retired dashboards carried keeps its original PromQL
   (only gaining the new variable filters); new panels cover the
   previously-undashboarded metric families above, node/pod
   CPU/RAM/disk-IO/network-IO/error consumption, the new database
   exporters, and ArgoCD sync health (`argocd_app_info` — already live,
   no scrape change needed). Several panels add TraceQL tables or
   `fieldConfig` data links into Tempo Explore — the first real use of
   the `tempo` datasource on this dashboard set.

See `gitops/charts/grafana/README.md`'s dashboard table for the full
per-dashboard panel/filter inventory.

## Accepted risks (and their remediations)

- **PostgreSQL's `ccp_*` panel expressions
  (`dashboard-infra-data.yaml`) are unverified against a live
  exporter.** The `crunchy-postgres-exporter` sidecar this ADR enables
  hadn't been synced/scraped as of this change — Crunchy's custom-query
  metric names are documented but not confirmed against this cluster's
  actual PGO version. MariaDB (`mysqld_exporter`) and Redis
  (`oliver006/redis_exporter`, bitnami's default) use stable upstream
  metric names and are not expected to need adjustment. Remediation:
  adjust the `ccp_*` expressions once the exporter is live and its real
  series are confirmed via Thanos.
- **The vLLM `ServiceMonitor` selector and port name are best-effort.**
  VERIFIED live: all three predictor Services expose port 80 (name
  `http`) → targetPort 8080, which the ServiceMonitor and the
  NetworkPolicy ingress rules both assume — but the exact `vllm:*` series
  a given vLLM build emits can vary by version. Remediation: confirm live
  once the models chart re-syncs; the embeddings runtime may legitimately
  emit no `vllm:*` series (pooling/embed mode) with no fix needed.
  Confirmed separately, VERIFIED live 2026-08-19: `vllm:num_requests_running`
  already exists for the MaaS backend (job
  `zuno-ai-run/kserve-llm-isvc-vllm-engine-default`, port 8000) via a
  scrape mechanism this ADR doesn't touch — that confirms the metric
  family itself is real on this vLLM build, only the three classic
  predictors' own scrape was missing before this change.
- **Grafana's Explore deep-link URL schema is unverified on the deployed
  Grafana version.** The four `fieldConfig.defaults.links` data links
  (AI models latency panel, per-agent success-ratio panel, MCP tool
  invocations panel, RAG searches panel) were built by hand-encoding the
  documented `/explore?left=...` JSON payload shape; Grafana 11.x's exact
  accepted format wasn't confirmed against a live click-through.
  Remediation: click-test one link after this syncs; if the schema has
  moved on, only those four `url` values need updating, not the TraceQL
  queries themselves.
- **The mesh's `PeerAuthentication` mode was confirmed permissive
  (no cluster-wide `PeerAuthentication` resource exists), so the new
  database exporter scrapes cross the mesh sidecar boundary in plaintext
  without issue** — VERIFIED live 2026-08-19, not assumed. If a future
  change introduces a `STRICT` mTLS policy in `zuno-data`/`zuno-auth`,
  the exporter NetworkPolicies alone won't be sufficient and the
  MariaDB CR's existing `traffic.sidecar.istio.io/excludeInboundPorts`
  precedent (already used for port 3306) is the documented remediation
  pattern.
