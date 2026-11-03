# ADR-0594: Give the three experiences the same MCP tools behind signed classification markers

- **Status:** Implemented (2026-11-03, WP-191: same tools in the three experiences, markers verified from OpenClaw, Open WebUI fail-closed)
- **Target:** v0.13
- **Date:** 2026-11-03
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0592](0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md) (amended in part), [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md), [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0588](0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md)

## Context

UnifAI, Open WebUI and OpenClaw already call one MCP endpoint, the mcp-gateway's `POST /mcp` (WP-152). They do not see the
same tools. ADR-0592 gave the two experience clients a `chat` task with three C1 tools (Drive, Gmail, diagram) and kept
Confluence and the technical knowledge base with the UnifAI agents, because an experience client's chat may be answered by a
SaaS model and the client never raises the level of its own turn from a tool result.

The user asked on 2026-11-03 for the same tools in the three experiences, filtered by the user's groups, not by the UI. The
risk ADR-0592 avoided is real: both SaaS providers accept C1 and C2 (WP-187 measurement), and a Confluence page fetched in
Open WebUI would otherwise go to a SaaS model on the next turn. The control has to sit on the server side, where the
experience clients cannot switch it off.

The pieces exist. ADR-0034 computes the effective classification of a call from its complete context. ADR-0035 lets a tool
declare that its results must never reach an external model (`external_model_policy.allow_context: false`). The ai-gateway
routes on the classification and on `local_only`. What is missing is a way for the ai-gateway to know, from the messages it
receives, that a tool result was in the context and how sensitive it was.

## Decision

**Experience clients get the read tools their users' groups allow, as the agents do; every tool result carries a signed
classification marker, and the ai-gateway raises the call from the markers it finds.**

1. **Tools.** The `chat` task of `open-webui` and `openclaw` (agents release) also allows `confluence.page.search`,
   `confluence.page.read` and `knowledge.tech.search`. The tool policy's groups still decide who sees them. Writes, Git, AAP
   and Salesforce stay with the agents. The two clients call `/mcp` with `X-Zuno-Data-Classification: C2`, the highest level
   of the tools they may use; their model calls keep declaring C1.
2. **Marker.** The mcp-gateway appends one line to the text of every successful `tools/call` result on `/mcp`:
   `[zuno-classification level=<C1..C4> external=<0|1> sig=<hex>]`. `level` is the highest of the tool's
   `min_classification` and the levels its results carry (the RAG chunks of WP-187); `external=0` when the tool's policy
   forbids external context (ADR-0035). `sig` is an HMAC-SHA256, with a key shared by the two gateways, over the level, the
   external flag and the SHA-256 of the result text the line follows. The structured content is unchanged.
3. **Raise.** For every call, the ai-gateway reads the markers in all the messages it receives. A marker whose signature
   verifies raises the call's classification to its level (ADR-0034); `external=0` makes the call local-only. For an
   experience client (ADR-0587), a `tool` message without a valid marker counts as `C2` and local-only: fail closed. For an
   experience client, a call raised to C2 or above is local-only too, since the external providers accept C2.
4. **Key.** One random key, generated in Vault and read by both gateways through an ExternalSecret; rotating it only makes
   older markers count as missing. Without the key, the mcp-gateway adds no marker and the ai-gateway trusts none, so the
   experience clients fall back to fail-closed.
5. **Scope.** UnifAI agents are not changed by this ADR: their routing stays per task (`local_only_for`, ADR-0565). The
   markers they receive are read the same way, so a marked C2 result can only raise their call, never lower it.

> **Note (2026-11-03, WP-193):** the same experience-client list (`MARKER_FAIL_CLOSED_CLIENTS`) also narrows the
> ai-gateway's `GET /v1/models` to `auto` alone, named "Zuno". Live testing also showed that a streamed tool call needs an
> `index` for Open WebUI to run it; the ai-gateway now sends one.

> **Note (2026-11-03, WP-191 live proof):** Open WebUI rewrites MCP results before the next model call. When the text is
> not JSON it adds the structured content beside it, then dumps the list as indented JSON. The signed text never reaches
> the ai-gateway, so in Open WebUI no marker verifies: every tool turn counts as unmarked, C2 and local. That is the
> fail-closed case of the Consequences. The user accepted it on 2026-11-03. OpenClaw passes the text through and its
> markers verify.

## Alternatives considered

- **A dedicated local model per UI that alone receives the C2 tools:** little code, but nothing stops a user from using the
  tool with a SaaS model; the control would be a client setting.
- **Every experience-client conversation local-only:** simplest, but the SaaS models disappear from Open WebUI and OpenClaw
  and the GPU load grows for every chat.
- **An unsigned marker:** a client or a user editing a message could lower the level by rewriting it.

## Consequences

- One tool surface per person across the three experiences, filtered by groups. Confluence content read in Open WebUI or
  OpenClaw is only ever answered by a local model.
- A user who edits a tool message can only make it count as unmarked, which is C2 and local-only. A signed marker copied
  from another result fails, because the signature binds the text it follows.
- If a client rewrites tool output (whitespace, truncation), its markers fail and its tool turns become local-only. That is
  the safe direction; it is measured live in WP-191.
- The mcp-gateway and the ai-gateway share a secret; Vault seeds it like the other platform keys (ADR-0345).
- Visible to the user: after a Confluence or knowledge-base call in Open WebUI or OpenClaw, the rest of that conversation is
  answered by a local model, even when a SaaS model was picked; a request that only SaaS models may serve is refused with
  503 "no eligible provider". Neither UI has a hook to show why, so the demo script says it.
- ADR-0592 decision 5 (experience clients declare C1 and use only C1 tools) and the C1 clause of ADR-0588 are amended in
  part: the model connection stays C1, the MCP connection becomes C2. The agents release's client checks
  (`validate_client`, `admit_okf_bundle.py` in the signer image) follow the same change.
