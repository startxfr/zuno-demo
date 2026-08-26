# WP-085: Integrate OpenShift Lightspeed with Zuno inference, knowledge and identity

- **State:** Not started.
- **ADRs:** ADR-0524 (Proposed)
- **Depends on:** ADR-0521/WP-076 (Implemented - MaaS is the local-model transport this reuses),
  ADR-0117 (Implemented - the Confluence MCP server), ADR-0060 (Implemented - Day 1/Day 2/Day 3
  sequencing)
- **Related:** WP-072/WP-073 (the `aap`/`aap-config` two-component split this mirrors)

## Goal

Make OpenShift Lightspeed answer console questions using a Zuno-served local model, the
operator's own OpenShift documentation and live-cluster introspection, and read-only internal
Confluence knowledge reached through the **existing** MCP Gateway - with the operator installed
in Day 1 and every Zuno-dependent wire connected in Day 2.

## Why

Every backing capability already exists; none of it is currently reachable from the console. Two
concrete blockers make this more than configuration, both verified in-repo:
`components/mcp-gateway` exposes REST (`/v1/tools/{name}/invoke`), not MCP, so Lightspeed's
`spec.mcpServers[]` has nothing to connect to; and `components/mcp-gateway/app/auth.py` accepts
only a Keycloak-issued JWT, which Lightspeed cannot produce from any of its three header sources.
Step 3 and step 4 below close exactly those two gaps.

## Component and file layout (ADR-0524 clause 7)

Two components, mirroring `aap`/`aap-config` exactly - two roles, two Applications, **two
charts**. A single shared chart was considered and rejected: two ArgoCD Applications rendering
one chart contend over `argocd.argoproj.io/tracking-id` for the same resources.

| | Day 1 - `lightspeed` | Day 2 - `lightspeed-config` |
|---|---|---|
| Role | `ansible/roles/lightspeed/tasks/{install,precheck,uninstall}.yml` | `ansible/roles/lightspeed_config/tasks/{install,precheck,uninstall}.yml` |
| Chart | `gitops/charts/lightspeed` | `gitops/charts/lightspeed-config` |
| App | `gitops/apps/lightspeed/application-d{0,1}.yaml` (`zuno-lightspeed-d1`) | `gitops/apps/lightspeed-config/application-d{0,1}.yaml` (`zuno-lightspeed-config-d1`) |
| Contains | Namespace membership, OperatorGroup, Subscription, CSV wait | `OLSConfig/cluster`, provider Secret, CA ConfigMap, Keycloak client, MaaS entitlement wiring |
| Depends on | OLM only | `models`, `mcp`, `keycloak` |

Makefile placement:

- `DAY1_RUN_COMPONENTS`: insert `lightspeed` after `openshift-ai`, before `aiagent-operator` -
  it has no dependency on either, and this keeps `aiagent-operator` last as its comment requires.
- `DAY2_RUN_COMPONENTS`: append `lightspeed-config` **after `mlops`** (before the check-only
  `supply-chain`), so it runs once MaaS entitlement, the `/mcp` front-door and the agents are all
  in place.
- `ansible/playbooks/day1_install.yml` `day1_components` and `day2_install.yml`
  `day2_components` get the same two entries in the same positions, with a comment stating why
  the configuration half waits for Day 2.

The Day 1 role installs the operator and stops there. It must **not** create `OLSConfig` - an
`OLSConfig` without a reachable model or MCP endpoint sits Degraded for the whole Day 2 window.

## Steps

### Step 1 - Day 1: install the operator

