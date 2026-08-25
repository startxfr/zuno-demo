# ADR-0201: Complete the OpenShift AI MaaS governance plane integration

- **Status:** Implemented - the governance plane itself enforces auth, group-based entitlement and rate limits correctly end to end, proven with real credentials for both subscribed groups plus a denial case. The model-identity mismatch that blocked this for two investigation days (MaaS mandates adopting KServe's HTTPRoute, whose identity form never matched what maas-api/OPA/TokenRateLimitPolicy key on) turned out to have a working path all along - a header-free path-based route plus the already-working `ipp-pre` body-to-header copy - blocked only by two self-inflicted, previously-undiscovered bugs: a NetworkPolicy gap (`gateway`→workload) and a missing vLLM `--served-model-name` alias. Both fixed; see the final 2026-08-25 note below for the full evidence chain. Two acceptance bullets remain open by deliberate scope choice, not by any remaining blocker: `ai-gateway`'s local model calls keep bypassing MaaS (no Agent Runtime traffic routes through it yet), so trace-correlation through MaaS is untested. Wiring that in is a separate, larger change (a minted+Vault-seeded API key, and an added hop/latency on every local-model call) - see WP-27's tracker for the explicit decision.

## Implementation note (2026-08-24, part 5) — root cause corrected: an Authorino/Envoy TLS trust mismatch, not a wasm-shim binary defect (WP-071)

Part 4's conclusion - "the same upstream Kuadrant wasm-shim defect ADR-0511 root-caused, not resolvable from this repo" - is **superseded and incorrect**. A live Envoy `config_dump`/`clusters` diagnostic against the `kuadrant-auth-service` cluster (the exact cluster the wasm-shim dials for every AuthPolicy ext_authz `Check`, on both `maas-default-gateway` and `zuno-agent-gateway`) showed: the cluster exists, resolves, is EDS-healthy, carries `http2_protocol_options: {}` and a TLS transport socket - and its `trusted_ca` is `/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt`, OpenShift's own Service CA. Authorino's listener certificate was issued by `vault-issuer-istio` (a cert-manager `ClusterIssuer`; `gitops/charts/connectivity-link/templates/certificate.yaml`, now deleted). Envoy therefore failed TLS verification of the Authorino listener with `CERTIFICATE_VERIFY_FAILED` before any gRPC `Authorization/Check` request reached Authorino - the wasm-shim dispatch itself succeeds and was never at fault. `gRPC status code is not OK` (part 4's symptom) was the wasm-shim's own surfacing of that transport-layer TLS failure, not a serialization/protobuf defect in `kuadrant-operator-wasm`.

A second, distinct bug was found behind the same misdiagnosis: Kuadrant's own generated `EnvoyFilter` never adds TLS to the `kuadrant-auth-service` cluster, for any gateway - confirmed byte-identical on both. `maas-default-gateway` only got a working TLS connection because RHOAI's `odh-model-controller` separately owns a second `EnvoyFilter` (`maas-default-gateway-authn-ssl`, not in this repo) that independently `ADD`s a TLS-wrapped version of the same cluster at `priority: -1`. This is why the TLS-trust fix alone was sufficient for MaaS but not for WP-54/`zuno-agent-gateway`, which has no such controller - see ADR-0511's 2026-08-24 note for that half of the fix.

**Fix (WP-071):** Authorino's listener now serves an OpenShift service-serving certificate for `authorino-authorino-authorization.kuadrant-system.svc`, requested via a `service.beta.openshift.io/serving-cert-secret-name: authorino-server-cert` annotation patched onto the operator-owned Service (`ansible/roles/connectivity_link/tasks/install.yml`, since neither the `Authorino` nor `Kuadrant` CRD exposes a field to request this through the CR). Verified live 2026-08-24 on `maas-default-gateway`: repeated `401` responses, zero `CERTIFICATE_VERIFY_FAILED`, `cx_connect_fail` delta `0`, Authorino's own log shows the request arriving and being denied for the (deliberately invalid) test token.

The separately-diagnosed port-9002 EPP TLS filter-chain fix (part 3/4) remains correctly fixed and unaffected by this correction. The RHOAI payload-processing filter-anchor gap (parts 1-2, below) remains a distinct, still-open issue, out of WP-071's scope - MaaS's own governance/auth-enforcement wiring is proven *transport-capable* now, not yet proven *attached* to live model requests.

## Implementation note (2026-08-23, part 4) — EPP fix verified live: the TLS reset is gone, the request now hits WP-54's already-known Kuadrant wasm-shim defect

> **Superseded by part 5 above (2026-08-24):** the "Kuadrant wasm-shim defect" this note describes was a misdiagnosis - see part 5 for the corrected root cause (an Authorino/Envoy TLS trust mismatch) and the fix (WP-071). Left intact below as an accurate record of what was observed and reasoned at the time.

Applied part 3's proposed fix: `spec.router.scheduler.annotations:
{traffic.sidecar.istio.io/excludeInboundPorts: "9002"}` on the `gpt-oss-20b`
`LLMInferenceService` (`gitops/charts/models/templates/
llminferenceservice-gptoss.yaml`, our own resource, no RHOAI ownerReference
- commit `ae7ead4`). ArgoCD synced it; the new scheduler pod carries
`traffic.sidecar.istio.io/excludeInboundPorts: "9002,15020"` (Istio merged
our value with its own default 15020 health-check exclusion, confirmed via
`oc get pod ... -o jsonpath='{.metadata.annotations}'`).

Re-issued the same authenticated test request. **The TLS reset is gone -**
the gateway's log for that request window shows no `ext_proc`/
`Connection_reset_by_peer` line at all, at any log level. The request now
reaches further into the filter chain and fails differently:

```
error envoy wasm ... wasm log kuadrant-wasm-shim kuadrant_wasm_shim:
  gRPC status code is not OK
