# ADR-0524: Integrate OpenShift Lightspeed as a consumer of the Zuno AI platform

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-26
- **Decision owners:** Zuno Demo architecture team

## Context

OpenShift Lightspeed gives the OpenShift web console a native conversational assistant. Zuno
already owns every backing capability it needs - local inference (ADR-0019, ADR-0521), an MCP
authorization plane (ADR-0010, ADR-0011, ADR-0036), a real Confluence MCP server (ADR-0117),
Keycloak identity (ADR-0012), and the Day 0-3 deployment sequencing (ADR-0060). The integration
is therefore about *consuming* those, not about growing a parallel stack beside them.

Confirmed live against this cluster on 2026-08-26 (`oc get packagemanifest lightspeed-operator
-n openshift-marketplace`, plus the v1.1.2 bundle's own `ols.openshift.io_olsconfigs.yaml`
extracted from `registry.redhat.io/openshift-lightspeed/lightspeed-operator-bundle`):

- Package `lightspeed-operator`, catalog `redhat-operators`, `defaultChannel: stable`, current
  CSV `lightspeed-operator.v1.1.2`. **Not installed** - no `olsconfigs.ols.openshift.io` CRD and
  no `openshift-lightspeed` namespace exist yet. (`ansiblelightspeeds.lightspeed.ansible.com` is
  AAP's CRD from ADR-0354, unrelated.)
- InstallModes: **`OwnNamespace` only** - no `AllNamespaces`. Same posture as `rhbk-operator` and
  `ansible-automation-platform-operator`: a dedicated namespace with its own OperatorGroup, never
  the shared `openshift-operators`. Suggested namespace `openshift-lightspeed`.
- `operators.openshift.io/valid-subscription: ["OpenShift Container Platform", ...]` - covered by
  the cluster's existing entitlement, no additional SKU. FIPS-compliant and disconnected-capable.
- Owned CRD `OLSConfig` `v1alpha1`, a cluster singleton named `cluster`.
- `spec.llm.providers[].type` accepts **`rhoai_vllm`** - the local-inference path this platform
  already serves.
- `spec.mcpServers[]` exists, accepts **HTTP/HTTPS transport only**, and is inert unless
  `spec.featureGates` contains `MCPServer` (enum `[MCPServer, ToolFiltering]`, all gates off by
  default). Per-server auth is `headers[].valueFrom.type`, one of `secret` (a Secret in the
  operator's own namespace), `kubernetes` (Lightspeed's ServiceAccount token) or `client` (the
  console user's own OpenShift token).
- `spec.ols.rag[]` is BYOK-only (container images carrying FAISS indexes). Official OpenShift
  documentation is served by the operator's own RHOKP sidecar and stays on unless
  `spec.ols.byokRAGOnly: true`.
- `spec.ols.introspectionEnabled` **defaults to true**, which makes the operator deploy its own
  `openshift-mcp-server` for live cluster introspection.
- `spec.ols.conversationCache.type` accepts `postgres` only, backed by an operator-deployed
  `rhel9/postgresql-16` in its own namespace. The CRD exposes no external-database reference.

Three facts on the Zuno side constrain the design and were verified in-repo:

1. **The MCP Gateway is not an MCP server.** `components/mcp-gateway/app/main.py` exposes
   `POST /v1/tools/{tool_name}/invoke`, a bespoke REST contract. It speaks MCP *downstream* only
   (`app/downstream.py`, `streamable_http_client` to `confluence-mcp`). ADR-0043's "standard MCP
   protocol" applies to the gateway's south side, never its north side. Lightspeed cannot consume
   it as-is.
2. **Lightspeed cannot mint a Keycloak JWT.** `components/mcp-gateway/app/auth.py` validates an
   RS256 Keycloak token against the realm JWKS and reads its `groups` claim, with no bypass under
   any configuration. None of Lightspeed's three header sources produces such a token: the console
   user's OpenShift token is an opaque `sha256~` string, not a JWT, even though OpenShift's OAuth
   is federated to Keycloak (ADR-0346/ADR-0347).
3. **Read-only is already expressible.** `policies/tools/tool-policy.yaml` carries
   `confluence.page.search`, `.read`, `.create` and `.update` as four independent
   policy-intersection entries with their own `allowed_groups` - ADR-0117's "read access never
   implies write access" is a property of the existing policy model, not something to build.

## Decision

Integrate OpenShift Lightspeed as a **consumer** of the Zuno AI platform, under seven clauses.

**1. Local inference through MaaS.** A single `rhoai_vllm` provider pointed at the MaaS gateway
(`https://maas-default-gateway-istio.openshift-ingress.svc/zuno-ai-run/<published-model>/v1`),
not at a KServe predictor Service and not through `ai-gateway`. This follows ADR-0521: MaaS is
the transport for local model traffic. Lightspeed becomes a first-class MaaS tenant with its own
`MaaSSubscription` + `MaaSAuthPolicy` subject declared in `gitops/charts/models/values.yaml`,
mirroring the existing `*-ai-gateway` entries, so its consumption is entitled, rate-limited and
attributable rather than anonymous. The MaaS gateway's serving CA is trusted through
`spec.ols.additionalCAConfigMapRef`.

**2. Native OpenShift knowledge, untouched.** `spec.ols.rag[]` stays empty and
`spec.ols.byokRAGOnly` stays unset, so the operator's RHOKP sidecar keeps serving official,
version-matched OpenShift documentation. Zuno builds no OpenShift-documentation ingestion
pipeline and no pgvector corpus for it.

**3. Internal knowledge through the existing MCP Gateway, via a new MCP front-door on it.**
`components/mcp-gateway` gains a standard MCP streamable-HTTP endpoint (`/mcp`) served by the
**same deployment, same process and same policy path** as the existing REST contract. No new
workload is deployed for this. Lightspeed registers exactly one entry in `spec.mcpServers[]`
pointing at that endpoint, with `spec.featureGates: [MCPServer]` set. `tools/list` over `/mcp`
advertises only what the caller's policy intersection already permits, so the tool surface is
derived from `policies/tools/tool-policy.yaml`, never hand-listed.

**4. Read-only Confluence, enforced in three independent places.** The Lightspeed identity is
granted a group that appears only on `confluence.page.search` and `confluence.page.read` in
`policies/tools/tool-policy.yaml`; the `/mcp` front-door advertises only read capabilities; and
`spec.ols.toolsApprovalConfig` keeps its `tool_annotations` default. A write attempt therefore
fails closed at the gateway even if the first two layers were misconfigured.

**5. Two identity modes, service-level and per-user.** Lightspeed's MCP calls carry identity in
one of two ways, both delivered together:
- *Service identity* - a dedicated Keycloak `lightspeed` client (client-credentials) whose token
  carries a read-only group, supplied as `headers[].valueFrom.type: secret`. Works with no change
  to `auth.py`, and is the fallback whenever a per-user token is absent.
- *Per-user identity* - `headers[].valueFrom.type: client` forwards the console user's own
  OpenShift token; `mcp-gateway` gains a **second, additive** authentication path that resolves
  such a token through the Kubernetes `TokenReview` API and maps the resulting OpenShift groups
  onto Keycloak groups before ADR-0011's intersection runs.

  The Keycloak-JWT path remains the primary and unchanged one; the `TokenReview` path is
  additive and fails closed. This preserves ADR-0032/ADR-0033 - identity is still derived only
  from a validated token, never from request content - while giving real per-user authorization
  when the console forwards a user token.

**6. Introspection stays enabled.** `spec.ols.introspectionEnabled` keeps its `true` default, so
the operator's own `openshift-mcp-server` answers live questions about this cluster. That server
is operator-managed, scoped by the querying user's own RBAC, and is the OpenShift-native half of
Lightspeed's value. It is explicitly **not** a Zuno MCP deployment and does not duplicate the MCP
Gateway: it serves cluster introspection, the Gateway serves enterprise knowledge.

**7. Split across Day 1 and Day 2, as two components.** The operator (`lightspeed`) installs in
Day 1 with no dependency beyond OLM. Its configuration (`lightspeed-config`) runs **last in Day
2**, after `models` (MaaS entitlement), `mcp` (the `/mcp` front-door and the NetworkPolicy
allowing Lightspeed in) and `agents`. Two Ansible roles and **two Helm charts**, one per
component - the same shape `aap`/`aap-config` already uses (ADR-0354, WP-072/WP-073). Each chart
is rendered by the repository's standard **two** Applications, `-d0` (namespace + operator) and
`-d1` (operand), whose value gates keep their rendered resource sets disjoint; `lightspeed`'s
`-d1` points at `gitops/charts/noop`, since its operand is `lightspeed-config`'s job in Day 2.
The split is by component lifecycle and day tier, not by any ArgoCD limitation - `aap` proves one
chart serves two Applications cleanly.

Tracked by WP-085.

## Non-goals

This decision does **not** introduce: a Zuno-built MCP server or deployment dedicated to
Lightspeed (clause 3 adds an endpoint to an existing component; clause 6's introspection server
is the operator's own, not Zuno's); an OpenShift-documentation ingestion pipeline; a pgvector
corpus for official OpenShift documentation; any Confluence write capability; or a replacement
for the Lightspeed console plugin or conversational backend.

## Target architecture

```text
OpenShift Console  --(console plugin)-->  Lightspeed (openshift-lightspeed)
                                             |
      +--------------------------------------+----------------------------------+
      |                       |                                  |
      v                       v                                  v
 MaaS gateway          RHOKP sidecar +                     mcp-gateway /mcp
 (rhoai_vllm)          openshift-mcp-server                (zuno-ai-run, existing)
      |                (operator-managed)                        |
      v                                                   ADR-0011 intersection
 qwen3.6-27b-instruct                                             |
 (zuno-ai-run, KServe)                                            v
                                                            confluence-mcp
                                                          search / read ONLY
```

## Operational considerations

Verification is condition-driven. `oc get olsconfig cluster -o
jsonpath='{.status.conditions}'` must report the API, console-plugin, cache and (once clause 3
lands) MCP-server conditions healthy before this ADR moves past `Proposed`. Lightspeed's own
PostgreSQL is operator-managed inside `openshift-lightspeed` and is **not** a PGO cluster
(ADR-0015): the CRD offers no external-database reference on v1.1.2, so this is an accepted
deviation, not an oversight, and it is deliberately excluded from Day 3's pgBackRest
backup/restore scope - conversation cache is disposable state.

`openshift-lightspeed` is created by `gitops/charts/lightspeed`'s own vendored `project`
subchart, following `lws` and `custom-metrics-autoscaler` - `gitops/charts/namespaces` owns only
`zuno-*` namespaces, never `openshift-*` operator ones. It is **not** mesh-injected: Lightspeed's Deployments are operator-owned, and injecting a sidecar into them
would put the platform in the business of patching a Red Hat operand. Reachability into
`zuno-ai-run` is therefore a NetworkPolicy question only - `mcp-gateway`'s policy today admits
only `agent-runtime` and `acceptance-gate` pods and must gain a namespace-scoped allow.

Day 3 gains Lightspeed coverage on both existing verbs: `platform_health_check.yml` probes the
Lightspeed API service the same way it probes `mcp-gateway`, and `make d3 check lightspeed`
delegates to the component's own `precheck.yml`.

## Migration / evolution

Clause 5's `TokenReview` path deliberately does not decide how OpenShift users map onto Keycloak
groups beyond what WP-085 needs for the read-only Confluence case. Extending that mapping to the
full business-role model (ADR-0040, ADR-0340) is a separate decision. Likewise, this ADR does not
decide whether Zuno's own agent frontends should eventually be reachable from the console, nor
whether Lightspeed should ever consume Zuno's RAG corpora directly through `spec.ols.rag[]` -
both would need their own records.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0010](0010-introduce-a-central-mcp-gateway.md), [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md),
  [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md) - the
  authorization plane clause 3 routes Lightspeed through instead of around.
- [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md) - established MCP as
  the gateway's south-side protocol; clause 3 extends the same protocol to its north side.
- [ADR-0117](0117-implement-confluence-as-the-first-real-external-mcp-integration.md) - the
  Confluence MCP server and its read-never-implies-write property clause 4 relies on.
- [ADR-0521](0521-route-local-model-traffic-through-maas.md) - the MaaS transport decision
  clause 1 follows; [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md) for
  the underlying serving stack.
- [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md),
  [ADR-0032](0032-propagate-trusted-identity-end-to-end.md),
  [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md) - the identity invariants
  clause 5 extends without weakening.
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md) - the
  network/workload boundary the new NetworkPolicy allow must respect.
- [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md) and
  [ADR-0354](0354-add-ansible-automation-platform-as-a-day-1-component.md) - the day sequencing
  and the two-component `aap`/`aap-config` precedent clause 7 mirrors.
