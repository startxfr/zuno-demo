# WP-124: Restore ai-gateway's egress to external SaaS providers

- **State:** Not started
- **ADRs:** ADR-0415 (SDXL via OVHcloud AI Endpoints), ADR-0416 (gpt-oss-120b
  via OVHcloud), ADR-0417 (Codestral via Mistral API) - the three provider
  decisions this defect silently voids; ADR-0537 (Decision 3/4, the
  `maas-controller` operator-immaturity class - its `MaaSModelRef`s are
  already `ReconcileFailed`, yet it still emits the networking resources that
  break egress); ADR-0020/ADR-0021 (the local-vs-external provider routing
  this makes untestable above C1).
- **Depends on:** none.
- **Related:** WP-112 (found there while verifying a Comage fix, out of that
  WP's scope and split out here - it cannot reach `images=1` until this is
  fixed); WP-106 (ADR-0537's own WP, same operator, a different confirmed
  `maas-controller` defect on `ExternalModel`).
- **Target:** v0.7.

## Goal

`ai-gateway` cannot open a single connection to any external SaaS provider,
and has not been able to since its pod started. Every C2/C3 request that
should reach OVHcloud or Mistral fails and falls back to a local model,
silently - no alert, no failed health check, and the platform looks healthy
throughout. Restore that egress without weakening the mesh for the pod's
other outbound traffic.

## Live evidence already gathered (2026-09-03, do not re-derive)

Envoy's own counters, `pilot-agent request GET clusters` in `ai-gateway`'s
`istio-proxy`:

| Upstream | `cx_total` | `cx_connect_fail` | `rq_total` |
| --- | --- | --- | --- |
| `oai.endpoints.kepler.ai.cloud.ovh.net` (SDXL + gpt-oss-120b) | 49 | 49 | 0 |
| `api.mistral.ai` (mistral-large, Codestral) | 30 | 30 | 0 |

Istio telemetry tags every one `response_flags.UF,URX` with 0 bytes sent.
Never a single successful request.

The user-visible symptom, from the `make d3 stresstest agents` run that
exposed it:

```
10:24:31 ai_gateway image_call: provider=ovhcloud-sdxl model=stable-diffusion-xl-base-v10
10:24:31 openai._base_client Retrying request to /images/generations in 0.45s
10:24:32 openai._base_client Retrying request to /images/generations in 0.88s
10:24:33 WARNING ai_gateway image provider 'ovhcloud-sdxl' failed: Connection error.
         "POST /v1/images/generations HTTP/1.1" 502 Bad Gateway
```

**Three-way isolation** - this is the part worth not re-deriving:

1. **Non-mesh pod -> host: works.** `curl` from `trusted-artifact-signer`'s
   `cli-server` (no sidecar), on the *same node* as `ai-gateway`, gets
   OVHcloud `http=200` and Mistral `http=401` (no API key), TLS handshake
   under 80ms. The endpoints are healthy; this was never an outage.
2. **Mesh pod -> host with a ServiceEntry + DestinationRule: reset.** Both
   `ai-gateway` and `mcp-gateway` get `Connection reset by peer`.
3. **Mesh pod -> host with no ServiceEntry: works.** From that same mesh pod,
   `https://github.com` returns `200`. `meshConfig` sets no
   `outboundTrafficPolicy`, so the default `ALLOW_ANY` sends it through
   `PassthroughCluster` - raw TCP, no TLS origination, no problem.

A plain TCP probe from an app container is worthless here and must not be
used as evidence: it terminates on the sidecar and "succeeds" regardless.

## Root cause

The differentiator isolated above is exactly the pair the `maas-controller`
reconciler generates from our `ExternalModel` CRs
(`gitops/charts/models/templates/externalmodel-mistral.yaml`,
`externalmodel-ovhcloud-gpt-oss-120b.yaml`): a `ServiceEntry` (port 443,
`protocol: HTTPS`, `resolution: DNS`) plus a `DestinationRule` with
`trafficPolicy.tls.mode: SIMPLE`.

`ai-gateway` composes `https://` endpoints
(`platform/ai-gateway/provider-routing.yaml`,
`image-provider-routing.yaml`) and terminates its own TLS with the image's
certifi bundle. The DestinationRule therefore asks Envoy to originate a
**second, redundant TLS layer** over bytes that are already a TLS
ClientHello. Same family as the `*-kserve-workload-svc` double-TLS trap and
as the port-8000 case `gitops/charts/ai-gateway/templates/deployment.yaml`
already works around with `traffic.sidecar.istio.io/excludeOutboundPorts`.