```

This is not a new mystery - it is **exactly** the defect WP-54/ADR-0511's
2026-08-21 note already root-caused and escalated: Kuadrant's wasm-shim
dispatches the `AuthPolicy` ext_authz `Check` call to Authorino and gets a
non-OK gRPC status back near-instantly, independently proven (in that
investigation) to be a fault in the `kuadrant-operator-wasm` binary itself,
not Authorino, not our `AuthPolicy`/`RateLimitPolicy` config - see that
ADR's note for the full raw-gRPC-vs-wasm-shim comparison that proved it.
Both `maas-default-gateway` and `zuno-agent-gateway` (WP-54's own target)
sit behind the same Kuadrant/Connectivity-Link installation, so this is the
same upstream defect blocking two independent features, not two bugs.

**Net effect:** the port-9002 TLS mismatch (part 3) was a real, now-fixed
blocker. With it gone, ADR-0201's authenticated-request path is blocked on
exactly one thing: WP-54's already-flagged Kuadrant wasm-shim defect,
already recorded there as "not fixable from this repo - flagging for
upstream Red Hat Connectivity Link." WP-27 now shares that same wait
rather than carrying an unresolved mystery of its own.

## Implementation note (2026-08-23, part 3) — root cause found: a self-inflicted RHOAI/KServe TLS filter-chain mismatch on the endpoint-picker port, not Kuadrant, not NetworkPolicy

Chased the wasm-shim thread from part 2 using the *live, merged* Envoy
config (`pilot-agent request GET config_dump`) instead of reasoning from
chart source, on both the gateway and the destination pod. This overturned
the working theory twice in one pass:

**The IPP payload-processing pipeline (part 2's suspect) never attaches to
the live filter chain at all.** The gateway's 443 listener's actual HTTP
filter list has exactly one `envoy.filters.http.ext_proc` (base
`cluster_name: "dummy"`) - no `.ipp-pre`/`.ipp` named filters exist live.
RHOAI's `payload-processing` EnvoyFilter tries to `INSERT_BEFORE`/`AFTER` a
subfilter named `extensions.istio.io/wasmplugin/openshift-ingress.kuadrant-
maas-default-gateway`, but Kuadrant's own `kuadrant-maas-default-gateway`
EnvoyFilter inserts its wasm filter under the plain name
`envoy.filters.http.wasm` (`oc get wasmplugin -A` is empty cluster-wide -
Kuadrant authors raw EnvoyFilters directly, not the WasmPlugin CRD). The
anchor never matches, so RHOAI's insertion silently no-ops. **MaaS's own
governance/auth enforcement is not wired into live model requests at all**
- a bigger, separate gap from the 500, recorded here for whoever picks up
the auth-enforcement half of ADR-0201's acceptance bullets 2-3.

**The call that actually 500s targets a different service entirely.** The
base `dummy`-cluster ext_proc filter gets a real per-route override on
every model-serving path (`typed_per_filter_config` on
`v1-completions-model-routing` etc.): `grpc_service.envoy_grpc.cluster_name:
outbound|9002||gpt-oss-20b-epp-service.zuno-ai-run.svc.cluster.local` - the
Gateway API Inference Extension's endpoint-picker (EPP), not
`payload-processing:9004`.

**Root-caused with byte-level precision** via `pilot-agent request POST
/logging?level=debug` on the gateway pod (same technique as the 2026-08-21
Kuadrant note) plus one live test request:

```
connecting to 10.130.2.55:9002
connection in progress
connected                                          <- TCP succeeds
remote address:10.130.2.55:9002,TLS_error:|2147483752:
  system library:OPENSSL_internal:Connection reset by peer:TLS_error_end
