# WP-081: Fan mesh traces out to RHOAI's collector

- **State:** Done (live-verified 2026-08-26).
- **ADRs:** ADR-0523 (To be implemented)
- **Depends on:** WP-079 (RHOAI traces stack live), WP-080 (diagnosed the zero-traces root causes)
- **Related:** WP-082 (workload-level path, independent), ADR-0029/ADR-0413 (the zuno-monitoring
  pipeline this must not regress)

## Goal

Make MaaS Gateway/Envoy spans reach RHOAI's Tempo. Envoy sidecars mesh-wide already export
every span to `zuno-otel-collector` (`zuno-monitoring`) via the single `otel-tracing`
extensionProvider; add an `otlp/rhoai` exporter to that collector's `traces` pipeline so a copy
of every span is also forwarded to
`data-science-collector-collector.redhat-ods-monitoring.svc.cluster.local:4317`. The fan-out
lives in the collector - not the mesh - because Istio's Telemetry API honors only a single
tracing provider per rule (ADR-0523); the service-mesh chart and `Istio` CR stay untouched.

## Why not a second extensionProvider

That was the originally-prescribed shape. Verified against the live v1.30.3 CRD: `providers` is
effectively single-valued per tracing rule, and multiple `tracing` list entries without `match`
have undefined/last-wins semantics - a silent way to lose the existing `zuno-monitoring` export
that this repo's Grafana dashboards depend on. Collector-level fan-out is the standard OTel
pattern and leaves the proven path byte-for-byte identical.

## What changed

