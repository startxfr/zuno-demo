# WP-220: Evaluate the RHOAI 3.6 MCP lifecycle, MaaS consumer portal and WorkbenchesV2 components

- **State:** Repo work in review
- **ADRs:** [ADR-0571](../../adr/0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0036](../../adr/0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)
- **Depends on:** [WP-195](wp-195-update-every-operator-on-demo333-through-the-repository.md) (RHOAI 3.6.0-ea.2 live on demo333)
- **Related:** [WP-152](wp-152-mcp-gateway-evaluation-and-mcp-north-side.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md), [WP-177](wp-177-finish-the-maas-quota-delegation.md), [WP-206](wp-206-kubernetes-read-tools-behind-the-mcp-gateway.md)
- **Target:** v0.11
- **Estimated files touched:** ~3 for the evaluation (this file, the tracker, the change log); a pilot adds the chart value and the DSC patch, decided later

> Why: RHOAI 3.6.0-ea.2 brings three DSC components that are `Removed` on demo333: `mcplifecycleoperator`,
> `dashboard.maasConsumerPortal` and `workbenches.workbenchesV2`. Before enabling any of them on an EA platform, this WP records what
> each one does, which custom code of this project it could replace, and what stays open. Written from the repository, the live cluster
> (read only) and the upstream repositories and documentation. Nothing was changed on the cluster.

## Goal

A decision per component (adopt, pilot, wait), a pilot choice, and the list of questions that gate each pilot.

## 1. MCP lifecycle operator

**What it is.** `kubernetes-sigs/mcp-lifecycle-operator` (API `mcp.x-k8s.io/v1beta1`, beta). An `MCPServer` object (image, port, path,
env and secrets, storage mounts, replicas, resources, probes, security context, service account, `mcp.stateless`) generates the
Deployment, Service and NetworkPolicy, and publishes the server's address and discovered capabilities in `status`. The
`network.ingressFrom` field takes standard NetworkPolicy peers; under the operator's `restricted` posture the list must include the
operator pods and each gateway source, otherwise the operator's handshake cannot reach the server and no address is published.
`spec.gateway` makes an `MCPGatewayBinding`; two providers ship, `httproute` (Gateway API) and `kuadrant` (Kuadrant MCP gateway). A
bring-your-own mode references existing workloads.

**Today in this project.**

| Piece | Where | Size |
|---|---|---|
| MCP gateway, the single policy point (agent and task rights, tool policy, classification, `allow_context`, `auth_mode`, JWT groups) | `components/mcp-gateway/app/` | about 3,470 lines Python, plus 575 in `app/handlers/` |
| Five servers (confluence, git-forge, aap, salesforce, k8s): Deployment, Service, ServiceAccount, NetworkPolicy from the gateway only, ExternalSecret | `gitops/charts/mcp-*` | about 1,500 lines of near-identical charts |
| Binding registry, 35 capabilities with their endpoints | `platform/bindings/tools/tool-bindings.yaml`, `app/bindings.py` | 419 + 220 lines |
| Scaffolder and conformance check | `platform/scaffolding/new_mcp_server.py`, `platform/supply-chain/check_mcp_server_conformance.py` | 716 + 166 lines |
| Install ordering, Argo apps per component | `ansible/roles/mcp`, `gitops/apps/mcp` | about 400 lines |
| Server health | day-3 check probes only the gateway; servers are blocked by their NetworkPolicies | gap |

ADR-0571 and WP-152 evaluated Kuadrant's MCP gateway (v0.7.1, tech preview) and kept the custom gateway because it cannot express the
agent and task rights, classification and `allow_context` of ADR-0011 and ADR-0036. RHCL 1.5.0 now installs the Kuadrant
`mcp-gateway-controller` (1.0.2, idle: no CR, namespace `mcp-system` absent).

**Assessment.**
- **Servers: strong fit, low risk.** Five `MCPServer` objects could replace most of the 1,500 chart lines, give each server a
  `status` with address and tools (closing the observability gap), and feed the binding registry. The Python tool logic does not change.
- **Gateway: the operator does not enforce policy.** It only binds servers to a gateway. Replacing `components/mcp-gateway` means
  expressing the OKF-bundle intersection, classification and delegation in Authorino (OPA/CEL) on the Kuadrant gateway. About 1,500 lines
  of that logic have no counterpart in a generic gateway, so the realistic outcome is a hybrid: operator for servers, custom policy layer in front.
  This needs a spike before the ADR-0571 decision is reopened.

