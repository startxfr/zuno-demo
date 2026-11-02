# WP-181: Install Open WebUI on demo333

- **State:** Not started
- **ADRs:** [ADR-0588](../../adr/0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
- **Depends on:** [WP-179](wp-179-common-preparation-for-experience-clients.md), [WP-180](wp-180-open-webui-preparation.md)
- **Related:** [WP-183](wp-183-install-openclaw-on-demo333.md), [WP-184](wp-184-three-experiences-demonstration.md)
- **Target:** v0.13
- **Estimated files touched:** ~10, all in the track's own directories (`gitops/charts/open-webui/`, `gitops/apps/open-webui/`, `ansible/roles/open_webui/`), plus one Keycloak client in `realm-zuno.json` and, if WP-180 says so, `components/open-webui-relay/`

> Track Open WebUI. Follow WP-179's coordination protocol: own directories only; shared files by request to the other
> session; every cluster action after the user's go in this session.

## Steps

1. **Chart** `gitops/charts/open-webui`: the official chart as a pinned dependency, image by digest, values from WP-180
   (SCC, volume, switches off, OIDC, one OpenAI connection to the ai-gateway, one MCP connection to the mcp-gateway).
   Secrets (`WEBUI_SECRET_KEY`, OIDC client secret) through ExternalSecrets from Vault.
2. **Applications** `gitops/apps/open-webui/application-d{0,1}.yaml` following the UnifAI pair.
3. **Role** `ansible/roles/open_webui` replaces WP-179's stub: Vault seed of missing paths, Keycloak client reconcile with
   WP-179's pattern, Application apply, wait, and `check` (pod Ready, Route answers, OIDC discovery reachable).
4. **Relay** (only if WP-180 requires it): `components/open-webui-relay`, built and signed in-cluster like any zuno
   component, deployed by the same chart.
5. **Mcp-gateway entitlement** for the logical agent `open-webui`: request it from the owner of the agents and corp
   policies (`zuno-demo-agents`), as any agent entitlement; no local override.
6. **Install** on demo333 with `make d2 install open-webui` (user's go), then `make d2 check open-webui`.

## Acceptance (live, demo333)

- A persona logs in through Keycloak; local sign-up is refused.
- The model list equals the ai-gateway's `/v1/models` for that persona.
- A chat produces `zuno_model_tokens{client="open-webui",user=<persona>}` in **raw Prometheus**.
- A tool the persona is entitled to works; a tool they are not entitled to is refused by the mcp-gateway.
- A blocking prompt raises `zuno_guardrails_*` with `client="open-webui"`.
- An HTTP request from the Open WebUI pod to the internet fails.
- No shared key appears in the chart, the Secret or the pod environment.
