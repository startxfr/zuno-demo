# WP-183: Install OpenClaw on demo333

- **State:** Not started
- **ADRs:** [ADR-0589](../../adr/0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md), [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
- **Depends on:** [WP-179](wp-179-common-preparation-for-experience-clients.md), [WP-182](wp-182-openclaw-preparation.md)
- **Related:** [WP-181](wp-181-install-open-webui-on-demo333.md), [WP-184](wp-184-three-experiences-demonstration.md)
- **Target:** v0.13
- **Estimated files touched:** ~12, all in the track's own directories (`gitops/charts/openclaw/`, `gitops/apps/openclaw/`, `ansible/roles/openclaw/`, `components/claw-token-proxy/` if WP-182 requires it), plus one Keycloak client per persona in `realm-zuno.json`

> Track OpenClaw. Follow WP-179's coordination protocol: own directories only; shared files by request to the other
> session; every cluster action after the user's go in this session.

## Steps

1. **Chart** `gitops/charts/openclaw`: CatalogSource pinned by digest, Subscription with manual approval, one `Claw` per
   persona with the values of WP-182 (provider `zuno` to the ai-gateway, MCP to the mcp-gateway, ClawHub and channels
   off, egress allowlist, namespace label). On the fallback path, one `openclaw-kube` release per persona instead.
2. **Applications** `gitops/apps/openclaw/application-d{0,1}.yaml`.
3. **Identity.** One confidential client `openclaw-<persona>` per persona (client-credentials, service-account user in the
   persona's groups), added with WP-179's Keycloak pattern; secrets in Vault, delivered by ExternalSecrets.
4. **Token proxy** (if WP-182 requires it): `components/claw-token-proxy`, built and signed in-cluster, injected as the
   egress path of each assistant.
5. **Front door.** oauth2-proxy per assistant (Keycloak `zuno`), OpenClaw trusted-proxy with `allowUsers` = the persona;
   one Route each with an ACME certificate.
6. **Role** `ansible/roles/openclaw` replaces WP-179's stub: catalog pin check, Vault seed of missing paths, clients
   reconcile, Application apply, wait, and `check` (each `Claw` Ready, Control UI behind the proxy, no ClawHub).
7. **Mcp-gateway entitlement** for the logical agent `openclaw`: request it from the owner of `zuno-demo-agents`.
8. **Install** with `make d2 install openclaw` (user's go), then `make d2 check openclaw`.

## Acceptance (live, demo333)

- The persona reaches its Control UI through Keycloak; another persona is refused.
- A request from the assistant produces `zuno_model_tokens{client="openclaw-<persona>"}` in **raw Prometheus**.
- A request to the ai-gateway from the assistant's pod **without** the proxy gets 401.
- An HTTP request from the assistant's pod to the internet fails.
- Installing a ClawHub skill is refused.
- An entitled tool works through the mcp-gateway; a non-entitled one is refused.