**Open questions (each gates a pilot).**
1. Can the generated NetworkPolicy admit only the zuno gateway (and the operator), and does it coexist with the mesh and our `zuno-mcp` rules?
2. Can the pod keep the ExternalSecret-fed environment, the `X-Zuno-Gateway-Token` check, digest-pinned images, and a dedicated service account?
3. Does the server's tool list reach `status` when the server requires the gateway token?
4. Does `MCPServer` status or metrics give what the day-3 check lacks (per-server readiness without opening the NetworkPolicy)?
5. Beta API: what is the upgrade path from `v1alpha1` objects (a storage version migration page exists upstream)?

## 2. MaaS consumer portal

**What it is.** A portal shipped by the dashboard operator and managed independently of the core dashboard
(`dashboard.maasConsumerPortal`). One Core-BFF Deployment is served by the MaaS gateway under `/maas-portal`. A `kube-auth-proxy`
(OIDC session) serves `/oauth2` publicly; an Authorino policy validates the browser session on the portal route and redirects to
`/oauth2/start` without a session. The OIDC issuer is configurable through `AITenant.spec.oidc` (tech preview), with
`clientSecretRef` for the proxy and the redirect `https://<MaaS gateway>/oauth2/callback`; the policy carries organization claims
(`org_id`, `roles`). Upstream features: API key create, list and revoke through maas-api, a Gen AI view, and a per-project
observability page (Perses).

**What maas-api gives for keys** (MaaS documentation): `sk-oai-*` keys stored as SHA-256 hashes, `expiresIn` TTL (90 days by default),
binding to one MaaSSubscription at mint time, the creator's groups copied at creation, `last_used_at`, bulk revoke by user or
subscription with a dry-run, soft-deleted rows kept 90 days, optional organization association, per-subscription telemetry labels.

**Today in this project.** No code manages MaaS keys. They are minted by hand (WP-164: an OpenShift login that creates `User` and
`Identity` objects, a 2 h key). The `MAAS_GATEWAY_API_KEY` fallback in `components/ai-gateway/app/maas_adapter.py` is dead. Human
traffic goes Keycloak JWT, then the ai-gateway, then MaaS with a service-account token. There is no key-use audit.
Not replaceable by the portal: the quota ledger (`quota.py` and friends, about 490 lines, plus the 694-line generator), the token proxy
(about 355 lines), Keycloak client secrets and provider keys in Vault.

**Assessment (target: humans with external tools such as an IDE or CLI).**
- Fills a real gap: self-service issue, list, revoke and expiry for a person calling MaaS directly, and replaces the manual WP-164 procedure.
- A portal key bypasses the ai-gateway, so the ledger's user and group ceilings and the attested headers do not apply. The only ceiling is
  the MaaSSubscription of the key. A subscription for such keys has to be designed (rate, models, groups) before a pilot.
- External OIDC could let Keycloak users sign in and mint keys with their realm groups. That would revisit the WP-122 finding that
  `maas-gateway-auth` rejects Keycloak JWTs; it is tech preview.

**Open questions.**
1. Which subscription and ceiling does a human's external-tool key get? (needs the user)
2. Does portal sign-in work with Keycloak on this build, or only with OpenShift login?
3. Are key lifecycle events logged anywhere we can read (audit is empty today)?
4. What does the observability page show compared with the `zuno_*` dashboards?
5. Each new subscription adds limits to the gateway wasm object (see section 4).

## 3. WorkbenchesV2

**What it is.** The second-generation workbench controller, `workbenches.workbenchesV2`, based on Kubeflow Notebooks v2. Upstream states
that Notebooks v2 is not yet released. The classic controller (Notebook CR `notebooks.kubeflow.org`) stays Managed and Ready in `zuno-ai-build`.

**Today in this project.** Nothing to migrate. No Notebook object, image, ImageStream, PVC, PodDefault, culling rule or MaaS variable
injection exists; no demo step depends on a workbench. The only traces are `workbenchNamespace: zuno-ai-build`
(`gitops/charts/openshift-ai/values.yaml`), the ADR-0328 and ADR-0333 intent, and an Istio selector listing the classic controller
pods (`gitops/charts/service-mesh/templates/istio.yaml`).

**Assessment.** This is a new scenario, not a migration. Candidate: a workbench in `zuno-ai-build` where a data scientist reaches the
models through MaaS (a portal key, section 2) to run an MMLU-style check or prepare LoRA data, which would tie the three components
together. Risks: unreleased upstream, an API different from the Notebook CR, and SCC, selector and NetworkPolicy traps like those of the 3.6 upgrade.

**Open questions.** Which V2 API objects exist on the cluster (none found yet); how images are provided; how the workbench gets a
MaaS key; whether the `zuno-ai-build` namespace policy (not mesh-injected) fits.

