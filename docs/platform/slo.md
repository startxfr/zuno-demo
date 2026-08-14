# Platform SLO (ADR-0102)

99.9% monthly availability is the industrialized objective for the
user-facing agent path:

```text
frontend -> BFF -> Agent Runtime -> AI Gateway -> model
```

This document defines the SLO, its measurement query, and the
error-budget policy. ADR-0102's own acceptance bar is explicit: this ADR
is `Implemented` only once the SLO is **defined, measured and alerted on
a live cluster** — not when the number below is merely written down. As
of this WP (roadmap WP-12), the definition and the alerting rules exist;
live measurement does not yet, for the concrete reason in "Current gap"
below.

## SLO definition

- **Indicator**: ratio of successful HTTP responses to total HTTP
  responses at the BFF boundary (`agent-bff`, ADR-0054's OpenAPI
  contract), per agent. "Successful" = any response with status `< 500`
  (a 4xx is a client/authorization outcome, not a platform availability
  failure - matches the same reasoning ADR-0053's security-negative
  checks use to distinguish "correctly rejected" from "broken").
- **Objective**: 99.9% success ratio, measured over a rolling 30-day
  window.
- **Error budget**: 0.1% of requests, i.e. ~43 minutes of full downtime
  (or the equivalent partial-failure-rate area under the curve) per
  30-day window. Budget policy:
  - **>50% of the monthly budget consumed**: page the on-call operator
    (`AgentPathErrorBudgetBurnFast` below, a fast-burn multi-window
    alert per the standard SRE burn-rate pattern), investigate before
    the next release.
  - **Budget exhausted**: freeze non-critical chart/config changes to
    the agent path until the next 30-day window opens or the incident
    causing the burn is resolved - the same "don't make it worse while
    it's already on fire" posture ADR-0053's mandatory (100%)
    security-check layer encodes for a different failure class.

## Measurement query

Intended PromQL (successful request ratio, per the standard SRE
multi-window burn-rate shape), against a `zuno_bff_requests_total`
counter labeled `agent` and `code`:

```promql
sum(rate(zuno_bff_requests_total{code!~"5.."}[5m]))
/
sum(rate(zuno_bff_requests_total[5m]))
```

(30-day objective query substitutes `[30d]` for `[5m]`; the alerting
rules below use the standard 1h/5m and 6h/30m burn-rate window pairs
recommended for a 99.9% SLO, not the raw 30d window directly - see
`gitops/charts/observability/templates/prometheusrule-slo.yaml`.)

## Current gap (honest status, not glossed over)

Two prerequisites are missing before the query above can return real
data:

1. **`agent-bff` does not yet emit `zuno_bff_requests_total`** (or any
   HTTP request-count/status metric). Confirmed by inspection,
   2026-08-14 - no `otel`/metrics import exists in
   `components/agent-bff`. Adding it is Go application instrumentation
   work, out of this WP's chart/docs scope; tracked as a residual item
   below, not silently assumed done.
2. **The shared OTel Collector's metrics pipeline does not yet reach a
   Prometheus-queryable backend.** Before this WP,
   `gitops/charts/observability/templates/opentelemetrycollector.yaml`
   exported metrics only to `debug` (stdout logging) - every metric any
   service in this repo already emits (e.g. rag-service's
   `zuno.rag_searches`, ai-gateway's cache-outcome counters) was
   therefore never actually queryable via PromQL, independent of
   ADR-0102. This WP adds a `prometheus` exporter to that pipeline
   (standard OTel Collector Contrib exporter, exposes `:8889/metrics`)
   so a Prometheus-compatible scraper *can* reach collected metrics -
   but confirming that OpenShift's User Workload Monitoring Prometheus
   (or another scraper) actually discovers and scrapes that endpoint
   (a `ServiceMonitor`/`PodMonitor` targeting whatever Service name the
   OpenTelemetryCollector operator creates for the new exporter port)
   is unverified against a live cluster and deliberately not guessed at
   here - see "Operator follow-up" below.

The PrometheusRule alerting rules below are schema-correct and shipped
(`gitops/charts/observability/templates/prometheusrule-slo.yaml`,
disabled by default alongside the rest of that chart) so they are ready
to evaluate the moment both gaps close - they will not error if the
underlying metric doesn't exist yet, they simply won't fire (Prometheus
evaluates an expression against absent data as "no series", not an
error).

## Alerting rules

`gitops/charts/observability/templates/prometheusrule-slo.yaml` ships
two alerts, following the standard Google SRE multi-window burn-rate
pattern (fast window + slow window both breaching avoids paging on a
single short spike while still catching a fast, severe burn quickly):

- `AgentPathErrorBudgetBurnFast`: 1h and 5m windows both burning budget
  >= 14.4x the sustainable rate (exhausts a 30-day budget in ~2 days if
  sustained) - pages.
- `AgentPathErrorBudgetBurnSlow`: 6h and 30m windows both burning budget
  >= 6x the sustainable rate (exhausts the budget in ~5 days if
  sustained) - tickets, does not page.

## Operator follow-up (not executable by the model)

1. Instrument `agent-bff` with a `zuno_bff_requests_total`-equivalent
   counter (status code + agent labels) - or confirm an existing/
   alternative metric name and update the query above to match.
2. Confirm the OpenTelemetryCollector's new `prometheus` exporter is
   reachable (`oc get svc -n zuno-monitoring` for the Service/port the
   operator creates) and add a `ServiceMonitor`/`PodMonitor` targeting
   it once confirmed.
3. Let the SLO measurement run over a real 30-day window and confirm the
   burn-rate alerts evaluate without error on the live monitoring stack.
   Only then does ADR-0102 satisfy its own "measured... on a live
   cluster" acceptance bar.
