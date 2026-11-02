# WP-183: Install OpenClaw on demo333

- **State:** Operator pending (2026-11-02: installed on demo333, `make d2 check openclaw` green, browser acceptance passed, chat through the gateway path working; the `openclaw` entitlement remains)
- **ADRs:** [ADR-0590](../../adr/0590-front-openclaw-with-oauth2-proxy-and-an-egress-firewall-one-claw-operator-per-persona-namespace.md), [ADR-0589](../../adr/0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md), [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
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

## Implementation notes (2026-11-02)

The values come from [WP-182's evidence](../evidence/wp-182-openclaw-spike.md), step 8; ADR-0590 records what
the spike changed in ADR-0589.

- **Step 1, chart** `gitops/charts/openclaw`. `operator.enabled` renders the CatalogSource (digest) and, per persona,
  the namespace `zuno-claw-<persona>` (label `zuno.io/experience-client`), an `OwnNamespace` OperatorGroup, a Manual
  Subscription on `startingCSV` and the EgressFirewall. `assistants.enabled` renders the ExternalSecrets, the
  oauth2-proxy front door (its Route on the operator's host, wave -10, before the `Claw`) and the `Claw` (oauth2
  credentials on the Keycloak Route, provider `zuno`, MCP `zuno`, lockdown). Personas and pins live in `values.yaml`.
- **Step 2, Applications** `zuno-openclaw-d0` (wave -58) and `zuno-openclaw-d1` (wave -57).
- **Step 3, identity.** Clients `openclaw-consultant-02` and `openclaw-sale-01` with WP-179's four-place pattern,
  appended after Open WebUI's (bba139b7): client credentials and browser flow, groups mapper. Their service-account
  users with the persona's groups are in `realm-zuno.json` for a fresh import; on a live realm the role copies the
  persona's groups to the service account through the admin API (users are create-only).
- **Step 4, token proxy:** not built. The operator's `oauth2` credential exchanges and refreshes the token and sets
  the headers (WP-182 steps 2 and 3).
- **Step 5, front door:** oauth2-proxy v7.15.5 by digest, the persona's email only, OpenClaw `password` mode behind
  it (ADR-0590 decision 3). The Route uses the router's certificate (edge), like the other Routes.
- **Step 6, role** `ansible/roles/openclaw`: `install` checks the catalog digest, checks
  `keycloak/openclaw-<persona>` and seeds `openclaw/<persona>` in Vault, sets the service-account groups, applies d0,
  approves only the InstallPlan naming the pinned CSV, applies d1 and waits for each `Claw` Ready. `check` asserts
  the CSV, the `Claw`, the running image IDs, the Routes, the 302 to Keycloak, and from each assistant's pod: 200
  through the proxy, nothing when bypassed, nothing from clawhub.ai or the internet. `make d2 check openclaw` runs
  `check` once `day2_check.yml` lists `openclaw` (shared file, requested from the WP-179 session).
- **Step 7, entitlement:** open. Until the `openclaw` agent is admitted in zuno-demo-agents, the MCP credential sends
  no `X-Zuno-Agent` (`gateways.mcpAgentHeader: false`) and the assistant gets the front-door read-only tools of its
  persona (consultant-02: five, sale-01: none).
- **Install order on demo333:** push (the Keycloak volume change rolls Keycloak, `zuno-keycloak-d1` follows
  `devel`), `make d0 install vault` (seeds the two client secrets), wait for the client reconcile Job, then
  `make d2 install openclaw`.

## Live results (demo333, 2026-11-02)

- **Install** (`make d2 install openclaw`, user's go) after `make d0 install vault` seeded `keycloak/openclaw-*` (seed
  **before** pushing the Keycloak change, or `zuno-keycloak-d1` stops on the missing ExternalSecret). Two fixes found by
  the first runs: the role waited for `zuno-openclaw-d0` Healthy before approving the InstallPlans, which keep it
  Progressing (af53c134); and the EgressFirewall's `Deny 0.0.0.0/0` cut the in-namespace operator from the API server,
  whose Service resolves to the control-plane node IPs (`dial tcp 172.30.0.1:443: i/o timeout`, crash loop), now allowed
  on 6443 by `nodeSelector` (030953fe).
- **State:** `zuno-openclaw-d0` and `-d1` Synced and Healthy; per persona the CSV `claw-operator.v0.0.227-commit-f5aa592`
  Succeeded, the `Claw` Ready, the operator's Route `HostAlreadyClaimed` behind the front door.
- **`make d2 check openclaw`:** all assertions pass for both personas: running image IDs equal the pins, front door
  admitted, 302 to Keycloak without a session, from the assistant's pod 200 from the ai-gateway through the proxy and
  nothing when bypassed, nothing from clawhub.ai or the internet.
- **Tools through the proxy** (`tools/list`, no `X-Zuno-Agent`): consultant-02's assistant gets
  `confluence.page.search`, `confluence.page.read`, `knowledge.tech.search`, `aap.platform.audit`,
  `aap.cluster.audit`; sale-01's gets none. The service accounts carry the persona's groups.
- **Metrics:** `zuno_model_calls_total{client="openclaw-consultant-02"}` in raw Prometheus.
- **Chat:** still times out with the GPU nodes down (the ai-gateway walks the local providers first); WP-188
  (ADR-0591) addresses it. Not a WP-183 defect.

- **Browser acceptance** (user, 2026-11-02): consultant-02 reaches its assistant's Control UI through Keycloak and its
  password; sale-01 is refused there; and the reverse on sale-01's assistant.
- **OpenClaw end to end:** `openclaw agent --local` in consultant-02's pod answers through the proxy, the ai-gateway and
  openai `gpt-4o-mini` (after WP-188). The gateway path (Control UI) gets 422: it sends message `content` as a list of
  text parts, which the ai-gateway schema refused; fixed in the ai-gateway (WP-179 session, build 32).
- **Secret exposure and rotation:** an over-broad `env` filter printed consultant-02's gateway token and UI password in
  the operator's terminal. The gateway token was rotated (operator Secret recreated, pod restarted); the UI password
  rotation in Vault (`openclaw/consultant-02`) is left to the user.

- **Gateway path after ai-gateway build 32** (3b300fe2, content parts accepted): `openclaw agent --agent default` (the
  Control UI's path) answers for both personas, model fetch 200 in 1.2 to 2.7 s from openai `gpt-4o-mini`;
  `zuno_model_calls_total` / `zuno_model_tokens_total` carry `client="openclaw-consultant-02"` and
  `client="openclaw-sale-01"` in raw Prometheus.

**Remaining acceptance:** the entitled-tool proof once the `openclaw` experience-client declaration is admitted (the Open WebUI track's WP,
then `gateways.mcpAgentHeader: true`).

