# ADR-0600: Govern Kubernetes read tools in the mcp-gateway and admit kagent as a thin operations client

- **Status:** Implemented
- **Target:** v0.14
- **Date:** 2026-11-04
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0524](0524-integrate-openshift-lightspeed-with-the-zuno-ai-platform.md), [ADR-0592](0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md), [ADR-0409](0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md), [ADR-0601](0601-inject-client-credentials-tokens-for-experience-clients-without-oidc-passthrough.md)

## Context

The platform has no governed tool that reads the cluster. The only cluster-introspection MCP is OpenShift Lightspeed's
operator-managed `openshift-mcp-server`, which runs on the user's own RBAC and is explicitly not a Zuno deployment
(ADR-0524 clause 6). The AAP audit tools are the closest thing to operations tooling.

kagent (CNCF sandbox, 0.10.3, 1.0 in alpha) is a Kubernetes operator for agents. It installs from
`oci://ghcr.io/kagent-dev/kagent/helm/{kagent-crds,kagent}` and declares `kagent.dev/v1alpha2` resources:

- `ModelConfig`: an OpenAI provider with `openAI.baseUrl`, `apiKeySecret` or `apiKeyPassthrough`, `defaultHeaders`, and
  `tls.caCertSecretRef`;
- `RemoteMCPServer`: `url`, `STREAMABLE_HTTP`, `headersFrom` a Secret or ConfigMap;
- `Agent`: `Declarative` (system message, model, tools) or `BYO`. Each tool reference can list `requireApproval` tool
  names. Agents are served over A2A by the controller.

kagent ships its own tool servers (Kubernetes, Helm, Prometheus, Istio, Argo), which run with the operator's own RBAC.
Installed as the vendor intends, kagent would be a second agent platform with ungoverned, cluster-wide tools. That
contradicts ADR-0587 clause 4 and the five-factor check.

## Decision

**The value kagent brings, reading the cluster, becomes a governed mcp-gateway capability that every client can use.
kagent itself is admitted only as a thin operations experience over those tools.**

1. **Capabilities.** The tool policy (`zuno-demo-agents/policies/tools/tool-policy.yaml`) gains `k8s.resource.read`
   (get and list), `k8s.events.read`, `k8s.logs.read` and `metrics.query` (PromQL through Thanos Querier), all
   `access: read`. There are no write capabilities in v0.14. `Secret` and `ConfigMap` data are never returned.
2. **Backend.** One MCP server `zuno-mcp-k8s` behind the mcp-gateway, like the other servers in `components/mcp-servers/`.
   WP-206 picks the implementation: `kubernetes-mcp-server` in `--read-only` mode (the server Lightspeed builds on) or
   kagent's tool server. It runs under its own ServiceAccount with `view` plus `cluster-monitoring-view`, an explicit deny
   on Secrets, and a namespace scope fixed in WP-206 (the `zuno-*` namespaces by default).
3. **Entitlement.** The tools are granted to the platform-operations groups only, through task declarations in the
   agents release. UnifAI agents and Open WebUI can then use them under the same five factors.
4. **kagent as a client.** kagent installs with `providers: null` and its bundled tool servers and agents disabled.
   Namespace `zuno-kagent` carries the experience-client label. A single `ModelConfig` points at the `zuno-token-proxy`
   (ADR-0601) in front of the ai-gateway, and a single `RemoteMCPServer` at the proxy in front of the mcp-gateway `/mcp`.
   Its declarative Agents are prompts over those tools, declared in the agents release as experience client `kagent`
   (ADR-0592), with a `diagnose` task.
5. **No platform role.** kagent agents are not UnifAI delegates and hold no OKF bundle. Their A2A endpoint is reachable
   only from the kagent UI (NetworkPolicy). The UI sits behind oauth2-proxy for the operations group.
6. **No writes until approval exists.** `requireApproval` is not a substitute for ADR-0409. Write tools (patch, scale,
   delete) wait for that ADR and WP-173 and for a new decision.

## Correction note to ADR-0587

ADR-0587 clause 4 ("UnifAI stays the agent platform; the other experiences call no agent") stays true. kagent's
declarative Agents are an experience surface over governed tools, like an Open WebUI model preset: no bundle, no
delegation, no entry of their own. ADR-0587 carries a dated correction note pointing here. It is not superseded.

## Alternatives considered

- **kagent as shipped, with its own tool servers and RBAC:** the guide's demo, but cluster access outside the gateway,
  outside audit and outside classification. Rejected.
- **kagent as a UnifAI delegate over A2A:** needs an OKF bundle type for external A2A agents and a non-local `base_url`
  in the a2a-gateway. Out of scope. Rejected for v0.14.
- **No kagent, only the new tools:** the governed tools are the lasting value, so this is the fallback if WP-207 finds
  kagent cannot run as a thin client. Kept as the fallback.

## Consequences

- Every experience gains a cluster-reading tool, audited and entitled like Confluence or Salesforce.
- kagent shows the Kubernetes-native style (agents as CRDs) without a second governance plane.
- kagent's CRDs are cluster-scoped and its controller may want cluster-wide RBAC. WP-207 reduces both or records why
  not.

## Security considerations

The cluster-reading identity is the `zuno-mcp-k8s` ServiceAccount, not the caller's. The mcp-gateway decides who may
call it, and the ServiceAccount's RBAC bounds what it can see. Logs may contain secrets printed by applications, so
`k8s.logs.read` is limited to the operations groups and its results are marked C2.

## Operational considerations

mcp-gateway audit lines with `capability=k8s.*` and `agent=kagent` show use, and a refused Secret read is part of the
WP-206 acceptance. `zuno_model_tokens{client="kagent"}` proves the model path.

## Implementation note (2026-11-05, WP-206)

The binding registry maps one capability to one backend tool, so `k8s.resource.read` (get) is paired with
`k8s.resource.list` (list). The backend is the upstream `kubernetes-mcp-server` v0.0.69 pinned by digest, in
`read_only` mode with an `enabled_tools` allowlist and Secret and ConfigMap denied by kind. `metrics.query`
needs `cluster-monitoring-view` (the namespaced Thanos port is unusable), so it reads the metrics of the whole
cluster, which the user accepted. The entitled groups were `ocp-ai-ops` and `aap_ops` (narrowed to `ocp-ai-ops` on 2026-11-06, see the amendment below). Evidence:
[wp-206-k8s-mcp-spike](../roadmap/evidence/wp-206-k8s-mcp-spike.md).

## Amendment (2026-11-06): UnifAI reaches the tools, operations group only

Tekos (`answer-technical-question`, agents 0.14.0) declares the five `k8s.*` capabilities. The policy entries now admit
`ocp-ai-ops` alone: `aap_ops` is also held by the consultant personas and the Dify and OpenClaw service accounts, and
cluster logs are C2. Verified live with ai-ops-01 (one `k8s.events.read`, allowed) and consultant-02 (no `k8s.*` call).
Arkos declares none. Evidence: [WP-208](../roadmap/work-packages/wp-208-five-experiences-demonstration.md).
