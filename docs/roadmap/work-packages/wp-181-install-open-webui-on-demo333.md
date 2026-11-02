# WP-181: Install Open WebUI on demo333

- **State:** Done (2026-11-02: installed on demo333, chain, tools and guardrails proven live; guardrails stay in observe mode, user decision)
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
  `open-webui/app`), the Route (edge, wildcard ACME certificate, timeout 5m), an egress NetworkPolicy and an EgressFirewall
  (below).
- **Keycloak egress.** The gateways accept only the public https issuer, so Open WebUI reaches Keycloak through the
  external load balancer. A first design mapped the Keycloak hostname to the in-cluster router
  (`router-internal-default`): the TLS handshake was reset, because the AWS router expects the PROXY protocol
  (`ROUTER_USE_PROXY_PROTOCOL=true`) that only the load balancer adds. Final design: the NetworkPolicy admits HTTPS out
  of the pod and Service networks, and an OVN `EgressFirewall` allows only `keycloak.<apps domain>`:443 and denies
  every other external destination.
- **Role** `ansible/roles/open_webui`: install seeds the missing Vault paths (`seed_vault.yml`), creates the group
  `openwebui_admin` and its members live (`keycloak_admin_group.yml`, create-only), applies `zuno-open-webui-d1`, waits
  for the Deployment. `precheck.yml` is the `make d2 check open-webui` (HTTP probes from the pod: Keycloak 200, both
  gateways 401 without a token, internet unreachable; Route `/health` 200).
- **Model list.** The ai-gateway's `/v1/models` is filtered by classification, not per user: the acceptance below
  reads "the model list equals the ai-gateway's `/v1/models`" (WP-180 section 2).

## Live results (demo333, 2026-11-02)

- `make d2 install open-webui`: Vault `open-webui/app` seeded (`keycloak/open-webui` was already seeded by the vault
  role), group `openwebui_admin` created with `ai-ops-01` and `paas-ops-01`, `zuno-open-webui-d1` Synced and Healthy.
  The OIDC client secret is identical on both sides (Open WebUI and Keycloak's KC_VAULT file, compared by hash).
- `make d2 check open-webui`: Keycloak discovery 200 through the EgressFirewall, ai-gateway and mcp-gateway 401 without
  a token, `https://huggingface.co` unreachable (000), Route `/health` 200.
- Browser sign-in (Playwright): `ai-ops-01` gets role `admin`, `consultant-02` role `user`; sign-up and password
  sign-in refused (403); 11 models listed.
- Raw Prometheus (thanos-querier): `zuno_model_calls_total{client="open-webui",provider="openai",outcome="success"}`
  for `consultant-02`, `zuno_model_tokens_total{client="open-webui"}` 160, and
  `zuno_guardrails_evaluations_total{client="open-webui",outcome="clean"}` (guardrails in observe mode, agent
  `open-webui`).
- MCP tools (WP-189, agents v0.9.0): `consultant-02` and `sale-01` get `drive.document.search`, `gmail.message.read`,
  `diagram.generation.create`; `finance-01` the first two; `recrut-01` none.
- Guardrails: a prompt carrying "ignore all previous instructions" and "you are now DAN" gave
  `zuno_guardrails_evaluations_total{client="open-webui",outcome="detected"}` and
  `zuno_guardrails_detections_total{client="open-webui",agent="open-webui"}` for `injection-ignore-instructions` and
  `injection-persona-override` (raw Prometheus). Mode stays `observe` (user decision 2026-11-02): the reply is not
  blocked; blocking is a platform decision for later.