## 4. Related findings

- The MaaS 3.6 documentation describes the quota incident of WP-195 (`subscription-cardinality.md`, "Gateway Config Size"): the
  wasm object grows with limits x route matches and hits the 1.5 MiB etcd limit. Red Hat's levers are to reuse a small set of rates across
  subscriptions, and to set `serving.kserve.io/model-based-routing-only: "true"` on an LLMInferenceService (19 to 9 route matches). This
  could allow `zuno-token-quota` to be switched on again, but only if the ai-gateway calls models by body-based routing; today it uses
  path-based URLs. To verify on one model, measuring the EnvoyFilter size, before touching the policy.
- The 3.6 upgrade guide describes IPP being replaced by Praxis (`maas.opendatahub.io/payload-processing-type=praxis`). Our
  payload-processing sidecar and NetworkPolicy workarounds may be affected.

## 5. Spike results (2026-11-05, read only on demo333)

**A human key for Claude Code in VS Code (user request: large ceilings, gpt-oss-20b in the cluster and Codestral).**
- **gpt-oss-20b through MaaS speaks the Anthropic Messages API.** With a service-account token, `POST
  /zuno-ai-run/gpt-oss-20b/v1/messages` returned 200 with `anthropic-version: 2023-06-01`, including a `tool_use` block for a
  tool call and a streamed `message_start` / `content_block_start` sequence. The model is served with `--max-model-len=131072
  --enable-auto-tool-choice --tool-call-parser=openai`. So a MaaS key can drive Claude Code with `ANTHROPIC_BASE_URL` set to the
  model's path URL, `ANTHROPIC_AUTH_TOKEN` set to the `sk-oai-*` key and the model name `gpt-oss-20b`. Not tested: Claude Code
  itself (it also calls `/v1/messages/count_tokens`), and long sessions.
- **Codestral is not reachable through MaaS.** MaaS holds two ExternalModels only (`mistral-large`, `gpt-oss-120b-ovhcloud`), both with
  `apiFormat: openai-chat`. `POST /zuno-ai-run/mistral-large/v1/messages` returns 500: ExternalModels need Praxis API translation, which is
  not enabled here (the IPP to Praxis migration is described in the 3.6 upgrade guide). Codestral runs only through the ai-gateway
  (`mistral-codestral`, dedicated key, classification C1/C2 only), and the ai-gateway exposes `/v1/chat/completions` only, not
  `/v1/messages`.
- **Existing subscriptions** (MaaS namespace `models-as-a-service`): `<model>-ai-gateway` 1,000,000 tokens/h (priority 100),
  `-lightspeed` 200,000/h (50), `-agents` 100,000/h (10), `-sales` 5,000/h (1). No subscription exists for developers. The Keycloak
  realm has the group `ocp-ai-dev` (member `ai-dev-01`), which fits a developer subscription.
- **Ceiling arithmetic.** Claude Code resends the whole context each turn, so a 40,000-token context costs about 40,000 tokens per
  call; 1,000,000 per hour is about 25 calls. A coding session needs several million per hour.
- **Gateway size.** The wasm object is 1.27 MB against the 1.5 MiB etcd limit. A subscription at an existing rate adds a clause of about
  80 bytes; a new rate adds a whole limit on every route match of that model (15 matches here).

**Portal sign-in with Keycloak.**
- The `AITenant` CRD of 3.6.0-ea.2 has `spec.oidc` with `clientId`, `issuerUrl` and `ttl` only. The `clientSecretRef`, `refreshInterval` and
  `audience` fields that the upstream main documentation lists for the portal's auth proxy are not in this build. So Keycloak can be
  accepted as a token issuer on the gateway (the WP-122 question, to test), but a Keycloak browser sign-in for the portal is not
  supported on this build. OpenShift login is the supported path, which matches the user's choice.
- The portal is not deployed (`MaaSConsumerPortalAvailable=False`, "not enabled"). The dashboard operator carries one related image
  (`odh-mod-arch-maas`), and `ai-gateway-controller` runs. Whether enabling the field deploys a complete portal in this EA build can only
  be learned by a pilot.

**MCP (Kuadrant side).** The CRDs on the cluster: `MCPServerRegistration` (targetRef to an HTTPRoute, `credentialRef`, `prefix`,
`userSpecificList`, `tokenURLElicitation`), `MCPVirtualServer` (`tools`, `prompts`: a tool allow-list per virtual server) and
`MCPGatewayExtension` (`trustedHeadersKey`, `oauthProtectedResource`, `sessionStore`, `publicHost`). None of them carries agent or task
rights, data classification or `allow_context`. Those would have to live in an Authorino AuthPolicy on the MCP route, written in
OPA/CEL against the OKF bundles. The `kubernetes-sigs` operator's `network.ingressFrom` accepts standard NetworkPolicy peers, so the
"only from the zuno gateway" rule of ADR-0037 is expressible; whether the generated pod keeps the ExternalSecret and gateway-token
wiring is still to be tested on one server.

