# WP-080: Perses Route, Dashboard verification, and phase-1 closure

- **State:** Done (live-verified 2026-08-26).
- **ADRs:** ADR-0522 (Implemented)
- **Depends on:** WP-078 (metrics), WP-079 (traces)
- **Related:** phase-2 unification (not yet an ADR/WP - see "Live finding" below)

## Goal

Give RHOAI monitoring's Perses dashboards a direct access path, confirm RHOAI Dashboard's
"Observe" tab surfaces the same live data, and verify a real inference call produces a trace in
RHOAI's own Tempo - the last item WP-079 deferred. Closes out ADR-0522's phase-1 scope
(side-by-side, RHOAI-managed-workloads-only, zero application code changes).

## What changed

- New `gitops/charts/openshift-ai/templates/route-perses.yaml` + `persesRoute` values block +
  `gitops/apps/openshift-ai/application-d1.yaml` opt-in: a bare edge `Route`
  (`data-science-perses-route`) to `data-science-perses:8080` in `redhat-ods-monitoring`. Your
  explicit choice: RHOAI already exposes Prometheus (x2) and Thanos-querier the same
  unauthenticated way in this namespace (verified live: `HTTP 200` with no credentials), and
  Perses itself has no built-in auth (single container, no oauth-proxy, no `--oidc` flag) - this
  matches that existing precedent rather than introducing a new gap.
- Live-verified: `HTTP 302` (edge redirect) then `HTTP 200` serving the Perses UI, no credentials.

## Verification checklist

1. ✅ `oc get route data-science-perses-route -n redhat-ods-monitoring` exists; `curl` confirms
   `302` → `200`.
2. ⬜ RHOAI Dashboard's "Observe" tab (`rhods-dashboard` route, already authenticated) - not
   click-through-verified via an authenticated browser session (would need a Playwright pass,
   per this repo's established frontend-verification method). Circumstantial evidence it works:
   every relevant `DSCInitialization` condition (`MonitoringStackAvailable`, `TempoAvailable`,
   `PersesAvailable`, etc.) is `True` and the `rhods-dashboard` pods are `Running` - RHOAI's
   documented behavior is to surface Observe once these are green. Not blocking closure; a light
   follow-up if ever needed.
3. ✅ (attempted, root cause found - see below) Triggered a real inference call
   (`qwen3-embedding-0.6b` via `embeddings-predictor.zuno-ai-run.svc`, `HTTP 200`) and searched
   RHOAI's Tempo (`tempo-data-science-tempostack-gateway`'s `/api/traces/v1/redhat-ods-monitoring/
   tempo/api/search`) for a resulting trace in the following 15 minutes: **zero traces found.**
   Diagnosed, not a bug - see below.

## Live finding: nothing sends RHOAI's Tempo data yet, by design

Two independent, real root causes, both confirmed live:

1. **KServe pods aren't auto-instrumented.** `oc get instrumentation -A` shows
   `data-science-instrumentation` (`redhat-ods-monitoring`) pointing at RHOAI's own collector via
   the standard OpenTelemetry Operator auto-injection mechanism - which only activates on pods
   carrying a specific `instrumentation.opentelemetry.io/inject-<lang>` annotation.
   `embeddings-predictor` (and every other InferenceService this repo deploys,
   `gitops/charts/models/templates/inferenceservice-embedding.yaml`/
   `llminferenceservice-{gptoss,qwen}.yaml`) carries none.
2. **The mesh's tracing provider points at the *other* stack.** The `Istio` CR's
   `meshConfig.extensionProviders` (`otel-tracing`,
   `gitops/charts/service-mesh/templates/istio.yaml:157-159`, referenced by
   `gitops/charts/service-mesh/templates/telemetry.yaml`) is hardcoded to
   `zuno-otel-collector-collector.zuno-monitoring.svc.cluster.local:4317` - the existing stack.
   This is what would otherwise generate gateway/Envoy-level spans for MaaS Gateway traffic.

Both are exactly the "dual-export application-level telemetry" work ADR-0522's Migration/
evolution section explicitly deferred to a second phase - not implemented here, deliberately.
RHOAI's Tempo/Prometheus/Perses stack is live and healthy; it is simply, by design, empty of
real traffic data until a phase-2 decision wires one or both paths to it. That decision is
scoped as a follow-up (see below) rather than folded into this WP.

## Status updates

- ADR-0522 → `Implemented`: every phase-1 acceptance point (metrics, traces, Perses, side-by-side
  scope, zero app-code changes) is live-verified. The "zero cross-stack data flow" state is the
  *intended* phase-1 outcome per the ADR's own Decision, not an unmet criterion.
- `docs/adr/README.md`'s ADR-0522 row → `Implemented`.

## Phase 2 (not started, no ADR/WP number yet)

Unify (or bridge) the two stacks so real traffic actually lands in RHOAI's Tempo, per this WP's
"Live finding" above. Two independent, composable options identified, not mutually exclusive:

- **Mesh-level:** point (or dual-point) the `otel-tracing` extensionProvider at RHOAI's collector
  (`data-science-collector.redhat-ods-monitoring.svc.cluster.local:4317`) - infra-level, covers
  MaaS Gateway/Envoy spans without touching application code.
- **Workload-level:** add the OpenTelemetry auto-instrumentation annotation to this repo's own
  `InferenceService`/`LLMInferenceService` pod templates - covers in-process vLLM/KServe spans.

Neither is implemented yet. A dedicated agent session has been briefed to start this
investigation/implementation (see handoff prompt, not stored in-repo).
