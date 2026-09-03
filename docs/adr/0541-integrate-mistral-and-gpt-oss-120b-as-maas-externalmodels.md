# ADR-0541: Integrate mistral and gpt-oss-120b as MaaS ExternalModels

- **Status:** Proposed - blocked on a RHOAI `payload-processing` ext_proc
  plugin defect that rejects every `ExternalModel` request as a "model
  mismatch" (root-caused 2026-09-03, see Decision 1); the
  originally-diagnosed Gateway-attachment defect is confirmed fixed
  on RHOAI 3.5.0 GA (re-verified 2026-09-03, see Decision 1)
- **Target:** v0.7
- **Date:** 2026-09-03 (extracted from ADR-0537, originally proposed
  2026-09-01; route-identity finding confirmed 2026-09-02, re-tested and
  found fixed - with a different blocker in its place - 2026-09-03 on
  RHOAI 3.5.0 GA)
- **Decision owners:** Zuno Demo architecture team

## Context

**Split note:** this ADR was extracted, unreworded, from
[ADR-0537](0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md)
on 2026-09-03. ADR-0537 originally bundled this decision with an unrelated
`HardwareProfile` decision from the same diagnostic session; that half is
now `Implemented` and stays in ADR-0537. This ADR carries only the
`ExternalModel`/MaaS half, which remains blocked upstream.

Two SaaS chat models sit outside MaaS governance. `mistral`
(native Mistral API, `api.mistral.ai`) and `gpt-oss-120b`
(OVHcloud AI Endpoints, ADR-0416) are called directly from `ai-gateway`
(`components/ai-gateway/app/providers.py`), with credentials mounted
directly into that component. Since ADR-0521, every **local** model's
traffic is routed through the RHOAI MaaS governance plane
(`MaaSModelRef`/`MaaSSubscription`/`MaaSAuthPolicy`), giving group-based
access control and platform-native rate limiting. These two external models
get neither - they are governed only by Zuno's own C1/C2/C3 classification
(ADR-0021) and the fleet-wide OVHcloud eligibility/exclusion rules ADR-0416
already established (Finage excluded via `zuno.model.local_only: true`).

The transport for a MaaS-routed SaaS candidate already exists in skeleton
form: `components/ai-gateway/app/maas_adapter.py::should_use_maas()`
(lines 110-124) has a third gate, `candidate_kind != "local" and not
MAAS_EXTERNAL_EGRESS_ENABLED`, anticipated since ADR-0201/WP-27 but never
exercised - no `provider-routing.yaml` entry sets `via_maas: true` on a SaaS
candidate, and `MAAS_EXTERNAL_EGRESS_ENABLED` is never set to `true`. This is
a gap to **activate**, not a mechanism to build from zero.

RHOAI's `ExternalModel` CRD was explicitly evaluated and rejected once
before, in ADR-0201, for a **local** vLLM Service - the CRD's
`externalProviderRefs[].ref` → `ExternalProvider` shape requires an
authenticated external FQDN + `auth` config, which does not fit an
unauthenticated in-cluster Service. That is exactly the shape of `mistral`
and `gpt-oss-120b`, both genuine external, authenticated SaaS endpoints -
`ExternalModel` is the right fit here, unlike in its original evaluation.

Live verification during this ADR's preparation confirmed:
- Two distinct `ExternalModel` CRDs exist on this cluster:
  `externalmodels.inference.opendatahub.io` (generic, multi-provider,
  weighted `externalProviderRefs[]`) and `externalmodels.maas.opendatahub.io`
  (single-provider: `endpoint`, `provider`, `targetModel`,
  `credentialRef.name`). `MaaSModelRef.spec.modelRef.kind: ExternalModel`
  is the `maas.opendatahub.io` one - it is the one referenced throughout
  ADR-0201 and is the one this ADR uses.