## 6. Recommendations

1. **Claude Code key: MaaS key on gpt-oss-20b only.** New subscription `gpt-oss-20b-developer`: owner groups `/ocp-ai-dev` and
   `ocp-ai-dev` (both spellings, as the other subscriptions do) plus the user's own login, priority 20, 5,000,000 tokens/h on
   `gpt-oss-20b` only, key TTL 30 days. Add the group to `gpt-oss-20b-entitlement`. Check the wasm object size after it is applied.
2. **Codestral stays on the ai-gateway** (Keycloak token, `zuno-code`, as tested by WP-194), because it is a SaaS model bound by
   classification. To use it from Claude Code, either a translating proxy in front of the ai-gateway or MaaS with Praxis translation; both
   are separate decisions.
3. **Portal pilot with OpenShift login** after the key works by hand, to get the self-service lifecycle.
4. **Keycloak token instead of a static key** (Claude Code can fetch a short-lived token through its `apiKeyHelper` setting): worth one
   test once `AITenant.spec.oidc` is configured, since it would avoid long-lived keys.

## 7. Pilot 1: developer key on gpt-oss-20b (2026-11-05, user go)

- `gitops/charts/models/values.yaml` gained the subscription `gpt-oss-20b-developer`: owner user `dev` (the static OpenShift user of
  demo333), priority 20, 5,000,000 tokens/h on `gpt-oss-20b` (commit 7e8bc34b). The chart already derives the `MaaSAuthPolicy` subject
  from the subscription, so `gpt-oss-20b-entitlement` gained `dev` with no second edit.
- Live: ArgoCD created it; the `MaaSSubscription` is `Active`, its `TokenRateLimitPolicy` `maas-trlp-gpt-oss-20b` is `Accepted`. The gateway
  wasm object went from 1,298,548 to 1,336,460 bytes (+38 KB) and the kuadrant-operator logged no `request is too large`. A chat through
  MaaS answers 200 and no token answers 401.
- Not yet done: the key itself. It must be minted by the `dev` user (`oc login` then `POST /maas-api/v1/api-keys`, `"subscription":
  "gpt-oss-20b-developer"`, `"expiresIn": "30d"`); the plaintext key is shown once. Then Claude Code is tested against
  `https://maas.apps.demo333.startx.fr/zuno-ai-run/gpt-oss-20b` with `ANTHROPIC_AUTH_TOKEN` set to that key.

### Pilot 1 results (2026-11-06, key minted by the user as `dev` through the maas-api REST call, subscription `gpt-oss-20b-developer`)

Tested with curl against `https://maas.<domain>/zuno-ai-run/gpt-oss-20b`, headers as Claude Code sends them:

| Request | Result |
|---|---|
| `GET /v1/models` with the key / without | 200 / 401 |
| `POST /v1/messages` (Anthropic Messages API) | 200, a `thinking` block then the text answer |
| `POST /v1/messages` with `stream: true` | 200, Anthropic SSE events (`message_start`, `content_block_delta`, ...) |
| `POST /v1/messages` with a `tools` array | 200, `stop_reason: tool_use` with a well-formed `tool_use` block |
| `POST /v1/messages/count_tokens` | 200, `input_tokens` returned |
| `POST /v1/messages` with a 24,082-token system prompt, three times | 200 each; 5.9 s cold, about 0.5 s on the repeats (prefix cache) |

The real Claude Code binary was not run: `claude` on the workstation is a podman wrapper that mounts the user's own `~/.claude.json`.

**Finding: the subscription ceiling does not count Anthropic-format traffic.** Limitador's counter for `dev` stayed at 5,000,000 of
5,000,000 after about 72,000 tokens sent through `/v1/messages`, and moved to 4,999,914 after one `POST /v1/chat/completions` of 86 tokens.
The Anthropic response carries `usage.input_tokens` and `usage.output_tokens` but no `total_tokens`, which is what the MaaS token limit
reads. So a Claude Code client is effectively uncapped by `gpt-oss-20b-developer`; the 5 M tokens per hour is real only for OpenAI-format
calls. Harmless for this pilot (the user asked for wide ceilings) but it must not be sold as a quota. Not investigated: which field the
generated TokenRateLimitPolicy reads, and whether a counter expression on `input_tokens + output_tokens` is possible in this build.

