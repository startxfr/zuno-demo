# Platform SLO (ADR-0102)

99.9% monthly availability is the industrialized objective for the user-facing agent path. This page defines the SLO, how it is
measured, the error-budget policy and the failover timings measured on demo333. [ADR-0102](../adr/0102-target-99-9-percent-platform-availability.md)
is `Implemented` only because the SLO is defined, measured and alerted on a live cluster; read its status line for what was proven when.

## The path and the indicator

Since WP-156 (2026-10-23) and WP-166 the agent path is `UnifAI UI -> UnifAI multiagent -> ai-gateway -> model (and mcp-gateway tools)`. The
frontend, BFF and Agent Runtime of the earlier path no longer exist.

- **Indicator**: the share of UnifAI agent sessions that finish with `mas_outcome="ok"`:

  ```promql
  sum(rate(mas_session_duration_seconds_count{mas_outcome="ok"}[5m]))
  /
  sum(rate(mas_session_duration_seconds_count[5m]))
  ```

  Sessions carry no agent label, so the SLO is fleet-wide. Per-agent volumes come from the ai-gateway's `zuno_model_calls_total{agent}` (one
  point per model call, provider fallbacks included, so not a turn count). UnifAI's incremental sync exposes no lag metric, so the RAG
  freshness-lag alerts were removed.
- **Objective**: 99.9% over a rolling 30 days. **Error budget**: 0.1%, about 43 minutes of full downtime per window.
- **Budget policy**: more than 50% of the monthly budget consumed pages the on-call operator and the cause is investigated before the next
  release; an exhausted budget freezes non-critical chart and configuration changes to the agent path until the window reopens or the cause is fixed.

## Alerting

`gitops/charts/observability/templates/prometheusrule-slo.yaml` ships two multi-window burn-rate alerts on the indicator above (rendered only
for the d1 Application with the collector and alerting enabled): `AgentPathErrorBudgetBurnFast` (1 h and 5 m windows both burning at 14.4 times
the sustainable rate, which would exhaust a 30-day budget in about 2 days) pages; `AgentPathErrorBudgetBurnSlow` (6 h and 30 m, 6 times,
about 5 days) opens a ticket. The overview and "Agents, tools & RAG" dashboards use the same indicator.

## Failover timings

Pod deleted at T0, Argo CD self-heal bypassed by deleting the pod (a rollout restart is reverted as drift), timings measured live on demo333.
Two runs, the second to re-confirm the first ([ADR-0101](../adr/0101-provide-ha-for-shared-agent-platform-services.md), ADR-0111):

| Service | 2026-08-18 | 2026-08-25/26 |
|---|---|---|
| PostgreSQL (PGO, 3 instances), primary deleted | new primary Ready in 4.8 s, writable in 5.7 s | Ready in 24.9 s, writable in 45.0 s |
| mcp-gateway (1 replica at the time) | replacement Ready in 31.0 s | 32.8 s |
| ai-gateway (1 replica at the time) | 33.9 s | 34.9 s |
| redis (`zuno-redis-master-0`) | 56.8 s | 59.2 s |
| keycloak (`zuno-0`, RHBK operator) | 64.7 s; the realm OIDC endpoint answered 200 at once | 55.7 s |

Reading: at one replica a single pod loss costs about a minute of that service, well inside the 43-minute budget. Since ADR-0614 the
ai-gateway and the mcp-gateway run two replicas, so a pod loss leaves one serving pod; the a2a-gateway stays at one replica by design
([ADR-0101](../adr/0101-provide-ha-for-shared-agent-platform-services.md)). The drills of the services that no longer exist
(rag-service, agent-runtime and the BFFs) are in the git history of this page and in the ADR-0101 and ADR-0111 records. The availability measured at the
BFF boundary on 2026-08-18 (73,894 requests over 24 h, zero 5xx) was the measurement of that earlier path.