Neither DestinationRule is ours to edit - both are controller-owned and
recreated on reconcile.

### Ruled out, with the check that ruled it out

- **Not an OVHcloud/Mistral outage** - point 1 above.
- **Not NetworkPolicy** - `gitops/charts/ai-gateway/templates/networkpolicy.yaml`
  declares `policyTypes: [Ingress]` only; there is no egress rule to violate.
- **Not the SDS `service-ca.crt` error loop, and not
  `automountServiceAccountToken: false`.** This was the first hypothesis and
  it is wrong. `config_dump` shows both clusters validate against SDS
  resource `file-root:system`, which is in `dynamic_active_secrets` and
  healthy; the failing `service-ca.crt` resource sits in
  `dynamic_warming_secrets`, referenced by nothing. And `mcp-gateway`, which
  runs `automountServiceAccountToken: true` and *has* the file, fails
  identically. ADR-0411's "so-far-benign" note about that loop stands.

## Steps

1. Author a client-side `DestinationRule` per external host that pins
   `trafficPolicy.tls.mode: DISABLE`, so Envoy passes the application's own
   TLS bytes through end to end. In-repo precedent for authoring a DR to
   override a traffic policy: `gitops/charts/mariadb/templates/destinationrule-mariadb.yaml`
   and `gitops/charts/postgresql/templates/destinationrule-postgres.yaml`
   (both `mode: DISABLE`, both with the rationale in a header comment).
2. Scope each one with `workloadSelector` on `ai-gateway`. Two
   DestinationRules for the same host in one namespace otherwise resolve by
   an unpredictable oldest-wins rule; a `workloadSelector` DR takes
   precedence over the selector-less controller-owned one for matching
   workloads. Istio here is v1.30.3, well past the version that added it.
3. Drive the host list off the same values that render the `ExternalModel`
   CRs (`gitops/charts/models/values.yaml`, `externalModels.*`) rather than
   hardcoding the two hostnames a second time.
4. Re-run the verification below, then close WP-112.

Rejected: `traffic.sidecar.istio.io/excludeOutboundPorts: "443"`. The
port-8000 pattern does not transfer - 443 carries every outbound HTTPS call
this pod makes, so excluding it would pull far more than these two hosts out
of the mesh, losing telemetry and policy on all of it.

Rejected: rewriting the endpoints to `http://` so Envoy originates the TLS
the DestinationRule expects. That makes correct operation depend on a
controller-owned resource continuing to exist, and puts cleartext model
traffic on the pod's loopback.

## Acceptance checks

- `python3 platform/docs/check_docs.py` exits 0.
- From inside `ai-gateway`, an HTTPS request to each host returns the same
  status a non-mesh pod gets (`200` for OVHcloud, `401` for Mistral).
- Envoy's `rq_success` for both clusters advances above 0 and
  `cx_connect_fail` stops climbing.
- `make d3 stresstest agents BULK=0`: Comage's `img-mockup_request` and
  `comage_chat_uses_photorealistic_images_only_for_marketing_visual_requests`
  reach a real SDXL image, with `sxa_visualization_boundary` still 1/1.
- `ai-gateway` logs show `image_call: provider=ovhcloud-sdxl` no longer
  followed by `Connection error`.

## Out of scope

- Fixing `maas-controller` itself, or the `ReconcileFailed` `MaaSModelRef`s
  ADR-0537 already documents - this WP works around the resources it emits,
  it does not repair the operator.
- The port-8000 `excludeOutboundPorts` workaround already in
  `gitops/charts/ai-gateway/templates/deployment.yaml`. Different
  DestinationRule, different mechanism, still correct for its own case.
- `img-mockup_request`'s grounding-based decline - a WP-112 finding, not an
  egress problem.
- Adding alerting for a provider that never connects. Real gap (this went
  unnoticed for at least a day behind a silent local-model fallback), but it
  belongs with the observability work, not here.

## Status updates

- On merge: State -> "Repo work merged", and record the live Envoy counters
  from the first run that shows `rq_success > 0`.
- On a clean stresstest with both Comage checks green: State -> "Done", and
  update WP-112's own State in the same pass - this is its last blocker.
