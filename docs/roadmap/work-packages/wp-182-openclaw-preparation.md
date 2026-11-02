# WP-182: OpenClaw preparation

- **State:** Not started
- **ADRs:** [ADR-0589](../../adr/0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md), [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
- **Depends on:** [WP-179](wp-179-common-preparation-for-experience-clients.md) (its interfaces only; this spike can start once they are written)
- **Related:** [WP-183](wp-183-install-openclaw-on-demo333.md), [WP-180](wp-180-open-webui-preparation.md)
- **Target:** v0.13
- **Estimated files touched:** one evidence file `docs/roadmap/evidence/wp-182-openclaw-spike.md`; no shared file

> Track OpenClaw. Runs in parallel with WP-180 under WP-179's coordination protocol. No cluster action except, with the
> user's go, a throw-away install in a scratch namespace that is removed afterwards.

## Goal

Decide, from claw-operator's source and a scratch run, whether ADR-0589 is built on the operator or on the
`openclaw-kube` fallback, and fix every value WP-183 needs.

## Steps

1. **Operator and pins.** Read `codeready-toolchain/claw-operator` (and `redhat-et/claw-project`, to know which is
   authoritative): the `Claw` CRD fields, the namespaces it creates and their labels, RBAC it requests (cluster-wide?),
   the catalog image, its digest, the OpenClaw image and its digest. Note the commit read.
2. **Custom provider.** Can a `Claw` declare a custom `openai-completions` provider whose `baseUrl` is an in-cluster
   service (the ai-gateway), with only the models of `platform/ai-gateway/provider-routing.yaml`?
3. **Credential proxy.** Can its proxy inject a **refreshable** credential (client-credentials token from Keycloak) and
   extra headers (`X-Zuno-Agent: openclaw`) for in-cluster destinations? If not, specify the first-party sidecar
   `components/claw-token-proxy` (interface, refresh, failure mode: refuse, never pass through without a token).
4. **Egress.** Can its allowlist name in-cluster services and deny the internet? Can the operator-created namespaces carry
   `zuno.io/experience-client: "true"` (CR field, or a namespace template), so WP-179's ingress applies?
5. **Lockdown.** The settings that disable ClawHub and community skills and every messaging channel; whether they can be
   enforced from the CR or only from `openclaw.json`.
6. **Front door.** oauth2-proxy in front of the Control UI with OpenClaw in trusted-proxy mode and `allowUsers`; whether the
   operator's Route can be replaced or fronted.
7. **MCP.** OpenClaw's MCP client against the mcp-gateway `/mcp` from the scratch instance: `tools/list` returns only the
   persona's tools.
8. **Decision.** Operator or fallback, written with the reasons; the list of personas (2 or 3) and their groups.

## Acceptance

The evidence file answers steps 1 to 8 with sources and test output, records the decision of step 8, and lists every
value WP-183 will set. The scratch namespace is gone.
