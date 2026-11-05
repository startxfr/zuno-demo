# WP-207: kagent chart study (2026-11-05, offline) and live spike

## 1. Offline study (done, no cluster)

`helm pull` of `oci://ghcr.io/kagent-dev/kagent/helm/{kagent,kagent-crds}` **0.10.4** (v0.10.5 and 1.0.0-rc are
under two weeks old). Rendered with the values of `gitops/charts/kagent`:

| Question | Finding |
|---|---|
| CRDs scope | all eight are `Namespaced` (agents, memories, modelconfigs, remotemcpservers, sandboxagents, toolservers, agentharnesses, modelproviderconfigs) |
| Controller RBAC | with `controller.watchNamespaces` and `rbac.namespaces` set to the install namespace the chart renders **two Roles and two RoleBindings, no ClusterRole** |
| Bundled pieces | `kmcp`, `substrate`, `kagent-tools`, `grafana-mcp`, `oauth2-proxy` and the ten sample agents are dependency conditions, all switched off; `providers: null` renders no ModelConfig |
| Database | `database.postgres.urlFile` reads the URL from a mounted file; the bundled PostgreSQL (`runAsUser 999`, refused by `restricted-v2`) is off |
| UI | Route owned by the chart (`ui.route.enabled`) switched off; our oauth2-proxy front door is the only Route. Controller `auth.mode: unsecure`, so the UI has no login of its own |
| Ports | UI 8080, controller (REST and A2A) 8083 |
| Declarative agent | `Agent` `spec.type: Declarative`, `declarative.{modelConfig, systemMessage, tools[].mcpServer{name,kind,toolNames}, a2aConfig.skills}` |

Images, index digests (2026-10-21): controller `sha256:e284fbdd…`, ui `sha256:a6edf70c…`, agent runtime `app`
`sha256:b811b0dd…`, `golang-adk` `sha256:89d5a7df…`, `skills-init` `sha256:5be7cb94…` (the last three are used by the
controller to start the agents; the controller and ui are pinned by tag and digest in the chart values).

## 2. Open until the live install

- The controller starting with `providers: null` and no default ModelConfig.
- The agent runtime image (`app`) under `restricted-v2` with an arbitrary UID, and its egress to the token proxy.
- Whether the network policy and EgressFirewall let the controller reach the API server (control-plane addresses on 6443).
- The `persona` ai-ops-01 against the ai-gateway quota and the MaaS subscription (fallback: consultant-02).
- `zuno-sre` answering from mcp-gateway tools only (`agent=kagent`, `capability=k8s.*`), with `zuno_model_tokens{client="kagent"}`.