**Outcome (2026-11-06, user):** Claude Code in VS Code worked against `gpt-oss-20b` with this key. The user then revoked it, and the
revoked key is refused with 403 on `/v1/models`. Pilot 1 is done.

## 8. Pilot 2: MaaS consumer portal (2026-11-05, user go, OpenShift login)

Window announced to the peer sessions and opened after zuno-demo-7e closed its Codestral-down drill (18:21Z). DSC `zuno-dsc` backed up
first, then one live patch: `dashboard.maasConsumerPortal.managementState: Managed` (the chart carries the same value, because ArgoCD
ignores the DSC `/spec`).

What happened:

- The dashboard operator created `maas-consumer-portal` (Deployment, Service, NetworkPolicy, HTTPRoute) within seconds. The pods looped in
  `Init:1/2` and the DSC went `Ready=False` (`MaaSConsumerPortalDeploymentUnavailable`).
- Cause: the same gap as ADR-0517. The portal pods are `part-of: maas-consumer-portal`, so the supplementary egress policy
  `zuno-dashboard-modules-istiod-egress` (selector `part-of: odh-dashboard`) did not select them, and the vendor policy `maas-consumer-portal`
  allows only DNS, 6443, `maas-ui` and `gen-ai-ui`. The istio-proxy xDS dial to istiod:15012 timed out.
- Fix, in the chart (b8eb1b51): the policy selector is now `part-of In (odh-dashboard, maas-consumer-portal)`. After the Argo sync the
  pod went 2/2 and the DSC `Ready=True`.
- Reachability: the portal is **not** under the MaaS hostname. The HTTPRoute is on `data-science-gateway` at
  `https://rh-ai.apps.demo333.startx.fr/maas-consumer-portal` (the earlier assumption `/maas-portal` on the MaaS gateway was wrong). An
  unauthenticated request gets a 302 to the OpenShift OAuth server (client `data-science`), as designed.
- No regression: MaaS without a token still answers 401, the four models are Ready, no unhealthy pod, DSC Ready.

Interactive run (2026-11-05 evening to 2026-11-06, the user signing in as the static OpenShift user `dev`, identity provider
`startx-htpasswd_auth`):

- **Sign-in first failed with a 404 at `/oauth2/callback`.** OpenShift authenticated `dev`, then the return hit
  `https://rh-ai.<domain>/oauth2/callback`, which no route served: the portal HTTPRoute has an explicit hostname, the vendor
  `oauth-callback-route` (to kube-auth-proxy) has none, and Istio does not merge a hostname-less route into the virtual host of a
  host-specific one. Fixed by the supplementary route `zuno-portal-oauth-callback` (chart template `maas-portal-oauth-callback.yaml`,
  4766b438); the callback then answers 403 without a session cookie, as kube-auth-proxy does, and the browser sign-in succeeds.
- **The portal opens**: Red Hat AI shell with "AI asset endpoints", "API keys" and "Playground". "AI asset endpoints" and "Playground" are
  empty ("To begin you must deploy a model"): they list models flagged as AI assets in the `Startx default project`, and the local
  models live in `zuno-ai-run`. Expected, and unrelated to the key flow.
- **"API keys" fails with "maas-api is not available".** Not a network problem: maas-ui reaches maas-api, which answers
  `GET /v1/tenants` with 500, "gateway openshift-ingress/maas-default-gateway is not configured with an external hostname (found internal
  service name: maas-default-gateway-istio.openshift-ingress.svc.cluster.local). Please configure the Gateway with
  spec.listeners[].hostname and use LoadBalancer service type". Our MaaS Gateway has no listener hostname and is reached through an
  OpenShift Route, so maas-api cannot derive the external URL and the portal's key pages cannot load.
- **Options recorded, none applied to the Gateway** (it carries every model call; a change regenerates the Kuadrant EnvoyFilters, and the
  2026-11-05 outage and the EnvoyFilter size limit are recent): (A) leave the Gateway as is and mint keys through the maas-api REST call;
  (B) add `hostname: maas.<domain>` to the `https` listener in `maas-gateway.yaml` (the seven attached routes have no hostname, so they
  would inherit it; untested whether maas-api accepts that without a LoadBalancer Service); (C) prove B on a throwaway Gateway and
  AITenant first. Preferred: A now, C only if the portal matters for the demo.

Still open: whether key events are audited, and which subscriptions the portal would list for `dev` once maas-api can answer.

## 9. Anthropic-format traffic is not counted by the MaaS token limit (2026-11-06)

The question left open by section 7 was which field the limit reads, and whether it could count `input_tokens + output_tokens`.