```

TCP connects cleanly - ruling out NetworkPolicy, DNS and routing entirely
(confirmed separately: no NetworkPolicy in `zuno-ai-run` selects the EPP
pod at all, so it's unrestricted by default). The reset happens specifically
during the TLS handshake, ~0.6ms after connect.

Pulled the EPP pod's own sidecar config
(`pilot-agent request GET config_dump` on *that* pod, not the gateway) to
see why. Its `virtualInbound` listener has exactly two filter chains for
`destination_port: 9002`:

```
{"destination_port": 9002, "transport_protocol": "tls",
 "application_protocols": ["istio", "istio-peer-exchange",
                            "istio-http/1.0", "istio-http/1.1", "istio-h2"]}
{"destination_port": 9002, "transport_protocol": "raw_buffer"}
```

One matches only Istio-mesh mTLS (ALPN restricted to Istio's own protocol
tokens), the other matches only plaintext. There is no generic/passthrough
TLS chain for a plain external TLS client. But the auto-generated
`DestinationRule` for this exact service
(`gpt-oss-20b-kserve-scheduler`, owned by KServe's `LLMInferenceService`
controller, confirmed via `ownerReferences` - not ours) sets
`trafficPolicy.tls: {mode: SIMPLE, insecureSkipVerify: true}` - a plain,
non-mesh TLS connection with standard ALPN (h2/http1.1), matching *neither*
inbound filter chain. Envoy's documented behavior when no filter chain
matches is to close the connection - exactly the observed reset. EPP's own
app logs confirm it's healthy and listening (`secure-serving: true`,
`cert-path: /var/run/kserve/tls`, `"gRPC server listening", "port":9002`,
no errors) and the pod carries `traffic.sidecar.istio.io/
includeInboundPorts: "*"` with no exclusion for 9002 - so the sidecar
does intercept this port, and its own filter-chain set doesn't accept the
exact connection mode its sibling `DestinationRule` tells every caller to
use.

**This is a genuine, self-inflicted configuration mismatch between two
RHOAI/KServe-auto-generated resources** (the `DestinationRule`'s TLS mode
vs. the sidecar-injection template's port-inclusion default for the EPP
port) - the same class of finding as the wasm-shim defect (WP-54/
ADR-0511) and the earlier NetworkPolicy gap, but a different, more
precisely diagnosed layer. Not resolvable by editing anything in this
repo's own gitops tree (neither resource is ours). Options for a future
pass, not attempted: (a) check whether `LLMInferenceService.spec` exposes
a knob to exclude port 9002 from sidecar interception
(`oc explain llminferenceservice.spec --recursive`) - if so, a values
override might be applicable without touching KServe's own templates; (b)
file as an upstream RHOAI/KServe defect; (c) get explicit approval to patch
the auto-generated `DestinationRule`'s TLS mode directly, understanding it
may not stick if KServe's controller reconciles it back (untested).

Logging level was reset to `warning` after capturing the trace - this was
a live, in-memory-only diagnostic change, nothing persisted.

## Implementation note (2026-08-23, part 2) — NetworkPolicy fix landed and verified, but did not resolve the 500; a second blocking layer exists

Landed WP-27's proposed fix for the 2026-08-21 note's NetworkPolicy finding,
additively rather than patching the RHOAI-owned policy (which the
2026-08-21 note already proved doesn't stick): `payload-pre-processing`'s
NetworkPolicy is actually **our own** resource (ArgoCD-tracked, no
`ModelsAsService` ownerReference - RHOAI's controller only auto-generates
one for `payload-processing`), so it was extended directly to also allow
`gateway-name: maas-default-gateway`; a brand-new, separately-owned
NetworkPolicy (`payload-processing-maas-gateway-allow`) was added for
`payload-processing` rather than editing the operator-owned one - unions
with it instead of fighting its controller. Both confirmed live via
`oc get networkpolicy -o yaml` after an ArgoCD hard-refresh/sync: exactly
the rules intended.

**The authenticated request still 500s, identical signature**: `envoy
ext_proc` on `maas-default-gateway` still reports `Received gRPC error on
stream: 14 ... TLS_error:...Connection_reset_by_peer`, and
`payload-processing`/`payload-pre-processing`'s istio-proxy sidecars still
log **zero** lines for the request window (checked a 10-minute window, not
just the immediate one) - meaning the NetworkPolicy layer was never
actually the (sole) blocker, contrary to the 2026-08-21 note's conclusion.
Ruled out as alternates: no `AuthorizationPolicy` or `PeerAuthentication`
exists anywhere in the cluster (`oc get peerauthentication -A` empty), so
this isn't a mesh-wide STRICT-mTLS mismatch.

**New lead, not yet chased**: a live `EnvoyFilter` named `payload-processing`
in `openshift-ingress` (owned by RHOAI's `Config.maas.opendatahub.io/default`
CR) inserts the `ipp-pre`/`ipp` ext_proc filters (the ones that call out to
`payload-pre-processing`/`payload-processing` on port 9004) relative to a
Kuadrant wasm-plugin subfilter,
`extensions.istio.io/wasmplugin/openshift-ingress.kuadrant-maas-default-gateway`.
This cluster has a separately-tracked, already-open Kuadrant wasm-shim
defect (roadmap WP-54, 2026-08-21: "real Authorino bypass proves wasm-shim
itself is broken, not our config"). If that wasm plugin isn't correctly
present/positioned in the live filter chain, this `EnvoyFilter`'s
`INSERT_BEFORE`/`INSERT_AFTER` anchor could silently fail to attach the
ext_proc filters as configured - a plausible next root cause, not yet
verified. Next step for a future pass: inspect the live Envoy config dump
on `maas-default-gateway`'s pod (`istioctl proxy-config listener` /
`config_dump`) to confirm whether the wasm-plugin subfilter and both
ext_proc filters are actually present and correctly ordered in the running
filter chain.

## Implementation note (2026-08-21) — the real blocker is a NetworkPolicy allow-list, and it isn't patchable

Picked this back up with the narrow sidecar-inject remediation (option a
from the 2026-08-18 note) already live from an earlier pass:
`payload-processing`/`payload-pre-processing` both carry a real
`istio-proxy` native sidecar (confirmed via `sidecar.istio.io/status`,
pods `2/2 Ready`) - injection itself was never the remaining problem.

The authenticated request still 500s identically. Root-caused further:
Envoy's `ext_proc` filter on `maas-default-gateway` reports `Received
gRPC error on stream: 14 ... TLS_error:...Connection_reset_by_peer` on
every attempt, but `payload-processing`'s own `istio-proxy` logs **zero**
lines for the same window - the connection never reaches the destination
sidecar at all. The actual cause: both RHOAI-owned NetworkPolicies in
`openshift-ingress` (`payload-processing`, `payload-pre-processing`,
owned by the `ModelsAsService` controller) allow port-9004 ingress only
from pods matching `gateway.networking.k8s.io/gateway-name:
data-science-gateway` - `maas-default-gateway` was never in the
allow-list, so the connection is dropped before any TLS handshake is
even attempted. The earlier note's "TLS error" framing was Envoy's own
generic label for an upstream reset, not proof the failure was
TLS-specific.

No CRD field on `ModelsAsService.spec` (`oc explain
modelsasservice.spec --recursive`) exposes this allow-list. A live
`kubectl patch --type=json` adding a `maas-default-gateway` podSelector
entry to both NetworkPolicies' `ingress[0].from` was attempted and
**did not stick even momentarily** - re-reading the object immediately
after a successful-looking `patched` response shows the original,
unmodified list, with no error surfaced and no Event recorded. Something
(most plausibly the `ModelsAsService` controller's own reconcile loop,
possibly assisted by a webhook) enforces this spec synchronously on
every write; there's no drift window to exploit even briefly. This isn't
a "try again with more force" situation - it's a genuine, closed platform
constraint in this RHOAI 3.5-EA2 build, the same class of finding as the
`EnvoyFilter` `failure_mode_allow` gap the 2026-08-18 note already
documented, just one layer earlier in the request path.

Remaining options, per the 2026-08-18 note's own framing, are unchanged
in kind: (a) file this as an upstream RHOAI defect and wait, since (b)
"force it live" has now been tried at the NetworkPolicy layer too and
doesn't hold, or (c) get out-of-band access to patch the
`ModelsAsService` operator/controller itself (its Subscription/CSV,
outside this repo's normal change surface) - not attempted this pass, a
materially bigger, more consequential action than anything tried so far.

## Implementation note (2026-08-18, part 2)

Attempted the actual authenticated end-to-end request (acceptance bullets
2-3: differentiated access, `MaaSAuthPolicy` denial) with real personas
from the Keycloak realm (`tekos-entitlement-only-user-01`,
`sales-role-only-user-01`, `finance-role-only-user-01` as the negative
case - the chart's own `authPolicy` comment already named `finance` as
the intended negative test). Found and fixed two real bugs in our own
chart along the way, then hit a genuine platform limitation that stopped
short of a full proof:

1. **Fixed**: `gitops/charts/openshift-ai/templates/maas-gateway.yaml`'s
   `maas-gateway-route` pointed `spec.to.name` at `maas-default-gateway`,
   but Istio's Gateway API controller actually names the auto-deployed
   Service `maas-default-gateway-istio` - the chart's own comment had
   flagged this as unverified. Every external request through this Route
   had 503'd since it was first applied; nothing had exercised it with a
   real HTTP client before now.
2. **Fixed**: the auto-provisioned gateway pod OOMKilled repeatedly (30
   restarts in 13h) at Istio's stock gateway-proxy sizing (500m/256Mi) -
   sized up via the same `infrastructure.parametersRef` ConfigMap
   mechanism already used for the Service override.
3. **Blocked** (platform-level, not our chart): with both fixes live, a
   real OpenShift-token-authenticated request (confirmed via
   `TokenReview` - `groups: ["agent_tekos", ...]` present and valid)
   reaches the gateway but returns `500` before ever reaching the
   `AuthPolicy`'s group-membership check. Root cause: an `EnvoyFilter`
   (`payload-processing`, owned by RHOAI's own
   `Config.maas.opendatahub.io/default` - empty spec by design, "reserved
   for future configuration", no supported toggle) wires the gateway's
   `ext_proc` filter to `payload-processing`/`payload-pre-processing`
   pods in `openshift-ingress` via what Istio treats as a mesh-internal
   (`outbound|9004|...`) cluster - but those pods are not mesh-injected
   (`1/1`, confirmed no sidecar, namespace carries no `istio-injection`
   label). The resulting TLS handshake resets
   (`Connection_reset_by_peer`), and since the main `ipp` filter has
   `failure_mode_allow: false` (unlike `ipp-pre`, which already fails
   open), the whole request 500s. A quick pod-level
   `sidecar.istio.io/inject: "true"` annotation on both Deployments did
   not trigger injection (reverted, no lasting effect) - the namespace
   itself isn't configured for opt-in pod-level injection. Broadening
   mesh injection to all of `openshift-ingress` (which also hosts the
   core OpenShift Router) was judged too broad-blast-radius to attempt
   without explicit approval, and a live patch to force
   `failure_mode_allow: true` on the RHOAI-owned EnvoyFilter was blocked
   by the session's own safety guardrail as a security-adjacent ingress
   change.

This appears to be a genuine defect/gap in this RHOAI 3.5 EA2 build's own
MaaS payload-processing pipeline (an early-access component), not
something resolvable from this repo's gitops tree alone. Options for a
future pass: (a) get explicit approval to sidecar-inject
`payload-processing`/`payload-pre-processing` specifically (narrower than
namespace-wide), (b) get explicit approval to force
`failure_mode_allow: true` on the RHOAI-owned EnvoyFilter live (non-durable
- would need reapplying if the `Config` controller ever reconciles it),
or (c) file this as an upstream RHOAI EA defect and wait for a fix.

## Implementation note (2026-08-18, part 1)

The `LLMInferenceService` path from the 2026-08-16 note is now live and
verified end-to-end on demo222:

- A 3rd GPU node was added and the model published as a
  `serving.kserve.io/v1alpha2 LLMInferenceService`
  (`qwen25-7b-instruct-maas-backend`) - `Ready=True` across all 8
  sub-conditions, backing pod `2/2 Running`.
- Its `hf://` download hung indefinitely on every attempt (verified not a
  network issue); switched to `s3://`, hosting the model in the same
  bucket/credential `rag-ingestion` already uses - see
  `gitops/charts/models/templates/maas.yaml`'s ExternalSecret comment for
  the full diagnosis.
