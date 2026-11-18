# WP-251: Require the agent chain for experience clients, with a self-name exemption

- **State:** Done (2026-11-12): lots 1 and 2 live on demo333; unifai joins the list when the UnifAI per-call signer exists (fork work, out of scope)
- **ADRs:** [ADR-0602](../../adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md),
  [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md) (M14, the agent chain)
- **Depends on:** [WP-225](wp-225-ai-and-agent-surface-guardrails-metering-delegated-scope.md) lot C (the chain and `agentChain.requireFor`),
  [WP-247](wp-247-sign-gateway-assertions-with-vault-transit.md) (the chain is signed by Vault Transit)
- **Related:** the [post-demo hardening list](../post-demo-hardening.md) item 4 (`agentChain.requireFor`, analysis of 2026-11-12 by the
  zuno-avancement session, handed to this WP), [WP-250](wp-250-retire-the-shared-mcp-workload-token.md)
- **Target:** v0.16
- **Estimated files touched:** ~6: `components/ai-gateway/app/main.py` (`_agent_identity`), its tests, the `ai-gateway` chart notes,
  `ansible/roles/llm/tasks/install.yml` and `ansible/clusters/demo333.yml` (the list), this brief, the post-demo list

> Execute this brief as a standalone task from the repository root. Code and tests are local first; every cluster action needs the
> user's go, outside a freeze, with a golden path after it. Opened 2026-11-12 (user's go) at the request of the zuno-avancement session.

## Why

The ai-gateway keys three things on the agent a call is made for: the WP-209 classification floor, the routing preferences and the
guardrails mode. The agent is the `X-Zuno-Agent` header, which any client can write, unless a valid `X-Zuno-Agent-Chain` (signed by the
a2a-gateway) replaces it. `agentChain.requireFor` lists the clients whose `X-Zuno-Agent` is ignored without a valid chain, so a token of
that client can no longer claim to be `tekos` or `arkos` to pick a lighter floor or a different model.

It is empty today. The analysis of seven days of `zuno_model_tokens_total` by (client, agent) shows why it cannot simply be filled:

- `unifai` names `arkos` (~43k tokens) and `tekos` (~27k). A chain exists only on a2a-gateway turns; the resources the UnifAI operator
  renders send static headers. Listing `unifai` needs a per-call signer in the UnifAI fork (a hook that signs `X-Zuno-Agent-Chain` with
  its own Ed25519 key, accepted by the verifiers as a second issuer). That is fork work, through unifai-main, and is **out of scope**.
- `dify`, `kagent`, `open-webui`, `openclaw-*` (as `openclaw`) and `blender` name ONLY themselves. Those names match nothing in the
  floors, the routing policy or the guardrails modes (all generated from the agents release); only the metrics `agent` label uses them.
  Listing these clients with today's code would blank the label and protect nothing.
- `zuno-evaluations` names `arkos`/`tekos` directly (probes, the golden path's sovereignty moment). It stays unlisted.

## Goal

A client listed in `agentChain.requireFor` may name ITSELF without a chain; any other agent it names needs a verified chain. Then
`requireFor = [dify, kagent, open-webui, "openclaw-*", blender, world-model]` changes no behaviour today and stops those tokens from
claiming `tekos` or `arkos`.

## Design

In `_agent_identity` (components/ai-gateway/app/main.py), when the client is in `requireFor`, no valid chain, and the agent header is
non-empty:

- the **self name** of a client is its `azp` (`dify`, `kagent`, `open-webui`, `blender`, `world-model`); for `openclaw-*` it is
  `openclaw` (the name the metrics already use);
- `X-Zuno-Agent` equal to the self name: keep it (unchanged behaviour, the metrics label stays);
- anything else: ignore it and log it, as today.

| Option | Verdict |
|---|---|
| **A. Self-name exemption in `_agent_identity` (recommended)** | Smallest change, no behaviour change for the listed clients, closes the claim of `tekos`/`arkos` |
| B. Teach the floors and the policy about the self names | Wider change in the generated agents release; no gain |
| C. Wait for the UnifAI signer and list everything at once | Leaves the gap open; the signer is fork work with its own schedule |

## Lots

| Lot | Content | Live effect |
|---|---|---|
| 1 | The exemption in `_agent_identity` and tests: a listed client naming itself keeps the name; naming `tekos` is ignored and logged; an unlisted client is untouched; a valid chain still wins; `openclaw-*` maps to `openclaw`; case and whitespace of the header | none (code only) |
| 2 | Build and roll ai-gateway (an image build is a roll through the image trigger), set `agentChain.requireFor` through `zuno_ai_gateway_agent_chain_require_for` in `ansible/roles/llm/tasks/install.yml` and `ansible/clusters/demo333.yml`, `make d2 install llm`, golden path | ai-gateway rolls; the quota counters restart once |

## Proof

- A dify-client token with `X-Zuno-Agent: tekos` logs "ignored: client dify must present a valid agent chain" and takes the client floor.
- The same token with `X-Zuno-Agent: dify` is unchanged, and the metrics label is still `dify`.
- The golden path passes (13/13), including the sovereignty and delegation moments.

## Out of scope

- Listing `unifai` (needs the fork signer, through unifai-main and b9) and `zuno-evaluations` (names the agents directly).

## Progress log

- **2026-11-12, lot 1 code and tests (repo only, not built, not applied).** `client_self_name()` and the exemption in `_agent_identity`
  (components/ai-gateway/app/main.py): a client listed in `AGENT_CHAIN_REQUIRE_FOR` that names itself (its `azp`, `openclaw` for
  `openclaw-*`, compared trimmed and case-insensitively) keeps the header silently; any other agent it names is ignored and logged as
  before; an unlisted client and a valid chain are unchanged. Four tests in `components/ai-gateway/tests/test_wp225_lot_c.py` (13/13
  pass; `test_wp225_guardrails_metering` 57/57; `test_wp209_classification_floor` exits 0). The role now passes
  `zuno_ai_gateway_agent_chain_require_for` (default empty) to the chart in `ansible/roles/llm/tasks/install.yml`; the cluster value
  (`dify, kagent, open-webui, openclaw-*, blender, world-model`) is added to `ansible/clusters/demo333.yml` only in lot 2.
- **2026-11-12, lot 2 live (user's go).** Pushed as devel 3104287e. ai-gateway rebuilt from it (a build is a roll through the image
  trigger), then `make d2 install llm` set `agentChain.requireFor` to dify, kagent, open-webui, `openclaw-*`, blender, world-model
  (`zuno_ai_gateway_agent_chain_require_for` in `ansible/clusters/demo333.yml`). `REDIS_ADDR` unchanged (internal Redis). Golden path
  13/13 PASS. Proof with a real token of the dify client (client_credentials, never printed): `X-Zuno-Agent: tekos` logs
  "X-Zuno-Agent 'tekos' ignored: client dify must present a valid agent chain (AGENT_CHAIN_REQUIRE_FOR)" and answers 200 on the
  client floor; `X-Zuno-Agent: dify` logs nothing and answers 200. The golden path's own dify, kagent, open-webui and blender
  moments logged no ignored agent, so none of them claimed another agent. Rollback: remove the list from `demo333.yml` and re-run
  `make d2 install llm`.
