# WP-181: Install Open WebUI on demo333

- **State:** Repo work in review (2026-11-02: chart, Application, role and Keycloak client in the repository; the install on demo333 and the agent entitlement remain)
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

## Implementation notes (2026-11-02)

- **Shared files, one commit** (`bba139b7`, announced to the OpenClaw track, which appends after it): client `open-webui`
  in `realm-zuno.json` (shape of `unifai`, callback `/oauth/oidc/callback`, mappers `groups`, `audience-self`,
  `maas-gateway-audience`), group `openwebui_admin` with `ai-ops-01` and `paas-ops-01`, `externalsecret-open-webui-client.yaml`,
  the `vault-secrets` item `zuno_open__webui__client__secret`, the vault role seed of `keycloak/open-webui`.
- **Chart** `gitops/charts/open-webui`: upstream `open-webui` 17.5.0 as a dependency, image by digest, values of the
  WP-180 evidence. The upstream default `openaiApiKey` is a shared key: it is set empty, so no `OPENAI_API_KEY` is rendered.
  Own templates: two ExternalSecrets (`open-webui-oidc` from `keycloak/open-webui`, `open-webui-app` from
  `open-webui/app`), the Route (edge, wildcard ACME certificate, timeout 5m), an egress NetworkPolicy (DNS, the gateways
  on 8080, the router on 443).
- **Keycloak through the router.** The gateways accept only the public https issuer, and the egress policy closes the
  internet: the role adds a `hostAliases` entry mapping `keycloak.<apps domain>` to the ClusterIP of
  `openshift-ingress/router-internal-default`, so the sign-in and the token refresh go through the in-cluster router.
- **Role** `ansible/roles/open_webui`: install seeds the missing Vault paths (`seed_vault.yml`), creates the group
  `openwebui_admin` and its members live (`keycloak_admin_group.yml`, create-only), applies `zuno-open-webui-d1`, waits
  for the Deployment. `precheck.yml` is the `make d2 check open-webui` (HTTP probes from the pod: Keycloak 200, both
  gateways 401 without a token, internet unreachable; Route `/health` 200).
- **Model list.** The ai-gateway's `/v1/models` is filtered by classification, not per user: the acceptance below
  reads "the model list equals the ai-gateway's `/v1/models`" (WP-180 section 2).
