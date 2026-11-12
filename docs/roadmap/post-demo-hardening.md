# Post-demo hardening list (ADR-0602, ADR-0603)

Written 2026-11-07, before the demonstration of 2026-11-09. Every item below is shipped in git and **off** or
**partly open** on demo333, by decision, to protect the golden path. Each needs a golden-path run after the switch.
The order is by risk reduction per effort.

## 1. Move the signing keys out of reach of `ocp-ai-dev` and `ocp-ai-ops`

- **Gap.** Members of those groups can create ExternalSecrets in `zuno-ai-run`, so they can read the two Ed25519
  private keys (`zuno/mcp/gateway-call-assertion`, `zuno/a2a/agent-chain`) and the workload token that signs the
  lot B caller context. With a key they can mint an assertion or an agent chain.
- **Fix, option A (recommended).** Vault Transit: the gateways ask Vault to sign (no private key leaves Vault),
  using the pattern WP-068 set up for image signing. The Vault role is bound to the gateway ServiceAccounts only.
- **Fix, option B.** Keep the keys as Secrets but sync them into a namespace those groups cannot create
  ExternalSecrets in, and mount through a projected volume, plus an admission rule that refuses an ExternalSecret
  naming those Vault paths outside the platform's own namespaces.
- **Proof.** As `ocp-ai-dev`, creating an ExternalSecret for those paths is refused; the golden path still passes.
- **Brief.** [WP-247](work-packages/wp-247-sign-gateway-assertions-with-vault-transit.md) (design settled with the user on
  2026-11-11: Transit, fail closed, one-shot public-key switch, assertion first then agent chain).
- **Status 2026-11-11 (WP-247 Done).** Both keys are in Vault Transit and no namespace store can read them (proved with the store's own
  role); golden path 14/14 after each switch. Open: the final persona proof, deleting the two old Vault values, and the
  workload token, retired by [WP-250](work-packages/wp-250-retire-the-shared-mcp-workload-token.md) (Done 2026-11-12: the caller context rides inside the Transit-signed assertion).

## 2. `callAssertion.required: true`

- **Status 2026-11-11 (switched).** `callAssertion.required: true` is set on the three servers in git and live; the
  golden path passed after the Transit switch (WP-247). The text below is the original plan.
- **State.** The mcp-gateway sends the assertion and confluence-mcp, git-forge-mcp and aap-mcp verify it, but still
  accept a call without one.