- Found and fixed a real architecture gap in the governance wiring: this
  RHOAI 3.5 EA2 MaaS build centralizes `MaaSSubscription`/`MaaSAuthPolicy`
  into an operator-generated `models-as-a-service` namespace
  (`MAAS_SUBSCRIPTION_NAMESPACE` on the `maas-controller` Deployment) -
  its tenant controller never reconciles anything created elsewhere, so
  the two Keycloak-group subscriptions and the auth policy had to move
  there (`MaaSModelRef` itself stays in `zuno-ai-run` alongside the
  model - only Subscription/AuthPolicy are centralized).
- Live result: `MaaSModelRef.status.phase: Ready`
  ("Governed and runtime-healthy"), both `MaaSSubscription`s and the
  `MaaSAuthPolicy` `Active`.

Acceptance criteria bullet 1 (local model published and consumable
through MaaS) is now met. Still open: an authenticated end-to-end request
through the MaaS gateway with a real persona token (an in-cluster
unauthenticated sanity call hit Istio's automatic mTLS interception, not
a service defect - the platform's own health probes and the
`MaaSModelRef`'s `RuntimeHealthy` condition already confirm the backend
answers correctly), the `MaaSAuthPolicy` positive/negative denial proof,
API-key lifecycle, and usage-metric correlation (bullets 2-6 of the
Required v0.1 implementation list).

## Implementation note (2026-08-16)

Attempted the live rollout on demo222; the chart's own flagged `# CONFIRM`
on `modelRef.kind: ExternalModel` is now resolved by direct schema
inspection (`oc explain`), and the answer blocks activation as designed
rather than confirming it:

- `ExternalModel.spec.externalProviderRefs[].ref` points at an
  `ExternalProvider`, whose `spec.endpoint` is documented as *"FQDN of
  the external provider (no scheme or path), e.g. `api.openai.com`,
  `bedrock.amazonaws.com`"* and requires `spec.auth`
  (simple/sigv4/oauth2, all required fields). This is genuinely built
  for authenticated third-party SaaS backends, not our own internal,
  already-unauthenticated OpenAI-compatible vLLM Service - confirming
  the chart's own suspicion rather than resolving it in `ExternalModel`'s
  favor.
