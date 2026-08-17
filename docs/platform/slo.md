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
  (a 4xx is a client/authorization outcome, not an availability failure).
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
    the agent path until the next 30-day window opens or the burn's
    root cause is resolved.

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

## Current gap (2026-08-18 update, ADR-0111)

Both prerequisites below were closed this pass - contrary to ADR-0111's
own earlier note that "no further repo-side work closes any row" in the
security control matrix, both turned out to be genuine repo-side gaps,
not live-cluster-only verification:

1. **`agent-bff` now emits the counter** - `internal/telemetry`
   (`components/agent-bff/internal/telemetry/telemetry.go`) registers an
   OTLP `zuno.bff.requests` counter (Prometheus name
   `zuno_bff_requests_total`, matching the query above exactly), labeled
   `agent`/`code`, incremented once per HTTP response by `main.go`'s new
   `metricsMiddleware`. Same OTLP-push-to-the-shared-Collector pattern as
   every Python service (ADR-0029), not a bespoke per-service `/metrics`
   endpoint. Unit-tested (`internal/telemetry/telemetry_test.go`,
   `main_test.go`) against a `ManualReader`; live emission depends on this
   change actually being built and deployed (tracked below).
2. **A `ServiceMonitor` for the Collector's `:8889` exporter now exists
   and is confirmed scraping live** -
   `gitops/charts/observability/templates/servicemonitor-otel-collector.yaml`,
   `apiVersion: monitoring.coreos.com/v1` (verified against the actual
   Prometheus instance that evaluates `prometheusrule-slo.yaml` - a
   second, separate ServiceMonitor CRD group also exists on this cluster,
   `monitoring.rhobs/v1`, watched by a *different* Prometheus; using it
   here would have rendered successfully while never being scraped by the
   one that matters). Confirmed live 2026-08-18:
   `up{job="zuno-otel-collector-collector"} == 1` on `prometheus-k8s`.

Remaining before ADR-0102 can claim "measured... on a live cluster":

- Get item 1 built and deployed (`make d1 build agent` pulls from
  `origin/main`, not local disk - requires this change to be pushed and a
  fresh image rolled out) and confirm `zuno_bff_requests_total` itself
  appears in Prometheus, not just the Collector's own `up` target.
- Let the SLO measurement run over a real 30-day window and confirm the
  burn-rate alerts evaluate without error.

The PrometheusRule alerting rules below are shipped and schema-correct
(disabled by default) — they simply won't fire until both gaps close;
Prometheus treats a missing metric as "no series", not an error.

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

1. ~~Instrument `agent-bff`~~ and ~~add a `ServiceMonitor`~~ - both done
   2026-08-18, see "Current gap" above.
2. Confirm `zuno_bff_requests_total` itself appears in Prometheus once
   the instrumented `agent-bff` image is built and deployed (this repo's
   `BuildConfig`s clone from `origin/main`, not local disk).
3. Let the SLO measurement run over a real 30-day window and confirm the
   burn-rate alerts evaluate without error on the live monitoring stack.
   Only then does ADR-0102 satisfy its own "measured... on a live
   cluster" acceptance bar.