Discover catalog and channel from the `PackageManifest` at run time rather than hardcoding, the
same pattern `ansible/roles/aap/tasks/install.yml` uses (fail loudly if the package is absent).
Confirmed on this cluster 2026-08-26: package `lightspeed-operator`, catalog `redhat-operators`,
`defaultChannel: stable`, CSV `lightspeed-operator.v1.1.2`, InstallModes **`OwnNamespace` only**.
Add `openshift-lightspeed` to `gitops/charts/namespaces/values.yaml` (no `istio-injection` label
- ADR-0524's operational note). OperatorGroup targets its own namespace.

### Step 2 - Day 2: local inference through MaaS

- `gitops/charts/models/values.yaml`: add a `MaaSSubscription` + `MaaSAuthPolicy` subject for
  Lightspeed's ServiceAccount, mirroring the existing `*-ai-gateway` entries (`user:
  system:serviceaccount:openshift-lightspeed:<sa>`, own rate limit, own priority).
  **The SA name cannot be determined ahead of the install** - checked 2026-08-26 against the
  v1.1.2 bundle CSV, which declares only `lightspeed-operator-controller-manager` (the operator's
  own SA); the operand ServiceAccounts are created by the operator at reconcile time. Read it off
  the running cluster after step 1 and before writing this value. It matters because the live
  `AuthPolicy/maas-gateway-auth` OPA `model_access` map lists only
  `system:serviceaccount:zuno-ai-run:ai-gateway` plus groups `agent_tekos`/`sales` - an unlisted
  identity is denied by omission, silently.
- `OLSConfig.spec.llm.providers[0]`: `type: rhoai_vllm`, `url` the MaaS gateway path for
  `qwen36-27b-instruct-maas`, `credentialsSecretRef` + `credentialKey`.
- `spec.ols.defaultProvider` / `defaultModel` set to that provider/model.
- `spec.ols.additionalCAConfigMapRef` for the MaaS gateway's serving CA (the CRD documents this
  field as CA trust "between OLS service and LLM Provider" - exactly this hop).

**Open item, narrowed 2026-08-26 (do not simply copy ai-gateway).** `credentialsSecretRef` takes
a **static Secret**, and neither of MaaS's two accepted credentials drops into that shape cleanly:

- *SA token* - the path this platform actually proved. `ai-gateway` mounts a **projected**
  ServiceAccount token (`audience: https://kubernetes.default.svc`, `expirationSeconds: 3600`),
  matching `AuthPolicy/maas-gateway-auth`'s `kubernetesTokenReview.audiences` exactly. WP-076 step
  3 made this the primary path. **Lightspeed's CRD cannot express a projected token** - there is no
  volume/projection field on `OLSConfig`, only `credentialsSecretRef`. Reproducing it means a
  long-lived `kubernetes.io/service-account-token` Secret, which is audience-less. Whether
  `TokenReview` accepts an audience-less legacy token when the policy requests an explicit audience
  must be **verified live against this cluster**, not assumed - it is the single fact this step
  turns on.
- *`sk-oai-*` API key* - fits `credentialsSecretRef` perfectly, but is currently **disabled
  platform-wide**: `gitops/charts/ai-gateway/values.yaml` sets `maasAdapter.apiKeyEnabled: false`
  and the Vault path `maas/gateway-api-key` is unseeded. That gate exists because of a live
  incident on 2026-08-26 - rendering the `ExternalSecret` against an unseeded Vault path leaves it
  permanently Degraded, and ArgoCD's wave-ordered sync then never reaches the Deployment, wedging
  the whole Application.

**Therefore:** decide by testing the legacy-token audience behaviour first, since it needs no new
secret material. If it works, use it. If it does not, mint and seed a real MaaS key **before**
rendering anything - and `gitops/charts/lightspeed-config` must replicate ai-gateway's
`apiKeyEnabled`-style gate so an unseeded path renders nothing rather than wedging the app.
Record which one won and why.

### Step 3 - Day 2: MCP front-door on the existing gateway

Add a standard MCP streamable-HTTP endpoint at `/mcp` to `components/mcp-gateway`, in the same
FastAPI app as `/v1/tools/{tool_name}/invoke`.

- `tools/list` returns the caller's **already-intersected** capability set - resolved through
  `app/policy.py` and `app/bindings.py`, never a hand-maintained list - so a caller entitled only
  to `confluence.page.search`/`.read` sees exactly two tools.
- `tools/call` routes into the same `evaluate()` -> `downstream.invoke()` path the REST endpoint
  uses. No second authorization path, no second binding registry.
- `gitops/charts/mcp-gateway`: NetworkPolicy gains a namespace-scoped ingress allow for
  `openshift-lightspeed` on 8080. Today it admits only `agent-runtime` and `acceptance-gate`
  pods.
- `OLSConfig.spec.featureGates: [MCPServer]` - **without this the whole `mcpServers[]` block is
  inert**; all feature gates are off by default on v1.1.2.
- `OLSConfig.spec.mcpServers[0]`: name `zuno-mcp`, `url`
  `http://mcp-gateway.zuno-ai-run.svc.cluster.local:8080/mcp`, a `timeout` well above the 5s
  default (the gateway's own `DOWNSTREAM_TIMEOUT_SECONDS` is 40s).
- Rebuild and redeploy `mcp-gateway`. **Push first** - the BuildConfig clones `origin/main`, not
  the local tree.

### Step 4 - Day 2: identity, both modes (ADR-0524 clause 5)

Both modes ship in this WP, service identity first so step 3 is provable end to end before the
harder path lands.

- *Service identity*: a `lightspeed` Keycloak client (client-credentials) in
  `gitops/charts/keycloak/files/realm-zuno.json` with a `groups` claim carrying a new read-only
  group; the token reaches Lightspeed as a Vault-seeded Secret referenced by
  `mcpServers[0].headers[0].valueFrom.type: secret`. No change to `auth.py`.
- *Per-user identity*: switch the header to `valueFrom.type: client` and add a second, additive
  branch to `components/mcp-gateway/app/auth.py` - when the bearer token is not a JWT, resolve it
  through the Kubernetes `TokenReview` API and map the returned OpenShift groups onto Keycloak
  groups before `evaluate()` runs. The Keycloak-JWT branch stays the primary path and is not
  modified; the new branch fails closed on any error.

**Verify before building the per-user branch:** that the Lightspeed console plugin actually
forwards the user's token for `type: client` on v1.1.2. If it does not, ship the service-identity
mode, mark the per-user half blocked in this WP with the evidence, and do not simulate it.

### Step 5 - Day 2: read-only Confluence

`policies/tools/tool-policy.yaml`: add the Lightspeed group to `allowed_groups` on
`confluence.page.search` and `confluence.page.read` **only**. Leave `.create` and `.update`
untouched. The `/mcp` front-door advertises only what that intersection permits, and
`spec.ols.toolsApprovalConfig` keeps its `tool_annotations` default. Three independent layers,
each sufficient on its own.

### Step 6 - Day 2/Day 3: native knowledge, introspection and operations

- Native OpenShift docs: **write nothing**. Leave `spec.ols.rag[]` empty and `byokRAGOnly` unset
  so the RHOKP sidecar keeps serving them.
- `spec.ols.introspectionEnabled`: leave at its `true` default (ADR-0524 clause 6).
- Day 3 `test`: add the Lightspeed API service to
  `ansible/roles/day3/tasks/platform_health_check.yml`, same shape as the `mcp-gateway`
  `/healthz`+`/readyz` pair.
- Day 3 `check`: `ansible/roles/lightspeed/tasks/precheck.yml` and
  `lightspeed_config/tasks/precheck.yml` assert CSV `Succeeded` and `OLSConfig` conditions
  healthy respectively; wire both into `ansible/playbooks/day3_check.yml`.
- Observability: the CSV sets `operatorframework.io/cluster-monitoring: true`, so operator
  metrics land in platform monitoring without extra work. Confirm before claiming it.
- Docs: `docs/platform/` component page and the ADR index row for ADR-0524.

## Verification checklist (operator step - ask before running)

- `make d1 install lightspeed`, then `oc get csv -n openshift-lightspeed` shows
  `lightspeed-operator.v1.1.2` `Succeeded` and `oc get crd olsconfigs.ols.openshift.io` exists.
- `make d2 build mcp` + `make d2 install mcp`, then `curl` the `/mcp` endpoint from an
  in-namespace debug pod and confirm `tools/list` returns exactly the read-only Confluence tools
  for the Lightspeed identity - and **404s or empty for a write capability**.
- `make d2 install lightspeed-config`, then `oc get olsconfig cluster -o
  jsonpath='{.status.conditions}'` reports healthy API/console-plugin/cache/MCP conditions.
- Browser verification as a real demo persona (see the Playwright method used for WP-061): open
  the console assistant and prove three answers - one from OpenShift documentation, one about
  live cluster state (introspection), one citing internal Confluence content.
- Negative test: ask Lightspeed to create or edit a Confluence page and confirm the gateway
  denies it, with the denial visible in `mcp-gateway` logs rather than only in the chat reply.
- `make d3 test platform` and `make d3 check lightspeed` both pass.

## Risks and known unknowns

1. **Console plugin token forwarding** (step 4) - the single largest unknown; gates the per-user
   half only, not the WP.
2. **MaaS credential shape** (step 2) - narrowed to one live test: does `TokenReview` accept an
   audience-less legacy SA-token Secret when the policy requests an explicit audience? Resolve
   early, it blocks every downstream step. Note the API-key alternative carries a known
   ArgoCD-wedging failure mode if rendered unseeded.
3. **MCP protocol conformance** - Lightspeed's client is stricter than `agent-runtime`'s REST
   caller. Test `tools/list`/`tools/call` against the real Lightspeed pod, not only against
   `components/mcp-gateway/tests`.
4. **Operator-managed PostgreSQL** - Lightspeed brings its own; do not attempt to point it at the
   PGO cluster, the CRD has no field for it.

## Status updates (once live-verified)

- ADR-0524 moves to `Implemented` only when steps 1-6 are all live-verified. If step 4's per-user
  half is blocked by the console plugin, ADR-0524 stays `Partially implemented` with the blocking
  evidence recorded here.
