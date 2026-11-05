# WP-206: Kubernetes read tools behind the mcp-gateway

- **State:** Repo work in review
- **ADRs:** [ADR-0600](../../adr/0600-govern-kubernetes-read-tools-in-the-mcp-gateway-and-admit-kagent-as-a-thin-operations-client.md)
- **Depends on:** none (its spike part can start at once; the install waits for the end of the demo333 upgrade)
- **Related:** [WP-207](wp-207-kagent-preparation-and-install.md), [WP-202](wp-202-common-preparation-for-dify-and-kagent.md)
- **Target:** v0.14
- **Estimated files touched:** `components/mcp-servers/k8s` (or a pinned upstream image), its chart, the mcp-gateway backend registration, `zuno-demo-agents/policies/tools/tool-policy.yaml`, evidence `docs/roadmap/evidence/wp-206-k8s-mcp-spike.md`

## Goal

`k8s.resource.read`, `k8s.events.read`, `k8s.logs.read` and `metrics.query` are mcp-gateway capabilities, read-only,
entitled to the operations groups.

## Steps

1. **Pick the server** (spike, scratch namespace `zuno-k8smcp-scratch`): `kubernetes-mcp-server --read-only` against
   kagent's tool server. Record the tool list, whether read-only holds when the RBAC would allow writes, whether Secret
   data can leak (`resources_get` on a Secret, `pods_exec`), image digests and licences.
2. **ServiceAccount and RBAC.** `view` plus `cluster-monitoring-view`, Secrets not readable, scope: the `zuno-*`
   namespaces (RoleBindings) unless the spike shows a cluster-wide read is needed.
3. **Backend.** Register the server with the mcp-gateway as the other servers in `components/mcp-servers/` are; map its
   tools onto the four capabilities; drop every other tool.
4. **Policy.** The four capabilities in `tool-policy.yaml` (`access: read`, logs marked C2); a task in the agents
   release that grants them to the operations groups.
5. **Proof.** A five-factor call from an operations persona token through `/mcp` lists pods of `zuno-ai-run`; the
   same call from a business persona is refused; a Secret read is refused.

## Acceptance

Step 5 passes live and is recorded in the evidence file; the scratch namespace is gone.