- `gitops/charts/observability/templates/opentelemetrycollector.yaml`: new `otlp/rhoai`
  exporter appended to the `traces` pipeline - straight to
  `tempo-data-science-tempostack-gateway...:8090` with `bearertokenauth/rhoai` (SA token),
  `X-Scope-OrgID: redhat-ods-monitoring` and service-ca TLS (see "Live finding" for why not
  RHOAI's collector), all gated on `collector.rhoaiTraceExport.enabled`. Metrics pipeline
  deliberately untouched (RHOAI's metrics side is Prometheus-scrape-shaped, not OTLP-push).
- New `gitops/charts/observability/templates/rbac-rhoai-traces.yaml`:
  `zuno-rhoai-tempo-traces-write` ClusterRole (+Binding for
  `zuno-monitoring/zuno-otel-collector-collector`) - the Tempo-operator-documented
  openshift-mode tenant-write rule.
- `gitops/charts/observability/values.yaml`: `collector.rhoaiTraceExport.enabled: false`
  (chart default false, matching the chart's all-default-false convention).
- `gitops/apps/observability/application-d1.yaml`: enables it inline next to
  `collector.enabled`. `helm template` verified: gate off renders byte-identical to before.
- `gitops/charts/openshift-ai/values.yaml`: DSCI traces retention canonicalized to `48h0m0s`
  (see "Live finding" item 5).
- `ansible/roles/openshift_ai/tasks/reconcile.yml`: header's `make d0` claim corrected to
  `make d1`; deliberate-non-action comment documenting the two operator-reverted fix attempts.

## Live finding: RHOAI's collector→Tempo hop has never worked, and can't be fixed in place

First verification attempt: the fan-out deployed clean (collector CR carried `otlp/rhoai`, new
pod healthy), a real embedding call returned 200 - and RHOAI's Tempo search still returned zero
traces. The debugging trail, all confirmed live:

1. **Spans DID arrive at RHOAI's `data-science-collector`** - whose own `otlp/tempo` exporter
   then error-looped `dial tcp <gateway-ClusterIP>:4317: i/o timeout`. The RHOAI-generated
   `tempo-data-science-tempostack-gateway` Service exposes ONLY `grpc-public=8090`,
   `internal=8081`, `public=8080`; 4317 exists solely on the distributor Service, whose
   NetworkPolicy admits only gateway pods. RHOAI 3.5.0-ea.2's trace pipeline can never have
   worked end-to-end.
2. **Fix attempt A - patch the collector's exporter endpoint to `:8090`** (via a new
   reconcile.yml task, `make d1 reconcile openshift-ai`): applied, then reverted by the
   Monitoring controller within seconds (it re-renders `spec.config`; unlike the TempoStack
   `resources.total` WP-079 patches, which it never revisits).
3. **Fix attempt B - append a `4317 -> grpc-public(8090)` port to the gateway Service**: applied
   (`changed`), stripped by the Tempo Operator within seconds.
4. **Also discovered: no ServiceAccount in the cluster holds the tenant-write grant**
   (`create` on `tempo.grafana.com/redhat-ods-monitoring`, resourceName `traces`) the
   openshift-mode gateway SARs against - not even RHOAI's own collector SA (it never gets far
   enough to need it). Third defect in the same pipeline, after the Instrumentation CR's
   nonexistent-Service endpoint (ADR-0523).
5. Incidental catch: the first reconcile run was blocked by latent WP-079 drift -
   `DSCInitialization`'s `traces.storage.retention: 48h` comes back from the cluster as
   `48h0m0s`, so ArgoCD saw permanent OutOfSync and the app-wait timed out. Fixed by
   canonicalizing the chart value; and reconcile.yml's header claimed a `make d0 reconcile
   openshift-ai` form that doesn't exist (openshift-ai is DAY1_RUN) - both corrected here.
   **The mechanism is not API-server normalization** (an early note in this WP said so and was
   wrong): the API server stores CRD strings byte-for-byte, and other `metav1.Duration` fields
   in this repo prove it (`Certificate.spec.duration` stores `8760h`, all 95
   `ExternalSecret.spec.refreshInterval` store `1h`). It is the **CRD conversion webhook**:
   `dscinitializations` serves v1 but stores **v2**, and this chart renders v1, so every write
   round-trips v1 -> operator Go structs -> v2 and canonicalizes whatever is a `metav1.Duration`
   in Go. The control experiment sits two keys away in the same chart: `metrics.storage.
   retention: 15d` crosses the identical webhook untouched, because it is a plain Go `string` -
   so that one must NOT be "canonicalized" (`MonitoringStack.spec.retention` even carries a
   pattern regex that would reject `360h0m0s`). `oc explain` prints `<string>` for both and
   cannot tell them apart.

**Final design**: bypass RHOAI's collector entirely. `zuno-otel-collector`'s `otlp/rhoai`
exporter goes straight to the Tempo **gateway** on 8090 with the documented RHOSDT pattern -
`bearertokenauth` (the pod's own SA token), `X-Scope-OrgID: redhat-ods-monitoring`, service-ca
TLS - plus a repo-owned `zuno-rhoai-tempo-traces-write` ClusterRole/Binding granting the
tenant write. Fully repo-owned, nothing for RHOAI's operators to fight. Consequence for WP-082:
its Instrumentation endpoint targets the platform collector (which fans out here), NOT RHOAI's
- so both Tempo stacks receive the workload spans. reconcile.yml keeps a deliberate-non-action
comment so nobody re-attempts the two reverted fixes.

## Second live finding: RHOAI's TempoStack starves the gateway's authz sidecar

Even with the gateway-direct design, first real load produced a cascade, diagnosed live: the
proportional split of TempoStack's `resources.total` (2Gi/2cpu per WP-079) hands the gateway's
`opa-openshift` sidecar ~2% - **40m CPU / 41Mi**. It survived WP-080's idle verification for a
day, then died (exit 137, liveness 1s-timeout kills) within 5 minutes of WP-081's fan-out going
live: the collector's retry backlog hammered the gateway, OPA saturated, the gateway went
unready, the EndpointSlice flipped `ready: false`, and every client's VIP path lost its
endpoints - meshed pods saw TLS resets from their own Envoy (empty upstream cluster), plain
pods saw gRPC deadlines, while `oc get pods` still showed `2/2 Running` on a stale look.
Debug method that cracked it: TLS to the gateway **pod IP** succeeded while the VIP failed →
endpoints, not the gateway. Fixes, both in reconcile.yml's TempoStack task: `resources.total`
raised to 4cpu/4Gi (OPA → 80m/82Mi; more would breach `zuno-platform-quota` limits.cpu) plus a
`spec.template.gateway.component.resources` override (500m/256Mi) for the main gateway
container - the override does NOT reach the opa sidecar, only the total does. One-time
recovery: deleted the `zuno-otel-collector` pod to drop its in-memory retry backlog so OPA
could come up against near-zero load.

## Verification checklist

1. ✅ `oc get opentelemetrycollector zuno-otel-collector -n zuno-monitoring -o yaml` shows the
   `otlp/rhoai` exporter (gateway:8090 + bearertokenauth) in the `traces` pipeline;
   collector logs clean - zero `Exporting failed` over the final observation minute.
2. ✅ Real embedding call (`oc exec deploy/rag-service -n zuno-data` → POST
   `http://embeddings-predictor.zuno-ai-run.svc:8080/v1/embeddings`, HTTP 200) → RHOAI Tempo
   search (`/api/traces/v1/redhat-ods-monitoring/tempo/api/search`, bearer token) returns a
   non-empty `traces` array: 20 traces including Envoy-originated spans (comage-bff, tekos-bff,
   advantage-bff, postgres sidecars) and app spans (agent-bff `bff_request`); filtered search
   `tags=service.name=embeddings-predictor.zuno-ai-run` → 10 traces
   (`isvc.embeddings-predictor.zuno-ai-run`).
3. ✅ Regression: same filtered search against `zuno-monitoring`'s Tempo
   (`tempo-tempo:3200/api/search`) still returns embeddings traces - existing Grafana path
   intact.

## Follow-up hardening (2026-08-26, after closure)

Both live findings above were one-off patches; this turned them into properties of the platform.
No new ADR/WP - the decisions are unchanged, this is robustness only.

**The trace pipeline can no longer starve silently.** The TempoStack right-sizing moved out of
`reconcile.yml` into a shared
`ansible/roles/openshift_ai/tasks/right_size_monitoring_stack.yml`, now included by
`install.yml` too - it had only ever run on the reconcile path, so a **fresh install** came up
with RHOAI's starving defaults and a pipeline that looks healthy while dropping every span.
Install needs an `until`/`retries` wait the reconcile path didn't: RHOAI creates the TempoStack
asynchronously after the DSC goes Ready, so a bare lookup there would silently no-op.
`precheck.yml` (i.e. `make d1 check openshift-ai`) gains a tripwire for the failure mode itself -
gateway pod not fully ready, or the `opa-openshift` sidecar sized below a floor
(`openshift_ai_tempo_opa_min_memory_mb`, default 64). Memory is parsed from raw bytes as well as
Mi/Gi because the Tempo Operator's split emits `85899344`, which a Mi-only parse would read as 85
million MiB and wave through. Verified live both ways: silent at the real 81Mi, fires with
`-e openshift_ai_tempo_opa_min_memory_mb=999`.

**Silent ArgoCD drift now explains itself.** New `platform/gitops/argocd_drift.py` asks ArgoCD's
own `managed-resources` API which fields differ (desired-as-subset, so operator-defaulted fields
aren't reported), restricted to resources ArgoCD itself marks OutOfSync - without that filter,
anything covered by `ignoreDifferences` false-positives, since ArgoCD strips ignored fields from
the normalized live state. `ansible/tasks/diagnose_gitops_app.yml` (shared by ~30 roles) now uses
it for the `cause` in place of `no health message reported`, and points at a git-side fix rather
than "re-sync" - a canonicalization mismatch survives any number of re-syncs. Proven against the
cluster's genuinely OutOfSync apps (`OAuth/cluster spec.identityProviders: git="<1 items>"
live="<2 items>"`) and silent on every Synced one.

**Latent instances of the same trap, closed:** `gitops/charts/kueue/templates/queue-resources.yaml`
rendered `v1beta1` while `v1beta2` is storage with a conversion webhook - the exact DSCI topology,
no duration fields today but a trap for whoever adds one - now bumped; `mariadb`'s
`PhysicalBackup.spec.maxRetention` pre-canonicalized to `168h0m0s`; and a deliberately **narrow**
`ignoreDifferences` on `/spec/monitoring/traces/storage/retention` in
`gitops/apps/openshift-ai/application-d1.yaml` (a blanket `/spec` ignore would blind real drift).
That last one also closes a process bug: `application-d0.yaml` already carried a DSCI `/spec`
ignore, but d0 sets `DSCInitialization.enabled: false` - the guard was written for the
Application that doesn't render the resource and omitted from the one that does. A repo-wide
sweep found **no other active drift** (104 of 106 Applications Synced; the two that aren't are
vendor apps outside `gitops/apps/`).

## Status updates

- WP-081 → Done (live-verified 2026-08-26). ADR-0523 stays `To be implemented` until WP-082's
  workload-level path is also live.
- 2026-08-26 follow-up: hardening above landed; no ADR/WP status change (decisions unchanged).
