# WP-079: Enable RHOAI monitoring traces (Tempo, dedicated S3 bucket)

- **State:** Done (live-verified 2026-08-26). Full metrics+traces stack Running in
  `redhat-ods-monitoring`: Prometheus/Alertmanager/Perses/Thanos-querier/OTel collector and every
  TempoStack component (distributor/ingester/querier/query-frontend/compactor/gateway) all
  `Running`, 0 CrashLoopBackOff. Three live-found bugs fixed same day (see "Live incident" and
  "Second correction" below, plus the TempoStack resources fix below that).
- **ADRs:** ADR-0522 (Implemented)
- **Depends on:** WP-078 (metrics — same `DSCInitialization.spec.monitoring` block)
- **Related:** WP-080 (Perses/Route/dashboard verification, next)

## Goal

Populate `DSCInitialization.spec.monitoring.traces` so RHOAI provisions its own
`TempoStack`/`TempoMonolithic` and `OpenTelemetryCollector` in `redhat-ods-monitoring`, backed
by a dedicated S3 bucket — the second of three side-by-side monitoring increments (ADR-0522).

## Why

Same root cause as WP-078: the DSCI's own status names it (`TracesNotConfigured`,
`OpenTelemetryCollectorAvailable: False`). Traces storage was chosen as S3 (not PV) for
durability, wired through the same Vault -> `ExternalSecret` -> Secret chain
`gitops/charts/aap/templates/externalsecret-hub-s3.yaml` already established for Automation
Hub's S3 storage — a dedicated bucket, `zuno-demo-rhoai-traces`, rather than reusing an existing
one, to keep this fully side-by-side and independently lifecycled.

## What changed

- `ansible/confidential.yml` / `ansible/confidential.example.yml`: new vars
  `zuno_rhoai_traces_s3_bucket_name` (`"zuno-demo-rhoai-traces"`), `zuno_rhoai_traces_s3_region`,
  `zuno_rhoai_traces_s3_access_key_id`, `zuno_rhoai_traces_s3_secret_access_key` — same 4-field
  shape as `zuno_aap_hub_s3_*`. **Access key/secret are still the `"xxxxxx"` placeholder** —
  operator fills these in once the bucket and a bucket-scoped IAM user exist.
- `ansible/roles/vault/tasks/install.yml`: new `vault kv put zuno/rhoai/traces-s3 bucketName=...
  region=... accessKeyId=... secretAccessKey=...` task, right after the AAP Hub S3 one, same
  `when: ... != 'xxxxxx'` guard on all four vars, `no_log: true`. No-ops until the real
  credentials are filled in above.
- New `gitops/charts/openshift-ai/templates/externalsecret-traces-s3.yaml`: `ExternalSecret` from
  `zuno/rhoai/traces-s3` -> Secret `rhoai-traces-s3-credentials` in `redhat-ods-monitoring`. Key
  **transform, not a straight copy**: Vault stores `bucketName`/`region` (this repo's own
  AAP-established convention) but the rendered Secret uses `bucket`/`endpoint`/`access_key_id`/
  `access_key_secret` — the keys the Tempo Operator's own S3 secret schema expects (confirmed
  against Red Hat Tempo Operator docs); `endpoint` is derived as `s3.<region>.amazonaws.com`.
- `gitops/charts/openshift-ai/values.yaml`: new `tracesS3:` block (same two-gate shape as
  `maasDb:`), and `cluster-ods.DSCInitialization.spec` extended with `monitoring.traces`
  (`sampleRatio: "1.0"`, `storage.backend: s3`, `storage.secret:
  rhoai-traces-s3-credentials`, `storage.retention: 48h`). `storage.secret` is required once
  `backend != pv` (CRD validation); the CRD also forbids `storage.size` for a non-`pv` backend,
  deliberately omitted.
- `gitops/apps/openshift-ai/application-d1.yaml`: `tracesS3: enabled: true` alongside the
  existing `DSCInitialization.enabled: true`.
- Verified with `helm lint`/`helm template` on `gitops/charts/openshift-ai` — the rendered
  `DSCInitialization` and `ExternalSecret` both parse and match the live cluster's own
  `dscinitializations.dscinitialization.opendatahub.io` CRD schema (`oc explain`).

## Live incident during first reconcile (2026-08-26, fixed same day)

The bucket/credentials were seeded and `make d1 reconcile openshift-ai` run; ArgoCD stayed
`OutOfSync`/never converged and two PVCs sat `Pending`. Two independent, real bugs, both
confirmed from `oc get dsci default-dsci -o jsonpath='{.status.conditions}'` and namespace
events, neither a cluster drift issue:

1. **TempoStack admission webhook rejection.** The DSCI's own `Ready`/`ProvisioningSucceeded`
   conditions on the generated `TempoStack` named the exact cause: `"endpoint" field of storage
   secret must be a valid URL`. `externalsecret-traces-s3.yaml` rendered a bare hostname
   (`s3.eu-west-2.amazonaws.com`); the Tempo Operator's `vtempostack` webhook requires a full URL
   with scheme. Fixed: `endpoint: "https://s3.{{ .region }}.amazonaws.com"`.