- **It is documented behaviour, not a defect.** The MaaS 3.6 documentation
  (`docs/content/configuration-and-management/quota-and-access-configuration.md`, the warning "Token rate limiting and API format")
  says token limits apply to `/v1/chat/completions` and `/v1/embeddings`; requests on `/v1/messages` (Anthropic Messages) or
  `/v1/responses` are not subject to them. Limitador counts `usage.total_tokens`; Anthropic reports `input_tokens` and `output_tokens`
  without a total, "so the rate limiting integration cannot extract the token count". Authentication, subscription validation and model
  access still apply. This is what section 7 measured.
- **The policy can be told which field to read, but not to add two.** Kuadrant's TokenRateLimitPolicy has
  `spec.dataExtraction.response.totalTokens`, an ordered list (1 to 8) of JSON Pointers where the first that resolves to a number wins; the
  built-in list starts with `/usage/total_tokens`. The CRD installed on demo333 has the field. A pointer returns one number, so the sum is
  not expressible. The closest is `[/usage/total_tokens, /usage/input_tokens]`, which counts the prompt only for Anthropic replies
  (the larger part for Claude Code, since the whole context is resent each turn) and misses the generated tokens.
- **The maas-controller would wipe a hand edit.** It does not set `dataExtraction`, and on every reconcile it replaces the whole `spec` of
  each managed TRLP (`maassubscription_controller.go`, `updateExistingTRLP`). The only durable ways are to opt a TRLP out of management
  (then subscription changes stop reaching it) or to ask upstream for a pass-through.
- **Options.** (1, recommended) Accept and document: Claude Code on a MaaS key is authenticated and authorised but not rate-limited by
  MaaS; the 5,000,000 tokens per hour of `gpt-oss-20b-developer` is real only for OpenAI-format calls. (2) Opt the `gpt-oss-20b` TRLP out
  and own it in the chart with the two-pointer list: undercounts, and freezes that model's subscriptions. (3) Upstream request to the
  maas-controller; the user deferred upstream issues earlier.

## 10. Two-listener Gateway chart (proven on a throwaway Gateway, not yet live)

The portal's "API keys" page needs maas-api to report an external URL (section 8). Upstream `maas-api/internal/tenant/handler.go` takes the
`hostname` of the first ready HTTPS listener that has an attached route, and only falls back to the Gateway address (which is the
in-cluster Service name here, then rejected). A LoadBalancer Service is not needed; the error text is misleading.

A hostname on the single existing listener would break every in-cluster caller, because they send `Host: maas-default-gateway-istio.openshift-ingress.svc`
(the ai-gateway, lightspeed and the four provider endpoints in `platform/ai-gateway/provider-routing.yaml`). The prepared change keeps both:

- listener `https-external` (`hostname: maas.<clusterBaseDomain>`, port 443, same TLS secret and `allowedRoutes`) **first**;
- the existing hostname-less `https` listener second.

It sits behind `maasGateway.externalHostnameListener.enabled`, default `false`; rendered with the flag off the chart is identical to
today's, with it on the Gateway has the two listeners in that order. The chart is on `devel` with the flag off (fbf22cb4), and the flag is
set to `true` in `gitops/apps/openshift-ai/application-d1.yaml` (a90dfe7d), which has no effect live because Applications are not
git-synced and the live Application's `helm.values` is a text block.

**Live proof on a throwaway Gateway (2026-11-06, demo333).** The first attempt, in its own namespace, could not start its Gateway pod:
the mesh accepts certificate requests only from a fixed list of namespaces (`zuno-default-deny-other-namespaces` in `zuno-mesh`, which
includes `openshift-ingress`). The second, with five `zuno-hostname-test-*` objects in `openshift-ingress` (all deleted afterwards), gave
two listeners both Accepted and Programmed with `attachedRoutes: 1` each, and through a port-forward:

| Request (Host / SNI) | Result |
|---|---|
| external host, external SNI | 200 |
| Service name, Service name (what the ai-gateway, lightspeed and the providers send) | 200 |
| external Host, Service-name SNI | 200 |
| any Host, no SNI | 200 |
| unknown host and SNI | 200 (the hostname-less listener catches it, as today) |
| external SNI with the Service name as Host | 404 (does not occur: callers use a matching SNI) |
| unknown path | 404 from the Gateway |

Two things to know. The test backend sits behind `openshift-ingress-deny-all`, so it needed a NetworkPolicy of its own (a test artefact, not
a chart concern). And with a hostname on a listener the cluster's Gateway controller adds `DNSReady=False` ("One or more listeners have DNS
provisioning issues", no DNSRecord created); `LoadBalancerReady=False` is already there on `maas-default-gateway`, which stays Programmed
and Argo-Healthy, so this is expected to be cosmetic, to confirm after the live change.