- `spec.provider` is a free string with no CRD-level enum
  (`oc apply --dry-run=server` accepted `provider: mistral` without
  rejection) - no admission webhook validates it; behaviour depends on the
  `maas-controller` reconciler at runtime, unverified until a live call
  succeeds.
- `credentialRef` requires the referenced Secret's data key to be literally
  `api-key`. The existing Secrets (`llm-provider-mistral`,
  `llm-provider-ovhcloud`, both `ExternalSecret`-managed) use `api_key`. This
  is a real mismatch this ADR must resolve, not a naming nit.

## Decision

1. **Publish `mistral-large-latest` and `gpt-oss-120b` as `ExternalModel` +
   `MaaSModelRef`**, bringing both under the same governance plane as local
   models, with **no change to which upstream endpoint each one calls**:

   ```yaml
   apiVersion: maas.opendatahub.io/v1alpha1
   kind: ExternalModel
   metadata:
     name: mistral-large
     namespace: zuno-ai-run
   spec:
     endpoint: api.mistral.ai
     provider: mistral
     targetModel: mistral-large-latest
     credentialRef:
       name: llm-provider-mistral-maas   # mirror Secret, see below
   ---
   apiVersion: maas.opendatahub.io/v1alpha1
   kind: ExternalModel
   metadata:
     name: gpt-oss-120b-ovhcloud
     namespace: zuno-ai-run
   spec:
     endpoint: oai.endpoints.kepler.ai.cloud.ovh.net
     provider: openai-compatible
     targetModel: gpt-oss-120b
     credentialRef:
       name: llm-provider-ovhcloud-maas   # mirror Secret, see below
   ```

   Each is paired with its own `MaaSModelRef` (`modelRef.kind: ExternalModel`)
   in the existing `range .Values.maas.models` loop
   (`gitops/charts/models/templates/maas.yaml`), and its own
   `MaaSSubscription` set, **reusing the exact per-group pattern already in
   production** for local models (`values.yaml`'s `maas.models[].
   subscriptions`): `group: agent_tekos` (priority 10), `group: sales`
   (priority 1), and a catch-all `user:
   system:serviceaccount:zuno-ai-run:ai-gateway` (priority 100) - not a
   single shared subscription.

   **Explicit decision: `mistral` stays on its native API** -
   `api.mistral.ai`, not OVHcloud. Only `gpt-oss-120b` uses OVHcloud. Wrapping
   `mistral` in `ExternalModel` changes its governance, not its endpoint or
   credential.

   **Secret key mismatch.** `ExternalModel.spec.credentialRef` requires a
   Secret with a data key literally named `api-key`; the existing
   `ExternalSecret`-managed Secrets (`llm-provider-mistral`,
   `llm-provider-ovhcloud`) use `api_key`. Per ADR-0416/ADR-0415's
   already-settled principle ("one key per account, not per model" -
   not reopened here), a **dedicated mirror Secret** is created by a new
   Helm template (`gitops/charts/models/templates/externalmodel-*.yaml`),
   sourced from the same Vault path (`providers/mistral`,
   `providers/ovhcloud`) as a second `ExternalSecret` target with the
   required key name - rather than editing the existing `ExternalSecret`'s
   key name and risking every current direct-call consumer.

   **Finage's exclusion from `gpt-oss-120b`** (ADR-0416,
   `zuno.model.local_only: true`) stays enforced **only** in `ai-gateway`'s
   own routing/classification layer, not duplicated into
   `MaaSAuthPolicy.spec.subjects`. Zuno's classification is already the
   stricter outer policy (ADR-0521's Security considerations framing);
   duplicating the exclusion into MaaS would create a second source of
   truth that can silently drift from the first.

   **Route-identity risk (inherited from ADR-0201) - now resolved, negatively,
   2026-09-02.** MaaS's subscription selection keys on `<modelRef
   namespace>/<modelRef name>`, while KServe's own adopted-Gateway
   publication used `publishers/<ns>/<model>` for a local
   `LLMInferenceService` - a mismatch that cost two days to debug for
   `gpt-oss-20b`. An `ExternalModel` has no KServe workload to adopt a route
   from, so whether the same mismatch class applies here was an open
   question. Live-verified after deploying both `ExternalModel`s: it is
   **worse than a naming mismatch** - `MaaSModelRef` for both
   `mistral-large-maas` and `gpt-oss-120b-ovhcloud-maas` reports `phase:
   Failed`, `reason: ReconcileFailed`, `message: 'Failed to reconcile
   HTTPRoute: HTTPRoute zuno-ai-run/<name> does not reference gateway
   openshift-ingress/maas-default-gateway (found: openshift-ingress/
   default-gateway)'`. The `HTTPRoute` `maas-controller` auto-generates for
   an `ExternalModel` backend attaches to a Gateway literally named
   `default-gateway` - which does not exist as a `Gateway` object on this
   cluster at all (it is the name of RHOAI's own `GatewayConfig`, a
   different resource kind that generates the actual `Gateway/
   data-science-gateway`) - instead of `maas-default-gateway`, the Gateway
   `maas-controller`'s own `--gateway-name`/`--gateway-namespace` flags
   correctly declare (confirmed live: `maas-controller`'s Deployment passes
   exactly `--gateway-name=maas-default-gateway
   --gateway-namespace=openshift-ingress`). `MaaSSubscription` fails in
   cascade (`TokenRateLimitPolicies` cannot attach to an unprogrammed
   route). No field in `ExternalModel.spec`, `MaaSModelRef.spec`, or the
   cluster-wide `Config` CRD (`maas.opendatahub.io`, `spec` is reserved/
   empty in v1alpha1) exposes a way to override this from our side - it is
   a `maas-controller` defect, not a configuration gap.

   **Confirmed as a known, currently-open upstream gap** (not something
   specific to this cluster), via `opendatahub-io/models-as-a-service`:
   - [Issue #1417](https://github.com/opendatahub-io/models-as-a-service/issues/1417)
     ("stop legacy ExternalModel reconciler when inference CRD exists")
     confirms the `maas.opendatahub.io` `ExternalModel` API this ADR uses is
     explicitly termed **legacy**, being superseded by a separate
     `inference.opendatahub.io` reconciler; the two can create duplicate/
     conflicting networking resources for the same model when both exist.
   - [Issue #1399](https://github.com/opendatahub-io/models-as-a-service/issues/1399)
     ("auto-resolve tenantRef from HTTPRoute gateway", RHOAIENG-87566) is
     the actual fix: a reverse-lookup against every `AITenant`'s
     `status.gatewayRef` to resolve which Gateway an `ExternalModel`'s
     route should really attach to - exactly the missing step here (our
     `AITenant/models-as-a-service` already correctly declares
     `spec.gateway.name: maas-default-gateway`; nothing consults it today).
     **Labelled `3.6-EA2`** - the next RHOAI release, not yet in the `3.5
     EA2` this platform runs (ADR-0002).
   - [Issue #1240](https://github.com/opendatahub-io/models-as-a-service/issues/1240)
     ("ExternalModel discovery still returns path-based status.endpoint
     instead of BBR gateway URL"), labelled `bug`/`3.5`, independently
     confirms `ExternalModel` routing/discovery is known-incomplete in our
     exact deployed version.

   **Conclusion, 2026-09-01/02: blocked upstream, not a configuration or
   workaround problem** (superseded in part below). No rename, annotation,
   or manifest change on our side could fix this (see the live
   investigation that ruled out renaming `zuno-agent-gateway` to
   `default-gateway`/`maas-default-gateway` - it would only mask the
   symptom, since Kuadrant's `AuthPolicy`/`TokenRateLimitPolicy` for MaaS
   governance are bound to `maas-default-gateway` specifically, not to
   whichever object holds a given name).

   **Re-verified live, 2026-09-03 (RHOAI 3.5.0 GA -
   `installedCSV=rhods-operator.3.5.0`, `channel=stable-3.5`, confirmed GA
   not EA2).** The Gateway-attachment defect above is **fixed**: both
   `MaaSModelRef`s now report `phase: Ready`, `reason: Reconciled`; their
   `HTTPRoute`s correctly `parentRef` `Gateway/maas-default-gateway` in
   `openshift-ingress` (`status.parents`: `Accepted: True`,
   `ResolvedRefs: True`), with Kuadrant's `AuthPolicyAffected`/
   `TokenRateLimitPolicyAffected` both `Accepted: True`; all 6
   `MaaSSubscription`s (`mistral-large-{ai-gateway,sales,tekos}`,
   `gpt-oss-120b-ovhcloud-{ai-gateway,sales,tekos}`, `models-as-a-service`
   namespace) are `Active`, priorities matching spec. **Root cause of the
   fix is unconfirmed - not assumed to be #1399**: that issue is still
   open upstream with no backport recorded, yet the symptom is gone; no
   `maas-controller` Deployment could be found on this build at all (only
   `maas-api`/`maas-ui`, in `redhat-ods-applications`), so the
   reconciler's naming/architecture may simply have changed on this
   build. `oc get aitenant -A` returns nothing despite the CRD existing -
   not chased further, worth a follow-up look.

   **But the live smoke test still cannot pass, for a different reason.**
   A completion request must key `X-Gateway-Model-Name` off the full
   `<namespace>/<name>-maas` identity (e.g. `zuno-ai-run/mistral-large-
   maas`), not a bare model name - confirmed by a working local-model
   control, `zuno-ai-run/qwen35-9b-maas`, returning a real HTTP 200 (this
   matches how `maas_adapter.py`'s real `maas_model_ref` config value
   already sends it, so live `ai-gateway` traffic would never hit this
   naming trap). Once the identity is corrected, AuthZ/subscription-
   matching passes cleanly for both `ExternalModel`-backed routes too -
   then the request **times out (60s, no response)** reaching the real
   upstream through the MaaS gateway's Envoy passthrough proxy. Ruled out:
   double-TLS (WP-124's plaintext `DestinationRule` correctly wins over
   the `ExternalModel` reconciler's own `mode: SIMPLE` one - the Envoy
   cluster for `api.mistral.ai` shows `transport_socket: None`);
   `NetworkPolicy` (`ai-gateway`'s policy is ingress-only, no egress
   rule); general egress/DNS/TLS (a direct call from the same
   `ai-gateway` pod straight to `https://api.mistral.ai/v1/models`,
   bypassing the MaaS gateway Service entirely, succeeds in 0.1s with a
   real `401 Invalid API Key`). Root cause not identified - Envoy debug
   logs/packet capture are the next step, not yet taken.

   **Conclusion, 2026-09-03: still blocked, but the blocker changed
   class.** No rename, annotation, or manifest change on our side fixed
   the original Gateway-attachment defect - RHOAI's own 3.5.0 GA build
   did, for a reason this platform did not cause and cannot confirm. What
   blocks a live completion today is the Envoy-proxy timeout above, a
   different failure with no known upstream issue tracking it yet - not
   the route-identity mismatch this Decision originally diagnosed.
   Re-evaluate once that timeout is root-caused; re-entry no longer
   depends on a RHOAI version bump, since the version this was pinned to
   (3.6-EA2) is not what actually changed.

   **Root-caused, 2026-09-03 (continued investigation, same day).** The
   "timeout" is not a network/TLS/DNS problem at all - the request never
   leaves the cluster. `maas-default-gateway-istio`'s own Envoy (not
   `ai-gateway`'s sidecar, which is irrelevant to this hop) correctly
   originates real TLS to both upstreams (`config_dump` shows a genuine
   `UpstreamTlsContext` on `outbound|443||api.mistral.ai` and the OVHcloud
   equivalent, TLS 1.2-1.3, system CA validation) - ruling out double-TLS
   on this pod too, not just `ai-gateway`'s. Debug-level Envoy logging on
   that pod during a live test shows the request is rejected by an
   ext_proc filter, `envoy.filters.http.ext_proc.ipp` (cluster
   `outbound|9004||payload-processing.openshift-ingress.svc.cluster.local`),
   *before* any upstream router logic for `mistral-large`/`gpt-oss-120b-
   ovhcloud` runs at all - `failure_mode_allow: false` on this filter
   (RHOAI's own setting, kept by design in
   `gitops/charts/openshift-ai/templates/maas-gateway-ipp-anchor.yaml`,
   see that file's own comments) turns the rejection into a local 404 (or,
   non-deterministically observed elsewhere, an indefinite hang - same
   underlying rejection, different Envoy-side handling of the streamed
   ext_proc protocol).

   `payload-processing`'s own logs name the exact defect: its
   `model-provider-resolver` plugin (`github.com/opendatahub-io/
   ai-gateway-payload-processing`, running on `llm-d/
   llm-d-inference-payload-processor@v0.1.0-rc.2`) extracts the
   `ExternalModel`'s bare name from the request path (`mistral-large`) and
   rejects with `"model mismatch between request body and ExternalModel"`
   / `"inference error: NotFound - model in request body
   'zuno-ai-run/mistral-large-maas' doesn't match ExternalModel"` -
   because the request body's `model` field carries the full
   `<namespace>/<name>-maas` identity, which Kuadrant's own
   `maas-gateway-auth` `AuthPolicy` *requires* earlier in the same filter
   chain (see the 2026-09-03 note above on Decision 1's route-identity
   fix). **No value can satisfy both checks at once**: this is a
   structural incompatibility between two RHOAI/Kuadrant components for
   an `ExternalModel` backend specifically, not a config error on our
   side, and not something this investigation searched for an existing
   upstream issue number for.

   This is architecturally distinct from the two previously-tracked gaps
   (#1417, #1399, #1240): those were about `HTTPRoute`/Gateway attachment
   and route-identity resolution; this is a request-body/path identity
   mismatch inside RHOAI's own metering ext_proc plugin, one that only
   triggers for `ExternalModel` backends (local `InferencePool`-backed
   models never hit this comparison at all). Unlike those, this one is
   *potentially workaroundable in this repo*: `maas-gateway-ipp-anchor.yaml`
   applies the `ipp`/`ipp-pre` filters at `context: GATEWAY` (every route,
   no scoping) - the same file's own comments describe the
   `typed_per_filter_config` mechanism RHOAI's own (broken) EnvoyFilter
   already uses to disable `ipp-pre` on specific routes
   (`maas-api-route.0`/`.1`); the same mechanism could, in principle,
   disable `ipp` for the two `ExternalModel`-backed routes here. **Not
   attempted** - it is a live change to a Gateway shared with every local
   model's production traffic, out of scope for this investigation pass.

   **`inference.opendatahub.io` native API explored, 2026-09-03 (same
   day) - confirmed dead end on this build, upstream integration gap, not
   a config error.** RHOAI 3.5.0 GA does ship the newer, generic
   `ExternalProvider`/`ExternalModel.inference.opendatahub.io` chain
   Red Hat documents (`ExternalProvider` = endpoint + auth;
   `ExternalModel.spec.externalProviderRefs[]` references one or more
   providers and `spec.modelName` sets the client-facing identity;
   `MaaSModelRef` is meant to publish it into MaaS governance) - live
   schema (`oc explain --recursive`) and a standalone canary
   (`mistral-large-inference-canary`, `ExternalProvider`+`ExternalModel`,
   no legacy parent) confirm the CRD/reconciliation half genuinely works:
   both went `Ready`, and critically **`spec.modelName` is accepted and
   preserved verbatim** - unlike the read-only `modelName` on the
   legacy-bridge-generated shadow (Decision 1's earlier finding). But two
   further live tests close this off entirely:
   - The canary's `HTTPRoute` is generated by a *different* controller
     (label `app.kubernetes.io/managed-by: ipp-external-model-reconciler`,
     vs. `maas-external-model-reconciler` for the legacy path) that has
     the *original* Gateway-attachment bug this Decision opened with -
     `parentRefs` pointed at the nonexistent `Gateway/default-gateway`,
     `status.parents: []`. The RHOAI 3.5.0 GA fix found above only landed
     on the legacy reconciler's path, not this one. (A manual `oc patch`
     of the `HTTPRoute`'s `parentRef` to `maas-default-gateway` persists
     without being reverted - the controller does not fight a child-object
     edit - but that is a live workaround, not a fix.)
   - `MaaSModelRef.spec.modelRef.kind: ExternalModel` **cannot resolve a
     standalone `inference.opendatahub.io/ExternalModel` at all**: a
     manually-created `MaaSModelRef` pointing at the canary by name never
     receives any `status` (no reconciliation attempt visible) and no
     `MaaSSubscription` is ever generated. `Config.maas.opendatahub.io/
     default` has `spec: {}` (confirmed empty, no group-mapping knob), and
     the `externalmodels.maas.opendatahub.io` CRD's own description says
     it is what's "referenced by MaaSModelRef resources" - the
     `inference.opendatahub.io` group is not a resolvable target for
     `MaaSModelRef` on this build. Consequence, live-verified: a real
     completion request using the canary's correct `modelName` is
     rejected by Kuadrant itself (`403`, `x-ext-auth-reason: not_found`/
     `Unauthorized`) *before* reaching `payload-processing` -
     `payload-processing`'s own logs never mention the canary at all. The
     model-mismatch question from the paragraph above could therefore
     not be confirmed or refuted this way; the chain is blocked one step
     earlier, for an unrelated reason.
   - **Name-collision test** (does creating a `maas.opendatahub.io/
     ExternalModel` under the *same name* as the standalone canary make
     the legacy reconciler adopt it, preserving `modelName`?): tried
     live, named `mistral-large-inference-canary` on both sides. Result:
     neither adoption nor overwrite - silent no-op. The pre-existing
     `inference.opendatahub.io` objects (`ExternalProvider`, `ExternalModel`,
     `HTTPRoute`, `Service`, `ServiceEntry`, `DestinationRule`) were
     completely untouched (unchanged `resourceVersion`, no new
     `ownerReferences`, ages unchanged), and the new legacy `ExternalModel`
     itself never produced any status, event, or child resource of its
     own (`oc describe` shows `Events: <none>`). The legacy reconciler
     appears to attempt creating its own same-named children, collide
     with the pre-existing ones, and give up without recording anything
     on the CR - not a mechanism this repo can lean on. All canary
     objects deleted after this test; live cluster confirmed clean.

   **Conclusion: the `ExternalProvider`/`ExternalModel`/`MaaSModelRef`
   architecture Red Hat documents for `inference.opendatahub.io` is real
   and works at the CRD/reconciliation layer, but `MaaSModelRef` - the
   only bridge into MaaS governance (subscriptions, quotas, the
   `AuthPolicy` `model_access` map) - cannot reference that group on
   RHOAI 3.5.0 GA. This is an upstream integration gap between two
   RHOAI/Kuadrant components, not a configuration error on our side, and
   not something a repo-side workaround can close (unlike the `ipp`
   filter scoping idea above, there is no per-route or per-object knob to
   attach here - `MaaSModelRef`'s resolution logic is compiled-in).
   No further investigation planned; re-evaluate if a future RHOAI
   release lets `MaaSModelRef` target `inference.opendatahub.io`, or if
   the `ipp` filter-scoping workaround above is ever attempted.**

2. **Activate the existing `via_maas` SaaS path in `ai-gateway`, then retire
   the direct-call branches (full cutover) - BLOCKED, do not execute yet.**
   The plan: set `MAAS_EXTERNAL_EGRESS_ENABLED=true`; add `via_maas: true`
   and `maas_model_ref: <published-name>` to the `mistral` and
   `ovhcloud-gpt-oss-120b` entries in `platform/ai-gateway/
   provider-routing.yaml`; once a live smoke test confirms both models
   answer correctly through MaaS, remove the old direct-`ChatOpenAI`/
   `ChatMistralAI` branches for these two providers from
   `components/ai-gateway/app/providers.py` - a full cutover, not a
   permanent dual path (unlike ADR-0521's own local-model fallback).

   **Status, 2026-09-02: blocked upstream, not attempted.** Decision 1's
   correction above establishes that `mistral-large-maas` and
   `gpt-oss-120b-ovhcloud-maas` cannot pass real traffic today - their
   `MaaSModelRef`/`MaaSSubscription` never leave `Failed`. Switching
   `ai-gateway` to `via_maas` for either provider now would break them
   outright (no working backend to route to). **The current direct-call
   path (`mistral`/`ovhcloud-gpt-oss-120b` in `provider-routing.yaml`,
   unchanged since before this ADR) stays the only functional path for
   these two providers** - `provider-routing.yaml` is deliberately left
   untouched by this ADR's implementation. Re-evaluate this Decision once
   RHOAI 3.6-EA2 (or later, carrying opendatahub-io/models-as-a-service#1399)
   is deployed and a live smoke test confirms `Ready`/successful completions
   through MaaS for both models - only then does "full cutover" become
   executable as originally planned.

   **Still blocked, 2026-09-03**: re-verification on RHOAI 3.5.0 GA fixed
   the Gateway-attachment defect but surfaced a new Envoy-proxy timeout
   (see Decision 1) - `mistral-large-maas`/`gpt-oss-120b-ovhcloud-maas`
   still cannot pass real traffic, so this Decision's precondition remains
   unmet, for a different reason than originally diagnosed.

## Consequences

`mistral` and `gpt-oss-120b` were meant to gain group-based access control
and rate limiting equivalent to local models, removing the last two SaaS
providers that bypass MaaS governance - **this part did not land**:
Decision 1's `ExternalModel` route-identity correction above found both
`MaaSModelRef`s permanently `Failed` on a confirmed upstream
`maas-controller` defect (RHOAI 3.5 EA2), not a configuration issue this
repo can fix. Net effect of this ADR on governance, as of 2026-09-02: zero
change for `mistral`/`gpt-oss-120b` - they keep bypassing MaaS exactly as
before, on their pre-existing direct-call path, with two now-inert
`ExternalModel`/`MaaSModelRef` objects sitting in `Failed` state until a
fixed RHOAI version is deployed. The cost in the meantime: a mirror Secret
per externally-published model (dormant, harmless), and `MaaSSubscription`/
`MaaSAuthPolicy` objects in `models-as-a-service` that report `Failed`
(visible clutter, not a security gap - Zuno's own C1/C2/C3 classification,
unaffected by any of this, is still the actual gate on these two providers
per ADR-0021/ADR-0521's "stricter outer policy" framing).

## Security considerations

No new Vault path is introduced - both mirror Secrets source from the
already-existing `providers/mistral`/`providers/ovhcloud` paths, preserving
ADR-0416/ADR-0415's "one key per account" principle. `ExternalModel.spec.
provider` has no CRD-level validation (confirmed via dry-run) - its
correctness is a runtime concern, not an admission-time guarantee.
Removing the direct-call branches in Decision 2 shrinks `ai-gateway`'s own
credential surface for these two providers once the cutover completes.

## Acceptance criteria

Beyond the Standard clauses - live verification, required before `Status`
can move to `Implemented`:

- The exact Secret key name (`api-key`) is confirmed live by a successful,
  real completion request through each `MaaSModelRef` - not just a `Ready`
  status.
- ~~The MaaS route-identity question flagged in Decision 1 is resolved by
  observation~~ - **answered, negatively, 2026-09-02; re-verified,
  positively, 2026-09-03**: on 2026-09-02 both `ExternalModel`-backed
  `MaaSModelRef`s were `Failed` - `maas-controller` attached their
  auto-generated `HTTPRoute` to a non-existent `Gateway/default-gateway`
  instead of the tenant's real `maas-default-gateway`. On RHOAI 3.5.0 GA
  (2026-09-03) this is **fixed**: both `MaaSModelRef`s report `phase:
  Ready`, correctly attached to `maas-default-gateway`. This specific
  criterion is now satisfied - see Decision 1's 2026-09-03 note for the
  live evidence and the open question of what actually fixed it (not
  confirmed to be
  [#1399](https://github.com/opendatahub-io/models-as-a-service/issues/1399),
  which remains open upstream).
- **Blocked upstream - not satisfiable today, blocker changed 2026-09-03,
  root-caused same day**: a live smoke test confirming real completions
  through `mistral-large-maas`/`gpt-oss-120b-ovhcloud-maas`, the Finage
  negative test, and the per-persona-group quota test below now block on
  RHOAI's own `payload-processing` ext_proc filter rejecting every
  `ExternalModel` request with `"model mismatch between request body and
  ExternalModel"` (see Decision 1's 2026-09-03 "Root-caused" note) -
  a structural identity-format conflict with Kuadrant's own `AuthPolicy`,
  not the route-identity defect that originally blocked them and not a
  config error on our side. None of the three can be attempted until
  either RHOAI fixes this plugin or this repo scopes the `ipp` filter
  away from these two routes (not attempted).
- A live negative test confirms Finage is still denied `gpt-oss-120b` after
  cutover (blocked - see above).
- A live test per persona group (`agent_tekos`, `sales`, catch-all) confirms
  the expected `MaaSSubscription` priority/quota is the one actually
  enforced (blocked - see above).
- The direct-call branches for `mistral`/`ovhcloud-gpt-oss-120b` in
  `providers.py` are **not touched by this ADR** - they remain the only
  functional path for these two providers until the above unblocks (see
  Decision 2's `2026-09-02` status note). Removing them is now a future
  Decision-2 follow-up, not part of this WP's current scope.

## References

- Work package: [WP-125](../roadmap/work-packages/wp-125-external-models-through-maas.md).
- `opendatahub-io/models-as-a-service` [#1417](https://github.com/opendatahub-io/models-as-a-service/issues/1417),
  [#1399](https://github.com/opendatahub-io/models-as-a-service/issues/1399),
  [#1240](https://github.com/opendatahub-io/models-as-a-service/issues/1240)
  - the upstream `ExternalModel`/`maas-controller` route-identity defect
    diagnosed 2026-09-02. **Note (2026-09-03):** this specific symptom is no
    longer reproducible on RHOAI 3.5.0 GA, though #1399 remains open
    upstream with no backport recorded - the fix's actual cause is
    unconfirmed. A separate, still-open Envoy-proxy timeout now blocks
    Decision 1/2 instead; see Decision 1's 2026-09-03 note.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md)
  - the MaaS governance plane this extends, and the source of the
    route-identity risk flagged in Decision 1.
- [ADR-0416](0416-consume-gpt-oss-120b-via-ovhcloud-ai-endpoints.md) - the
  OVHcloud credential/endpoint and Finage exclusion this ADR reuses without
  reopening.
- [ADR-0521](0521-route-local-model-traffic-through-maas.md) - the local-model
  MaaS cutover and per-group `MaaSSubscription` pattern this ADR extends to
  external models.
- [ADR-0537](0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md)
  - the sibling ADR this one was split from 2026-09-03: the `HardwareProfile`
    decisions from the same diagnostic session, `Implemented`.