- **Switch.** `callAssertion.required: true` on the three servers (in `gitops/apps/mcp-*/application-d1.yaml`).
- **Before.** List every caller of those servers in the access logs; anything that is not the mcp-gateway (probes,
  the agents' direct calls, evaluation jobs) must send an assertion or be moved behind the gateway.
- **Proof.** A call with the gateway's workload token and no assertion gets 401; the `tools` moment of the golden
  path still passes.

## 3. `jwtAllowedClients` (per-client `azp` allowlist)

- **Status 2026-11-11 (switched on both gateways).** Ten clients (unifai, open-webui, dify, kagent, world-model,
  blender, `openclaw-*`, zuno-evaluations, zuno-stresstest, zuno-admin-api), read from the live realm: the clients that
  carry the `zuno-admin-api` audience. No client refused in the 24 h after. The gateways log `azp` only on a refusal,
  so the "one week of logs" method below does not work; the list came from the realm. Open: check whether world-model,
  blender and `/admin/*` really call the gateways, to tighten the list. The text below is the original plan.
- **State.** Both gateways support it; empty means any client of the realm.
- **Switch.** Fill the list from the `azp` values seen in the gateway logs over a full week (UI clients, Dify,
  Open WebUI, Lightspeed, the evaluation client, the persona clients), then set it on ai-gateway and mcp-gateway.
- **Risk.** A forgotten client gets a 401 that looks like an outage. Roll it on one gateway first, watch 401s.

## 4. The rest of lot C and lot B switches

| Item | Switch | Waits for |
|---|---|---|
| REST entitlement | `restAgentEntitlement: true` | **done 2026-11-11** (user's go): on the demo333 mcp-gateway (`AGENT_ENTITLEMENT_EVERY_CALL=true`), golden path 13/13 after |
| Agent chain required | `agentChain.requireFor` | every caller that reaches the gateways signs, including agents called without a2a-gateway. **Live 2026-11-12** ([WP-251](work-packages/wp-251-agent-chain-required-for-experience-clients.md), zuno-main): dify, kagent, open-webui, `openclaw-*`, blender and world-model may name only themselves without a chain; a dify token naming tekos is ignored and served on its client floor; golden path 13/13. Still unlisted: unifai (needs the fork's per-call signer) and zuno-evaluations (see below the table) |
| Token-proxy inbound auth | `dify_token_proxy_inbound_auth` | re-registering Dify's stored credentials |
| Salesforce owner scoping | on with the connector | a Salesforce org (none today) |
| Namespace matcher on `metrics.query` | set the allowed namespaces per group | **done 2026-11-11** (user's go): `ocp-ai-ops` (the only group with the tool) gets the 13 mcp-k8s namespaces plus `nvidia-gpu-operator`; live, golden path PASS, a query outside them returns nothing ([evidence](evidence/hardening-allowlists-metrics-matcher-2026-11-11.md)) |
| Space and repository allowlists for the other groups | extend beyond the five groups | **done 2026-11-11** (user's go): consultant, board, cdp and lightspeed_readonly get the internal spaces SXSI, SXS, SXSD and SAC (no customer or personal space); consultant, board and cdp get `github:startxfr/*`; the unused `"*"` entries of sales, finance, adv and recrut are removed; live, a customer space and a non-startxfr repository are refused ([evidence](evidence/hardening-allowlists-metrics-matcher-2026-11-11.md)) |
| Guardrails `scanToolResults`, `/v1/messages` ceilings | on, with a ceiling per key | traffic numbers from a real week: **the measurement week started 2026-11-11 20:40 UTC** (user's go); read the per-key token and tool-result volumes from the ai-gateway metrics on 2026-11-18, then set the ceilings |

### `agentChain.requireFor`: analysis of 2026-11-12

`agentChain.requireFor` is the ai-gateway's list of Keycloak clients that must present a valid agent chain when they
name an agent. Over seven days, `zuno_model_tokens_total` broken down by client and agent shows this:

| Client | Agents named | Chain |
|---|---|---|
| unifai | arkos (about 43,000 tokens), tekos (about 27,000) | only on the turns the a2a-gateway runs; the operator-rendered resources send static headers |
| zuno-evaluations | arkos, tekos | none: the probes and the golden path name the agent directly |
| dify, kagent, open-webui, `openclaw-*` (as `openclaw`), blender | their own name only | none |

No client can be listed today without a change of behaviour:

- **unifai** needs the per-call signer in the UnifAI fork described in WP-225: a hook in the outbound LLM and MCP
  clients that signs a chain with its own key, which the verifiers accept as a second issuer.
- **The experience clients** name only themselves. Those names match nothing in the classification floors, the
  routing policy or the guardrails modes, which are all generated from the agents release; only the `agent` label of
  the metrics uses them. Listing these clients as the code is today would blank that label and protect nothing.
  Proposed change in the ai-gateway: a listed client may name itself without a chain (the agent equals its `azp`, with
  `openclaw-*` mapped to `openclaw`), and any other agent needs the chain. These clients could then be listed with no
  change of behaviour, and none of them could claim an agent such as tekos (its routing preferences and guardrails
  mode) any more.
- **zuno-evaluations** stays unlisted until its probes go through the a2a-gateway.

Handed to zuno-main, which owns the agent chain (WP-247, WP-250). Each live step needs the user's go.

## 5. Other open items from the wave

- zuno-unifai EgressFirewall: see [the rehearsal plan](../platform/wp-224-unifai-firewall-rehearsal-plan.md).
- Agents scaffold (`platform/templates/agent/scaffold_agent.py` in zuno-demo-agents) still emits `project: zuno`.
- GitHub settings on `main`: secret scanning with push protection, a ruleset against force-push and deletion, the
  required checks. The `main` Secret scan is red on a documented false positive until v0.14.5.
- `startx-cluster-auth` and `startx-cluster-infra-config` OutOfSync (not from this wave).
- WP-226 live steps: first rendered release (`make d3 release RENDER_DIGESTS=1`), the AAP execution environment
  digest, `zuno-first-party-images` enforce extended to more namespaces.
- `zuno_validate_route_certs`: **done 2026-11-11** (user's go). The three runs passed with it on, every Route these
  tasks call verifies, and the default is `true` in `ansible/inventories/demo/group_vars/all/main.yml` (ADR-0603 M3).
- WP-227 (hardened profile) not started. It now carries the removal of ArgoCD's `cluster-admin` (user decision
  2026-11-11, ADR-0602 amendment).
- The plain-HTTP startx chart repository: **done 2026-11-12**, fixed at its source.
  - The helm-repository project publishes HTTPS URLs (2026-11-11).
  - zuno reads the charts over HTTPS: `Chart.yaml` names the URL, and the locks, repository Secret, AppProjects (no
    http entry left), CI and console repository follow. The Applications are unchanged and the golden path passed
    ([evidence](evidence/adr-0602-c4-startx-charts-over-https-2026-11-12.md)).

## Accepted by the user

The Vault recovery files (`ansible/vault-recovery-demo333.json` and `.rekey-raw.json`) stay in the operator's
working copy, ignored by git, for the demonstration. They are the only copies outside the password manager and are
vital. This is a risk the operator accepts. Do not remind to destroy them.
