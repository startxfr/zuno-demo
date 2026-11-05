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
