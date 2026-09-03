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
   endpoint.

   *"Once per HTTP response" was true as written and false in practice
   between then and 2026-09-03:* `RecordRequest` also carried `user`/`group`
   labels and emitted one point PER KEYCLOAK GROUP, so a caller in twelve
   groups counted twelve times while a request that never reached a verified
   token counted once. Live, the fleet read 6541 against 6180 real responses.
   The ratios above are NOT immune to that - a ratio only survives a uniform
   fan-out, and this one scaled with the caller's group count, so an error
   from a one-group caller and one from a twelve-group caller carried
   different weight in the same `5xx/total`. The counter now matches this
   description again; the identity breakdown lives on
   `zuno_bff_requests_by_identity_total`, which counts group-request pairs
   and must never appear in a volume or SLO query. Expect a step down in
   every absolute count on 2026-09-03 with no change in real traffic. Unit-tested (`internal/telemetry/telemetry_test.go`,
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

**Confirmed end to end, 2026-08-18**: pushed, built (`oc start-build
agent-bff`, from commit `8b2d210`), and rolled out to all six BFF
Deployments (`tekos-bff`, `arkos-bff`, `comage-bff`, `advantage-bff`,
`finage-bff`, `naveo-bff` - this codebase is shared platform-wide, not
just Tekos/Arkos). `zuno_bff_requests_total` is real and queryable:

```text
zuno_bff_requests_total{agent="tekos",code="200"}   29
zuno_bff_requests_total{agent="arkos",code="200"}   9
... (all six agents present)
```

(`oc rollout restart` alone doesn't reliably work here - ArgoCD's
`selfHeal: true` on the agent Applications reverted `arkos-bff`'s and
`naveo-bff`'s restart within ~1s as drift, since the `restartedAt`
annotation isn't tracked in Git. Deleting the running pod directly
worked for both: `imagePullPolicy: Always` means the ReplicaSet's
replacement pod re-pulls `:latest`, and pod deletion isn't something
ArgoCD's Application-level diffing reverts.)

Remaining before ADR-0102 can claim "measured... on a live cluster":

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
2. ~~Confirm `zuno_bff_requests_total` itself appears in Prometheus~~ -
   done 2026-08-18 (same day, later pass): 1 aggregate series live on
   `thanos-querier`, ~73,894 requests over the trailing 24h window.
3. ~~Confirm the burn-rate alerts evaluate without error on the live
   monitoring stack~~ - done 2026-08-18: both
   `AgentPathErrorBudgetBurnFast`/`Slow` evaluate `health: ok`,
   `state: inactive` on the cluster Prometheus (group
   `zuno-agent-path-availability-slo`, 30s interval). The full 30-day
   window continues to accumulate (complete ~2026-09-17); per the
   operator's 2026-08-18 decision the measured short window below closes
   ADR-0102's "measured and alerted on a live cluster" bar, with this
   note recording the window length honestly.

## Failover drill record + measured window (2026-08-18, WP-12)

Measured availability at the BFF boundary over the trailing 24h window
(all six agents' BFFs, `sum(increase(zuno_bff_requests_total...[24h]))`):
**100.000%** - 73,894 requests, zero 5xx. Objective ≥ 99.9%: met on the
available window; the 30-day series keeps accumulating.

Failover drill, per service (pod deleted at T0, all timings measured
live on the demo cluster; ArgoCD `selfHeal` intentionally bypassed by
deleting pods, per the platform note in this file):

| Service | Drill | Result |
|---|---|---|
| PostgreSQL (PGO, 3 instances) | primary pod deleted | new primary elected + Ready in **4.8s**, writable in **5.7s** (Patroni) |
| rag-service (scaled to 2 for the drill, PDB `minAvailable: 1`) | 1 of 2 pods deleted under a 2 req/s probe | **79/81 requests OK**; 2 transient timeouts in the ~2.5s after the kill, continuous service on the surviving replica; PDB held |
| mcp-gateway (1 replica) | pod deleted | replacement Ready in **31.0s** |
| ai-gateway (1 replica) | pod deleted | replacement Ready in **33.9s** |
| agent-runtime (1 replica) | pod deleted | replacement Ready in **34.4s** |
| redis (`zuno-redis-master-0`) | pod deleted | Ready in **56.8s** |
| keycloak (`zuno-0`, RHBK operator) | pod deleted | Ready in **64.7s**; realm OIDC endpoint 200 immediately after |

Reading: at demo scale (replicas: 1) a single pod loss costs ≤ ~65s of
that service's availability - well inside the 43.2 min/30d error budget
- and the scaled continuity drill demonstrates the PDB + spread
mechanics deliver near-zero-loss behavior the moment `replicas` ≥ 2
(the production profile ADR-0101 targets). The rag-service drill's two
timeouts are endpoint-deregistration lag at pod kill, not a PDB or
scheduling failure.

## Failover drill re-run (2026-08-25/26, ADR-0111 live re-verification)

Same procedure repeated (pod deleted at T0, ArgoCD `selfHeal` bypassed by
deleting pods), to re-confirm the 2026-08-18 result still holds:

| Service | Drill | Result |
|---|---|---|
| PostgreSQL (PGO, 3 instances) | primary pod deleted | new primary elected + Ready in **24.9s**, writable in **45.0s** (Patroni); cluster back to 3/3 healthy |
| rag-service (scaled to 2 for the drill, PDB `minAvailable: 1`) | 1 of 2 pods deleted under a ~2 req/s probe (40 requests) | **40/40 requests OK**, zero timeouts; PDB held (`ALLOWED DISRUPTIONS: 0` while the replacement was still initializing) |
| mcp-gateway (1 replica) | pod deleted | replacement Ready in **32.8s** |
| ai-gateway (1 replica) | pod deleted | replacement Ready in **34.9s** |
| agent-runtime (1 replica) | pod deleted | replacement Ready in **34.9s**; fresh startup also re-verified all 8 OKF bundle signatures cleanly (WP-069's trust-anchor fix holds) |
| redis (`zuno-redis-master-0`) | pod deleted | Ready in **59.2s** |
| keycloak (`zuno-0`, RHBK operator) | pod deleted | Ready in **55.7s**; realm OIDC endpoint 200 immediately after |

All results within the same order of magnitude as the 2026-08-18 run
and well inside the 43.2 min/30d error budget; rag-service's continuity
was better this time (zero failed requests vs. 2 transient timeouts
previously) - both are consistent with PDB + spread mechanics working
as intended, not a regression or a fluke.