2. **`redhat-ods-monitoring`'s `ResourceQuota` already exhausted.** `oc get events` showed four
   separate `FailedCreate ... exceeded quota: zuno-platform-quota` (Prometheus, Alertmanager,
   Perses, the OTel collector's target-allocator) — the two `Pending` PVCs
   (`prometheus-data-science-monitoringstack-db-...`, `storage-data-science-perses-0`) were a
   downstream symptom: `gp3-csi` is `WaitForFirstConsumer`, so a PVC stays `Pending` until its
   pod is actually scheduled, and these pods were never even created. The namespace's quota
   (`gitops/charts/namespaces/values.yaml`, `redhat-ods-monitoring` entry) was sized for the
   original empty-namespace baseline (500m cpu/1Gi mem requests, 4 cpu/8Gi mem limits) — already
   at 410m/916Mi from the OTel collector (×2) and the two Prometheus/Thanos proxies alone, before
   Prometheus/Alertmanager/Perses/target-allocator/TempoStack's several components ever start.
   Raised to `requests: 2 cpu / 6Gi`, `limits: 4 cpu / 10Gi` (limits.cpu kept at 4 — an explicit
   choice, not auto-derived).

## Second correction (2026-08-26, same day): limits.cpu exhausted again

The first quota bump above was still wrong once the full stack actually existed:
`limits.cpu: used: 3970m` out of `4` blocked Tempo's `compactor`/`gateway` Deployments from ever
creating a pod (`FailedCreate ... exceeded quota`), and the `prometheus`/`alertmanager`/`perses`
StatefulSets showed 0 pods created. Computed the real need directly from every workload's
declared pod-spec resources in the namespace (`oc get statefulset,deployment -n
redhat-ods-monitoring -o json`, summed per-container × replica count, with the namespace's own
`LimitRange` defaults — `defaultRequest: cpu=100m`, `default: cpu=1` — applied to containers that
don't set their own value, e.g. Perses, the OTel target-allocator, Thanos-querier): **~1338m**
effective `requests.cpu`, **~9220m** effective `limits.cpu` across the whole namespace. Set with
headroom above a +40% margin on that measurement: `requests: { cpu: "4", memory: "15Gi" }`,
`limits: { cpu: "14", memory: "40Gi" }`.

## Third correction (2026-08-26, same day): TempoStack's own resources.total is hardcoded too small

Once the quota fix above unblocked pod creation, Tempo's components still failed
(`CrashLoopBackOff`/`OOMKilled`) — a completely separate bug. RHOAI's monitoring service
generates the `TempoStack` CR (`data-science-tempostack`, `redhat-ods-monitoring`) with
`spec.resources.total` hardcoded to `limits: 1cpu/256Mi`, `requests: 100m/256Mi` — unrelated to
anything `DSCInitialization.spec.monitoring.traces` exposes (that field has no `resources` knob
at all). The Tempo Operator proportionally splits that 256Mi across all 7 containers
(distributor/ingester/querier/query-frontend/compactor/gateway/gateway-opa), leaving
`query-frontend` with a **~5MB** memory limit.

Also found live: the `zuno_rhoai_traces_s3_*` credentials in `confidential.yml` were identical to
`zuno_aap_hub_s3_*` — that IAM user (`zuno-sxa-corpus-s3`) had no policy grant on the new
`zuno-demo-rhoai-traces` bucket (`s3:ListBucket` denied). Fixed on the AWS/operator side (IAM
policy), not in this repo.

Confirmed live (2026-08-26) that patching `TempoStack.spec.resources.total` directly (`limits:
2cpu/2Gi`, `requests: 500m/1Gi`) is **not** reverted by RHOAI's own reconciler — held steady
across a >3.5 minute observation window, and the Tempo Operator propagated it down to every
component proportionally. This is not a fight against another controller; RHOAI just never
revisits the field after generating the CR once. Persisted as a new remediation block in
`ansible/roles/openshift_ai/tasks/reconcile.yml` (same state-restoring, idempotent shape as this
file's existing InstallPlan-approval/istio-ca-root-cert/ipp-sidecar remediations) — re-applied on
every `make d1 reconcile openshift-ai`, so it's also self-healing if the CR is ever recreated from
scratch (uninstall/reinstall, fresh redeploy).

## Verification checklist

1. ✅ Created the `zuno-demo-rhoai-traces` S3 bucket and IAM access, filled into
   `ansible/confidential.yml`.
2. ✅ `make d0 install vault` seeded `zuno/rhoai/traces-s3`.
3. ✅ `make d1 reconcile openshift-ai` (run repeatedly across the three corrections above).
4. ✅ `oc get dsci default-dsci -o jsonpath='{.status.conditions}'` shows `TempoAvailable` and
   `OpenTelemetryCollectorAvailable` both `True`.
5. ✅ `oc get pods -n redhat-ods-monitoring` — every component (Prometheus ×2, Alertmanager ×2,
   Perses, OTel collector ×2 + target-allocator, Thanos-querier, and all 6 TempoStack components)
   `Running`, 0 `CrashLoopBackOff`/`OOMKilled`.
6. ⬜ Trigger a real inference call through an existing KServe/MaaS model endpoint and confirm a
   trace lands in RHOAI's own Tempo (not `zuno-monitoring`'s) — deferred to WP-080 alongside the
   Perses/Route verification, since it needs the same live-traffic check.

## Status updates

- ADR-0522 → `Implemented`. The condition stated here in the future tense ("stays `Proposed`
  until WP-080 also lands and verifies") was met on 2026-08-26: WP-080 closed `Done
  (live-verified)` and carried the ADR to `Implemented`. This WP closed the traces half of that
  acceptance criteria; its own `ADRs:` annotation lagged until 2026-08-27.
- Item 6 above stayed ⬜ on purpose. WP-080 ran that live-traffic check and root-caused the
  absence of traces to two deliberate phase-1 scope decisions, not a defect - see WP-080's
  "Live finding".
