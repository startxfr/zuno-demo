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

## 2. `callAssertion.required: true`

- **State.** The mcp-gateway sends the assertion and confluence-mcp, git-forge-mcp and aap-mcp verify it, but still
  accept a call without one.
- **Switch.** `callAssertion.required: true` on the three servers (in `gitops/apps/mcp-*/application-d1.yaml`).
- **Before.** List every caller of those servers in the access logs; anything that is not the mcp-gateway (probes,
  the agents' direct calls, evaluation jobs) must send an assertion or be moved behind the gateway.
- **Proof.** A call with the gateway's workload token and no assertion gets 401; the `tools` moment of the golden
  path still passes.

## 3. `jwtAllowedClients` (per-client `azp` allowlist)

- **State.** Both gateways support it; empty means any client of the realm.
- **Switch.** Fill the list from the `azp` values seen in the gateway logs over a full week (UI clients, Dify,
  Open WebUI, Lightspeed, the evaluation client, the persona clients), then set it on ai-gateway and mcp-gateway.
- **Risk.** A forgotten client gets a 401 that looks like an outage. Roll it on one gateway first, watch 401s.

## 4. The rest of lot C and lot B switches

| Item | Switch | Waits for |
|---|---|---|
| REST entitlement | `restAgentEntitlement: true` | a post-demo golden-path run (it changes who may call a tool over REST) |
| Agent chain required | `agentChain.requireFor` | every caller that reaches the gateways signs, including agents called without a2a-gateway |
| Token-proxy inbound auth | `dify_token_proxy_inbound_auth` | re-registering Dify's stored credentials |
| Salesforce owner scoping | on with the connector | a Salesforce org (none today) |
| Namespace matcher on `metrics.query` | set the allowed namespaces per group | the list of groups that may query which namespaces |
| Space and repository allowlists for the other groups | extend beyond the five groups | a decision on what consultants and board may read |
| Guardrails `scanToolResults`, `/v1/messages` ceilings | on, with a ceiling per key | traffic numbers from a real week |

## 5. Other open items from the wave

- zuno-unifai EgressFirewall: see [the rehearsal plan](../platform/wp-224-unifai-firewall-rehearsal-plan.md).
- Agents scaffold (`platform/templates/agent/scaffold_agent.py` in zuno-demo-agents) still emits `project: zuno`.
- GitHub settings on `main`: secret scanning with push protection, a ruleset against force-push and deletion, the
  required checks. The `main` Secret scan is red on a documented false positive until v0.14.5.
- `startx-cluster-auth` and `startx-cluster-infra-config` OutOfSync (not from this wave).
- WP-226 live steps: first rendered release (`make d3 release RENDER_DIGESTS=1`), `zuno_validate_route_certs`, the
  AAP execution environment digest, `zuno-first-party-images` enforce extended to more namespaces.
- WP-227 (hardened profile) not started.

## Accepted by the user

The Vault recovery files (`ansible/vault-recovery-demo333.json` and `.rekey-raw.json`) stay in the operator's
working copy, ignored by git, for the demonstration. They are the only copies outside the password manager and are
vital. This is a risk the operator accepts. Do not remind to destroy them.