**Not yet done: the live change.** It is one edit of the live Application's `helm.values` (add `externalHostnameListener.enabled: true`
under `maasGateway`), which turns the Gateway that carries every model call. The auto-mode classifier refused it as a change to a shared
resource, so it waits for the user's explicit go. Backups to take first: the Application and the Gateway YAML. Checks after: the Gateway
has `https-external` then `https`; `GET /maas-api/v1/tenants` answers 200 with `https://maas.<domain>`; the portal "API keys" page loads;
the four models answer from the ai-gateway; MaaS without a token is 401; the EnvoyFilter is still 1,336,461 bytes. Rollback: remove the
flag from the Application values (or set it `false`).

## 11. The k8s MCP server as an MCPServer (paper mapping, 2026-11-06)

State today: the CRD `mcpservers.mcp.x-k8s.io` is not on the cluster (`mcplifecycleoperator` is Removed in the DSC). Mapping of
`gitops/charts/mcp-k8s` onto the `mcp.x-k8s.io/v1beta1` `MCPServer` spec (upstream `api/v1beta1/mcpserver_types.go`):

| Chart object | MCPServer field | Fit |
|---|---|---|
| Image `ghcr.io/containers/kubernetes-mcp-server@sha256:...`, pull policy | `spec.source.containerImage.ref`, `pullPolicy` (a digest is accepted and validated) | Fits |
| `args: --config /etc/k8s-mcp/config.toml` | `spec.config.arguments` | Fits |
| ConfigMap `k8s-mcp-config` mounted read-only | `spec.config.storage[]` (ConfigMap source, path, permissions); the ConfigMap itself stays in the chart | Fits |
| Port 8080 | `spec.config.port` (required); `spec.config.path` defaults to `/mcp`, to confirm against the server | Fits, one check |
| `replicas`, `resources` | `spec.runtime.replicas`, `runtime.resources` | Fits |
| ServiceAccount `k8s-mcp` and its RoleBindings (`view` in 13 namespaces, `cluster-monitoring-view`) | `spec.runtime.security.serviceAccountName`; the SA and RBAC stay in the chart | Fits |
| `runAsNonRoot`, seccomp, drop ALL, read-only root | `runtime.security.podSecurityContext` and `securityContext` | Fits |
| Probes on `/healthz` | `runtime.health.livenessProbe`, `readinessProbe` (passed through unchanged) | Fits |
| NetworkPolicy: ingress only from pods labelled `app.kubernetes.io/name: mcp-gateway` | `spec.network.ingressFrom` takes standard peers | Fits, with a cost: under the operator's "restricted" posture the list must also admit the operator's own pods (its handshake), which widens ADR-0037's "only the gateway" |
| Service `k8s-mcp` (URL `http://k8s-mcp.zuno-ai-run.svc:8080` is in `tool-bindings.yaml`) | generated by the operator; its name must be checked, or use `serviceRef` | To verify |
| `priorityClassName: zuno-workload-default` | no field | Gap (only in "bring your own workload" mode) |
| `checksum/config` annotation that rolls the pod on a ConfigMap change | no field found | Gap: a config change would not restart the server |
| Argo sync-wave annotations | `spec.extraAnnotations` (on generated objects) | Probably fits |
| Tool inventory, address, capabilities | `status` (filled by the operator) | New: nothing consumes it, since `tool-bindings.yaml` is static |

What is not lost: the k8s server has no gateway-token check and no ExternalSecret (the chart says so), so there is nothing of that kind to
carry. The other four MCP servers do carry ExternalSecrets and the gateway token as env, which `config.env` and `config.envFrom` cover.
Mesh: `zuno-ai-run` has no PeerAuthentication (permissive), so an operator handshake from a non-mesh pod is possible.

**Verdict: a live pilot is reasonable, but the gain for this one server is modest** (the Deployment, Service and NetworkPolicy templates, 100 lines,
become one object; the ConfigMap, ServiceAccount and RBAC stay, and there are two gaps and a wider ingress). Prerequisites, in order: DSC backup; user go; an announced window; set
`mcplifecycleoperator: Managed` through a live patch (ArgoCD ignores the DSC `/spec`); check that the CRD appears and what the operator
namespace and pods are; `kubectl apply --dry-run=server` of the MCPServer; then run it in a throwaway namespace next to the chart-managed
server (same ConfigMap and RBAC) and compare the generated Deployment, Service and NetworkPolicy field by field before any switch.