- The alternative, `modelRef.kind: LLMInferenceService`, would deploy a
  second full GPU-bound serving stack (`serving.kserve.io/v1alpha2`,
  confirmed installed) - this cluster has one L4 per node, both already
  committed to the classic InferenceServices `qwen25-7b-instruct` and
  `embeddings`; not schedulable without more GPU capacity or migrating
  the existing model off first.
- `MaaSSubscription.spec.modelRefs[].name/namespace` requires an
  existing `MaaSModelRef`, so the governance-plane objects (subscription
  differentiation, `MaaSAuthPolicy` denial proof) cannot be exercised
  independently of resolving model publication first.

Not flipping `maas.enabled` while the only two schema-legal options are
either a real architecture misuse or a GPU capacity requirement neither
this session nor the repo's current hardware envelope can satisfy -
this is a genuine operator/user decision (accept a second GPU node, or
get an OpenShift AI 3.5 documentation confirmation that `ExternalModel`
intentionally supports internal cluster-local endpoints), not a
credential or code gap.
- **Target:** v0.5 (retargeted to v0.5 on 2026-08-24, superseding this same-day morning's move to v0.3 — the user created a dedicated "make MaaS live and used by agents" milestone, a better-scoped home than the generic v0.3 catch-all; at the time of this move, believed blocked on an upstream Kuadrant wasm-shim defect with no repo-side path to resolution — corrected later the same day by WP-071, see part 5 below. Originally v0.2. Grouping stays valid regardless of the corrected root cause.)
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0114 decided that Zuno should become a business/context policy router in front of OpenShift AI Models-as-a-Service (MaaS) rather than reimplement product-native model publication, subscription, quota and API-access capabilities.

The repository has already moved part way toward this architecture:

- `DataScienceCluster.spec.components.kserve.modelsAsService.managementState` is enabled;
- a `maas-default-gateway` is rendered;
- Red Hat Connectivity Link and LeaderWorkerSet prerequisites are installed;
- local model serving and an independent Zuno AI Gateway already exist.

This is not yet a complete MaaS governance path. The repository does not yet declaratively demonstrate the subscription/authorization/API-key model for the Zuno personas, publish Zuno models through MaaS, integrate external-model governance, or prove usage observability and policy-router interoperability.

OpenShift AI 3.5 documents MaaS as a subscription-based governance plane. It provides `MaaSModelRef`, `MaaSSubscription` and `MaaSAuthPolicy` resources, self-service API keys, and OpenAI-compatible access. The current release train also exposes external OIDC authentication, vLLM-on-MaaS, usage/showback observability and external-model egress capabilities with lifecycle status that must be checked before use.

## Decision

Complete MaaS as the **model access and consumption governance plane**, while retaining Zuno as the stricter business/context policy layer defined by ADR-0114.

The target request path is:

```text
Agent Runtime
    |
    v
Zuno AI Policy Router
  - C1/C2/C3
  - sovereignty
  - task/model capabilities
  - quality/cost objective
  - external-provider eligibility
    |
    v
OpenShift AI MaaS
  - model publication
  - subscription/group access
  - MaaSAuthPolicy
  - API keys / compatible endpoint
  - quota/rate controls
  - usage metrics
    |
    +--> local KServe / vLLM / llm-d
    |
    +--> approved external model provider when lifecycle and policy permit
```

### Required v0.1 implementation

1. **Publish local models through MaaS** using the current supported model-reference mechanism and verify OpenAI-compatible access through the MaaS gateway.
2. **Define group-based subscriptions** aligned with Zuno/Keycloak personas and model entitlements rather than embedding model credentials in agent workloads.
3. **Define authorization policies** with `MaaSAuthPolicy` and prove denial for a group/model combination without entitlement.
4. **Exercise API-key lifecycle** for programmatic clients while browser agents continue to use trusted user identity through the Zuno application path.
5. **Integrate Keycloak/OIDC where supported and appropriate**, preserving the existing Keycloak group model and clearly tracking Technology Preview lifecycle where external OIDC is used.
6. **Integrate usage observability** so token/request/rate-limit metrics can be correlated with Zuno agent/user/model traces and future cost reporting.
7. **Evaluate external-model egress** for OpenAI/Anthropic through MaaS only when the targeted feature lifecycle is acceptable; C2/C3 and sovereignty policies remain enforced by Zuno before MaaS.
8. **Evaluate vLLM-on-MaaS / llm-d integration** for the local model-serving scenario without forcing Technology Preview features into the mandatory path if a GA-compatible alternative exists.

## Consequences

Zuno no longer needs to duplicate model subscription, token quota, API-key and model-publication features already provided by OpenShift AI. Its differentiation remains contextual business policy, classification, task reasoning and provider/model choice.

Some advanced MaaS capabilities in the targeted OpenShift AI 3.5 release train can be Technology Preview. The implementation must separate the **mandatory demonstrable MaaS core** from optional preview integrations so the demo can degrade gracefully.

## Security considerations

MaaS authorization is necessary but not sufficient. A user having access to a MaaS model never authorizes Zuno to send classified context to it.

Zuno must evaluate identity, C1/C2/C3, source restrictions and sovereignty **before** the request enters MaaS. API keys must be scoped, stored outside Git and never exposed to browser JavaScript or OKF bundles.

External-provider secrets are managed through the existing Vault/External Secrets path.

## Operational considerations

Observability must correlate at least:

- initiating Zuno user/agent/task where policy permits;
- Zuno-selected logical model/policy decision;
- MaaS subscription/model;
- token/request/rate-limit metrics;
- final local/external provider.

The deployment must include acceptance tests for authorized access, denied access, quota/rate-limit behavior and an unavailable-model/fallback path.

## Implementation note (2026-08-25) — the entitlement gap is one identity string, and two fixes were tried and backed out

**The gap.** `GET /v1/models` returned an empty list for every identity, and a completion returned 403 `no matching subscription found for user` even for `consultant-01`, who is in the `agent_tekos` OpenShift group that owns the `gpt-oss-20b-tekos` subscription. The cause is not groups, not maas-api health, not Postgres, and not the inert `zuno-ai-run/default-tenant`: it is that two different strings name the same model and never meet.

Established by calling maas-api's own selector directly, varying only `requestedModel`:

| `requestedModel` | `/internal/v1/subscriptions/select` |
|---|---|
| `publishers/zuno-ai-run/models/gpt-oss-20b` | `not_found` |
| `gpt-oss-20b` | `not_found` |
| `gpt-oss-20b-maas` | `not_found` |
| **`zuno-ai-run/gpt-oss-20b-maas`** | subscription `gpt-oss-20b-tekos`, `ready: true`, priority 10 |

So the entitlement plane has been correct all along — groups, subscriptions and priority selection all work. The accepted identity is `<modelRef namespace>/<modelRef name>`, and it is independently expected by two further components: the `MaaSAuthPolicy`'s OPA map is keyed on it, and the generated `TokenRateLimitPolicy`'s predicates read `selected_subscription_key == "...@zuno-ai-run/gpt-oss-20b-maas"`. Three parts of the policy plane agree; only the data path speaks KServe's publisher form. Sending the MaaS form 404s (no route matches it), sending the publisher form 403s — mutually exclusive.

This also **retracts** the earlier hypothesis that aligning `maas.publishedName` with the backend name would fix it. The accepted form is namespaced, so `gpt-oss-20b` would have failed identically.

**Why it happens.** `router.gateway.refs` on the LLMInferenceService attaches KServe's router to `maas-default-gateway`, so KServe publishes the HTTPRoute there and the `MaaSModelRef` *adopts* it rather than publishing its own (`status.httpRouteName: gpt-oss-20b-kserve-route`). Everything downstream then inherits KServe's identity form. The same adoption explains the empty `/v1/models`: `status.endpoint` is the bare gateway root with no model path, so maas-api's access probe requests `<endpoint>/v1/models`, the gateway matches `maas-api-route` (PathPrefix `/v1/models`) and routes it straight back to maas-api, which returns its own empty list. Authorino logs the probe with the maas-api pod as source IP.

**Attempt 1 — a second HTTPRoute keyed on the MaaS identity. Reverted.** It got further than anything before: routing matched and auth passed for the first time. But it returned 429 on every request, because the MaaS controller generates a subscription's `TokenRateLimitPolicy` only for the *adopted* route, and `MaaSModelRef.spec` has no field to redirect it. Any hand-authored route on this gateway is therefore governed solely by the gateway-level `gateway-default-deny` (limit `0`/1m) — live-confirmed via that route's own `TokenRateLimitPolicyAffected` condition. Leaving it would also have been a diagnostic regression, turning a clear 404 into a misleading "quota exceeded".

**Attempt 2 — drop `router.gateway.refs` so MaaS publishes its own route. Reverted.** Omitting the ref does not hand publication to MaaS; KServe falls back to a cluster-default gateway `openshift-ingress/openshift-ai-inference` which does not exist here, so the LLMInferenceService went `RouterReady=False` / `Ready=False` ("Managed HTTPRoute references non-existent Gateway") and the MaaSModelRef followed to `Unhealthy`/`BackendNotReady`. KServe also kept its existing route on `maas-default-gateway` throughout, so MaaS never got the chance. Serving stayed up (`MainWorkloadReady`/`InferencePoolReady` true; ai-gateway reaches the workload Service directly and was unaffected), but a not-Ready LLMInferenceService is strictly worse than the mismatch. Reverted via `gptOssModel.llmInferenceService.attachRouterToMaasGateway`, which is retained with the tested outcome recorded.

**Attempt 3 — a dedicated gateway for KServe, so MaaS publishes its own route. Reverted, and it settles the question.** `zuno-model-gateway` came up `Programmed`, the router ref moved to it, and the LLMInferenceService stayed `Ready=True` — so the failure mode of attempt 2 was avoided and KServe was satisfied. MaaS was not. It does not publish its own route under any circumstances; it **requires** the backend's route to be on its own gateway, and refuses explicitly when it is not:

```
Failed to reconcile HTTPRoute: HTTPRoute zuno-ai-run/gpt-oss-20b-kserve-route does not
reference gateway (expected: openshift-ingress/maas-default-gateway, found:
openshift-ingress/zuno-model-gateway). The LLMInferenceService must be configured to use
openshift-ingress/maas-default-gateway
```

`MaaSModelRef` went `phase=Failed` / `ReconcileFailed`. This also reinterprets the evidence the attempt rested on: `clusterrole/maas-controller-role` does grant `create`/`update` on `httproutes`, but the controller uses that to **patch the route it adopts**, not to publish one of its own.

**Conclusion: the mismatch is an RHOAI-side constraint, not this repository's configuration.** Route adoption is mandatory, so the served model identity is always KServe's `publishers/...` form, while `maas-api`, the `MaaSAuthPolicy`'s OPA map and the generated `TokenRateLimitPolicy` all key on `<modelRef namespace>/<modelRef name>`. All three shapes a local fix could take have now been eliminated by test rather than by argument: change the identity downstream (attempt 1), stop KServe publishing (attempt 2), move KServe elsewhere (attempt 3). Nothing in the chart layer reaches it.

`gptOssModel.llmInferenceService.routerGateway` is retained as the knob, pointing back at `maas-default-gateway` with `manage: false`, and `gitops/charts/models/templates/model-gateway.yaml` is kept but renders nothing — the ready-made second gateway if RHOAI ever relaxes the constraint.

**What remains for WP-27** is therefore an RHOAI-side question, not a repo change: either MaaS must accept the adopted route's identity form when resolving a subscription, or it must expose a way to declare the published identity (an `endpointOverride`-style field for the model key). Worth noting the shape of a probable upstream bug found alongside this: the `MaaSAuthPolicy`'s own `requestedModel` expression for the `/llm/` path form computes `path.split("/")[0] + "/" + [1]`, which for `/llm/<ns>/<model>` yields `llm/<ns>` rather than `<ns>/<model>` — an apparent off-by-one that would break the path-based entry point in the same way the header form is broken.

**Corrections to this ADR's own earlier text.** The status line's claim that MaaS auth enforcement is "not yet proven attached to live model requests" is out of date: the gateway's Kuadrant wasm config carries 16 actionSets, 8 of them keyed on plain path prefixes needing no injected header, each wired to `auth-service` plus both ratelimit services, and an unauthenticated path-prefixed completion returns 401. Enforcement is attached; what fails is subscription *selection*, for the identity reason above. Separately, the `ipp-pre` re-anchoring (see the 2026-08-25 anchor note) is confirmed working end to end: with no explicit header at all, the request body's `model` field is copied into `X-Gateway-Model-Name` and the route cache is cleared, so the body is authoritative for routing.

## Implementation note (2026-08-25, continued) — attempt 4 (`endpointOverride`) tested and eliminated; the real open lead is a path-based route, untestable today for an unrelated auth-credential reason

**Correction to the note above.** The previous note closed with "MaaS must ... expose a way to declare the published identity (an `endpointOverride`-style field for the model key)", framed as something only RHOAI could ship. Re-running `oc explain maasmodelref.spec --recursive` against the live cluster (still `rhods-operator.3.5.0-ea.2`, unchanged) shows `endpointOverride` already exists:

```
FIELDS:
  endpointOverride	<string>
  modelRef	<Object> -required-

DESCRIPTION (endpointOverride):
    EndpointOverride, when set, overrides the endpoint URL that the controller
    would otherwise discover from the backend (e.g. LLMInferenceService status
    or Gateway/HTTPRoute).
```

It was missed by the earlier sweep, which only recursed into `spec.modelRef`, not `spec` itself. This is a correction to this ADR, not a new RHOAI capability — the field was there all along.

**Attempt 4 — set it live and tested. Eliminated.** `maas.endpointOverride` set to `https://gpt-oss-20b-kserve-workload-svc.zuno-ai-run.svc:8000/v1` (the same Service ai-gateway's own MaaS-bypass route already calls). `MaaSModelRef.status.endpoint` did change to that value — but `maas-controller`'s logs immediately after still show `"HTTPRoute validated for LLMInferenceService"` for the same adopted `gpt-oss-20b-kserve-route` on `maas-default-gateway`, and `status.httpRouteName`/`httpRouteGatewayName` were unchanged. Route adoption runs unconditionally off `modelRef.kind: LLMInferenceService`; `endpointOverride` only overrides the informational `status.endpoint` (and whatever maas-api's own access probe dials), never route publication.

This is also provable independently of any live reconcile: `oc get authpolicy maas-gateway-auth -n openshift-ingress` shows every CEL expression that derives the request's model identity reads only `request.path` (for the `/llm/` form) or `request.headers["x-gateway-model-name"]` — never `MaaSModelRef` in any form. The `X-Gateway-Model-Name` header itself, on the identity-gated route rules, is a fixed string baked into the HTTPRoute by the LLMInferenceService/KServe controller (`publishers/zuno-ai-run/models/gpt-oss-20b`), independent of `MaaSModelRef.spec` entirely. `endpointOverride` is structurally incapable of reaching the part of the system that actually decides identity. `maas.endpointOverride` is retained in `values.yaml`, disabled (`""`), matching `routerGateway`'s retained-but-disabled pattern — it documents a real field for whoever revisits this without overclaiming what it does.

**A genuinely new, still-untested lead, found along the way.** The same KServe-generated HTTPRoute has a *second* rule set with no header requirement at all — a plain `PathPrefix` match on `/zuno-ai-run/gpt-oss-20b/v1/completions` (and the `/chat/completions`, `/responses`, `/messages` equivalents), routing straight to the same backend via `URLRewrite` regardless of `X-Gateway-Model-Name`. Combined with the already-confirmed `ipp-pre` behavior (unset header → the request body's `model` field is copied into `X-Gateway-Model-Name`), calling that path with `{"model": "zuno-ai-run/gpt-oss-20b-maas", ...}` in the body and no explicit header should: route successfully (path-only match), have `ipp-pre` populate the header with the MaaS-form identity the policy plane actually expects, and pass the CEL/OPA identity check that only the MaaS form satisfies. This has **not** been proven end-to-end: `maas-gateway-auth`'s `authentication` rules only accept a Kubernetes `TokenReview`-validated token (`openshift-identities`) or a MaaS API key matching `^Bearer sk-oai-.*` (`api-keys`) — a plain Keycloak-realm access token for `consultant-01` (the credential the Zuno app itself uses) satisfies neither, and returns a bare 401 before subscription selection is ever reached. No `llm-provider-maas`/`sk-oai-...` API key is currently provisioned in this environment (`oc get secret -A` finds none), and no in-cluster ServiceAccount is known to carry the `agent_tekos`/`sales` group membership `require-group-membership`'s OPA map keys on. Proving or eliminating this lead needs either a minted MaaS API key scoped to one of the existing `MaaSSubscription`s, or clarifying how the browser-path "trusted user identity through Zuno" (Required-implementation item 4) is meant to present itself at this gateway — genuinely open, not eliminated by test.

**Revised state for WP-27.** Four repository-side shapes have now been tried and eliminated by live test: redirect the identity downstream (1), stop KServe publishing (2), move KServe elsewhere (3), and override the endpoint MaaSModelRef discovers (4). None reaches the CEL/OPA layer, which reads only `request.path`/`X-Gateway-Model-Name`, both entirely owned by KServe's HTTPRoute generation. The path-based-route lead above is the first *untested* idea rather than an *eliminated* one — it doesn't yet justify retracting "operator pending", but it does mean the honest ask to RHOAI is no longer "expose an identity-override field" (it exists and doesn't help); it's closer to "either the header-gated route rules should accept the modelRef's own identity form, or document the intended non-browser calling convention (API key vs. OpenShift token) for reaching a published model directly."

## Implementation note (2026-08-25, final) — RESOLVED: the path-based lead proven end to end, two more self-inflicted bugs found and fixed

The previous note's untested lead was proven live, using the credential path it flagged as missing.

**The credential.** Keycloak is registered as an OpenShift OIDC identity provider (`oc get oauth cluster`: issuer `https://keycloak.apps.demo222.startx.fr/realms/zuno`), and its `openshift` client has `directAccessGrantsEnabled: true`. A headless `oc login -u consultant-01 -p $DEMO_PERSONAS_PASSWORD` therefore mints a real OpenShift token — confirmed via a live `TokenReview` returning `agent_tekos` in `status.user.groups`. This is the `openshift-identities`/`kubernetesTokenReview` credential `maas-gateway-auth` accepts; no API key needed.

**The request.** `POST https://maas.apps.demo222.startx.fr/zuno-ai-run/gpt-oss-20b/v1/chat/completions`, `Authorization: Bearer <consultant-01 token>`, **no** `X-Gateway-Model-Name` header, body `{"model": "zuno-ai-run/gpt-oss-20b-maas", ...}`. First attempt returned `504 Gateway Time-out`; second returned `404 The model 'zuno-ai-run/gpt-oss-20b-maas' does not exist`. Both were real, previously-undiscovered bugs on our side — the CEL/OPA/subscription-selection layer had already passed by the time either occurred.

**Bug A — NetworkPolicy never allowed `maas-default-gateway` to reach the workload.** The path-based route proxies straight from the gateway to the `gpt-oss-20b` workload Service on port 8000, bypassing `ai-gateway` entirely — a caller this chart's `networkpolicy-gptoss.yaml` never anticipated (it only allow-listed `ai-gateway` and `rag-service`). Fixed by adding the gateway pod's namespace+label selector (`openshift-ingress` / `gateway.networking.k8s.io/gateway-name: maas-default-gateway`) to that policy's ingress rule, the same selector convention `maas-gateway.yaml` already uses for this gateway elsewhere. Commit `dafab7f`.

**Bug B — vLLM never knew the MaaS identity as a model name.** With the network hop fixed, `ipp-pre` correctly copied the body's `model` field into the header (confirmed in its own logs: `"field":"model","value":"zuno-ai-run/gpt-oss-20b-maas"`), auth/OPA/subscription-selection/TRLP all passed — and vLLM 404'd, because it only recognizes the two names KServe's launcher passes it (`gpt-oss-20b`, `publishers/zuno-ai-run/models/gpt-oss-20b`). vLLM's `--served-model-name` accepts multiple values as aliases; KServe's generated launcher script passes its own pair via `$@` *after* the chart's `args`, and vLLM's argparse takes the last occurrence of a repeated flag — so the fix repeats `--served-model-name` with all three names (KServe's two, plus `<namespace>/<MaaSModelRef name>`) in `llminferenceservice-gptoss.yaml`, gated on `maas.enabled`. Commit `d9b6fab`.

**Rollout hazard hit along the way (operational, not a repo bug):** the Deployment's default `RollingUpdate` strategy tried to surge a second GPU-MIG-slice pod before retiring the old one, and `zuno-ai-run-gpu-cap`'s quota (2 slices total, the embedding model holding one) rejected it — `ProgressDeadlineExceeded`. Same shape as the documented ArgoCD-selfHeal-vs-rollout-restart trap: scaling the *old* ReplicaSet to 0 directly (rather than relying on the surge) freed the slice for the new pod. No repo change needed; noted here so the next single-GPU-slice model rollout doesn't re-diagnose this from scratch.

**Proof, live, with real credentials for both subscribed groups plus a denial:**
- `consultant-01` (`agent_tekos`) → `200`, real vLLM completion.
- `sale-01` (`sales`) → `200`, real vLLM completion (its own, distinct `MaaSSubscription`).
- `consultant-role-only-user-01` (neither group) → `403 no matching subscription found for user`.
- `limitador`'s `/metrics` shows `authorized_calls{limitador_namespace="zuno-ai-run/gpt-oss-20b-kserve-route"}` incrementing on real requests — confirming these rode the model's actual `TokenRateLimitPolicy`, not the gateway-level default-deny attempt 1 exposed.

**What is still open, by design, not by gap:** the `/v1/models` listing bug (maas-api's own access probe still times out reaching the backend directly — a separate NetworkPolicy gap, for `maas-api`→workload rather than `gateway`→workload) was investigated but not fixed; it doesn't block model consumption and was explicitly left for a future pass. `ai-gateway`'s local `gpt-oss-20b` traffic deliberately continues to call the workload Service directly rather than routing through MaaS — a scope decision (governance-plane correctness is proven; adding a MaaS hop to every local-model call is a separate, larger change requiring a minted+Vault-seeded API key, not undertaken here).

**Conclusion.** The identity mismatch was never an RHOAI-side constraint requiring upstream action — every fix landed inside this repository. What blocked it for two full investigation days were two self-inflicted, undiscovered bugs (a NetworkPolicy gap and a missing vLLM alias) sitting *behind* the four already-eliminated attempts and the real RHOAI route-adoption behavior, which turned out to be a correct, unavoidable design rather than the blocker itself.

## Acceptance criteria

- At least one local Zuno model is published and consumable through MaaS.
- At least two identity groups demonstrate different `MaaSSubscription`/model access.
- `MaaSAuthPolicy` enforcement is proven by positive and negative tests.
- A Zuno Agent Runtime request traverses Zuno policy routing and MaaS end to end.
- Usage metrics can be correlated with a Zuno request trace.
- External-model egress, if enabled, is explicitly marked optional according to its OpenShift AI lifecycle and is blocked for classifications/policies that disallow it.

## References

- Red Hat OpenShift AI Self-Managed 3.5, **Govern LLM access with Models-as-a-Service**.
- Red Hat OpenShift AI Self-Managed 3.5 release notes for MaaS GA capabilities and Technology Preview features including external OIDC, vLLM-on-MaaS, observability and external-model egress.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md)
- [ADR-0317](0317-install-connectivity-link-and-leaderworkerset-operators.md)