## 12. Workbench V2 scenario (design only, 2026-11-06)

Facts: no Notebook v2 API is installed (`notebooks.kubeflow.org` is the classic one), `workbenchesV2` is Removed, and upstream says
Notebooks v2 is unreleased. A pilot cannot run until enabling the component shows which CRDs it brings; this section is the scenario to
test then.

Scenario: a data scientist opens a workbench in `zuno-ai-build` and runs an MMLU-style check against `gpt-oss-20b` through MaaS, then writes
the result to the existing S3 bucket. This reuses what already exists (the models, the developer-style subscription, the evaluation data).

- **Key.** A MaaS key bound to a subscription, minted through the maas-api REST call today (the portal's key page once section 10 is
  proven). It reaches the workbench as a Secret mounted as an environment variable (`MAAS_API_KEY`, `MAAS_BASE_URL`), never in an image. A
  short TTL (days) and revocation at the end of the exercise.
- **Image and storage.** One RHOAI-provided data-science image from the ImageStreams already on the cluster; a small PVC for the dataset.
  Culling after a day of idleness.
- **Network.** `zuno-ai-build` is not mesh-injected. The workbench reaches MaaS through the external route (`maas.<domain>`), so it needs
  egress to the router and DNS; check the namespace's default-deny policy and that the key path (Authorino on the Gateway) accepts the call.
- **Platform traps to expect** (the 3.6 upgrade showed them): SCC for the notebook pod, a vendor NetworkPolicy that allows only its own
  ports, the Istio selector in `gitops/charts/service-mesh/templates/istio.yaml` that lists the classic controller pods.
- **First live step, after a go.** Set `workbenches.workbenchesV2.managementState: Managed`, look at the new CRDs and pods, then decide
  whether to continue. Revert by setting it back to `Removed`.

## 13. model-based-routing-only: preparation (2026-11-06)

What it does (MaaS 3.6, `subscription-cardinality.md`): with `serving.kserve.io/model-based-routing-only: "true"` on a model, the managed
HTTPRoute drops the `/{namespace}/{name}/...` path tree and keeps header-based routing (the doc says 19 matches become 9; ours are 15 per
model). It needs `serving.kserve.io/model-based-routing-enabled: "true"` first, which none of our four LLMInferenceServices carries.

Why it is not a toggle here: every local-model caller uses the path form.

- `platform/ai-gateway/provider-routing.yaml` (the four models, `https://maas-default-gateway-istio.openshift-ingress.svc/zuno-ai-run/<model>/v1`),
  `gitops/charts/ai-gateway/values.yaml` and `gitops/charts/lightspeed-config/values.yaml` (the Service-name endpoint), the test scripts
  `platform/testing/quota_counters_probe.py` and `token_quota_429.py`, and external users such as Claude Code with
  `ANTHROPIC_BASE_URL=.../zuno-ai-run/gpt-oss-20b`.
- The body-based call shape, `/v1/chat/completions` at the Gateway root with `model` in the body, is the one the ADR-0201 IPP anchor
  workaround exists for (`gitops/charts/openshift-ai/templates/maas-gateway-ipp-anchor.yaml`: without it that shape 404s), so the annotation
  would also depend on that workaround, and on the 3.6 IPP to Praxis change recorded in the upgrade guide.

Test protocol, once the user allows a window: pick the lowest-stake model (`qwen35-9b-wesh`), accept that its path URL will 404; record the
route match count and the EnvoyFilter size; set both annotations through the models chart (a live patch is reverted by selfHeal); check the
matches fall; check a body-based call works and the path call 404s; record the new size; revert. Only if the saving is real and the
clients can move to the body-based form does it make sense to turn `zuno-token-quota` back on. Until then it is a client migration, not a
setting.

## Steps

1. This evaluation (done, in review).
2. Read-only spikes: the Kuadrant `MCPGatewayExtension`, `MCPServerRegistration` and `MCPVirtualServer` CRDs already on the cluster, to
   see whether ADR-0011 rights can be expressed in Authorino; the portal's Keycloak sign-in; the `status` fields of `MCPServer`.
3. Pilot gate. Recommended first pilot: the portal (one DSC field, easy to revert). Second candidate: one MCP server (the upstream k8s
   server of WP-206) as an `MCPServer`. A pilot needs the user's go, an announced window, a DSC backup and a live patch, because ArgoCD
   ignores the DSC `/spec`.
4. Test `model-based-routing-only` on one model and measure the EnvoyFilter size.

## Acceptance

The three evaluations are accepted or amended by the user, one pilot is chosen with its subscription and ceiling, and the spikes of
step 2 are recorded in an evidence file.
