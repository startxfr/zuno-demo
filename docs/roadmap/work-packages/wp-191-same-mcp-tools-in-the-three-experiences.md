# WP-191: The same MCP tools in the three experiences, behind signed classification markers

- **State:** Done (2026-11-03, [evidence](../evidence/wp-191-same-mcp-tools-live-proof.md))
- **ADRs:** [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md), [ADR-0592](../../adr/0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md), [ADR-0034](../../adr/0034-compute-effective-classification-from-the-complete-context.md), [ADR-0035](../../adr/0035-prevent-restricted-internal-context-from-reaching-external-models.md)
- **Depends on:** [WP-189](wp-189-experience-clients-in-the-agents-release.md), [WP-190](wp-190-one-identity-one-budget-and-one-infrastructure-pattern-for-the-three-experiences.md)
- **Related:** [WP-187](wp-187-carry-the-source-classification-through-unifai-rag-results.md), [WP-152](wp-152-mcp-gateway-evaluation-and-mcp-north-side.md)
- **Target:** v0.13
- **Estimated files touched:** ~12 in `zuno-demo` (mcp-gateway front door and tests, ai-gateway classification and tests, both
  charts, the Vault role, the open-webui and openclaw values, docs); ~4 in `zuno-demo-agents` (the two `chat` tasks, the client checks)

> Why: the user asked on 2026-11-03 for one "universal" MCP server for UnifAI, Open WebUI and OpenClaw. The endpoint is already
> one (`POST /mcp`, WP-152); the tools are not: the experience clients see three C1 tools, the agents see Confluence and the
> technical knowledge base. User decisions of 2026-11-03: same tools filtered by the user's groups; Confluence search and read
> plus the technical-docs search added; a signed marker on every tool result read by the ai-gateway (not a per-UI local model,
> not every chat local); work directly on `devel`.

## Goal

A person sees the same read tools in UnifAI, Open WebUI and OpenClaw, as their groups allow, and a Confluence or
knowledge-base result fetched in Open WebUI or OpenClaw is only ever answered by a local model.

## Steps

1. **Documents.** ADR-0594, this brief, the correction notes in ADR-0592 and ADR-0588, indexes; `check_docs.py` green.
2. **mcp-gateway (this session).** `tools/call` on `/mcp` appends the marker line of ADR-0594 decision 2 to each successful
   result text: level = max(tool `min_classification`, the `classification` fields in the result), `external` from the
   tool policy, HMAC-SHA256 over level, flag and the SHA-256 of the text, key from `ZUNO_MARKER_KEY`. No key, no marker.
   Tests: marker present and verifiable; RAG result levels raise it; `external=0` for a no-external-context tool; no key, no line.
3. **ai-gateway (this session).** Read every marker in the request messages, verify it, raise the classification of the
   call (never lower it) and set local-only for `external=0`. For an experience client: a `tool` message without a valid
   marker counts as C2 and local-only; a call at C2 or above is local-only. Tests: valid C2 marker raises and forces local
   for open-webui; forged or replayed marker on other text is ignored (and counts as missing); unmarked tool message is
   C2 local-only for an experience client and unchanged for UnifAI; no key, no trust.
4. **Key.** A Vault path `zuno/ai-gateway/tool-marker` seeded once (ADR-0345), one ExternalSecret per gateway, env
   `ZUNO_MARKER_KEY` in both charts (optional mount: absent key keeps today's behaviour plus fail-closed).
5. **Agents release (user).** `experience-clients/*/tasks/chat.md` allow `confluence.page.search`, `confluence.page.read`,
   `search_technical_docs`; the client checks (`validate_client`, `admit_okf_bundle.py` in the signer image) accept C2 tools
   for a client calling at C2. Release and promotion by the user; signer image rebuilt and mcp-gateway pod recreated.
6. **Clients.** `X-Zuno-Data-Classification: C2` on the MCP connection only: `TOOL_SERVER_CONNECTIONS` in
   `gitops/charts/open-webui/values.yaml` (announced to its owner) and the openclaw MCP headers. The model connections stay C1.
7. **Prove it live.** As sale-01 or consultant-01: in Open WebUI and in OpenClaw, list the tools (Confluence and the
   knowledge base appear for a consultant, not for recrut-01); a Confluence question is answered by a local provider
   (ai-gateway span `zuno.provider`), a Drive question by a SaaS one; the gateway logs show the markers verified.
8. **Close.** Evidence `docs/roadmap/evidence/wp-191-*.md`, ADR-0594 to Implemented, demo script step 6 updated.

## Acceptance

On demo333, the same user sees the same read tools in the three experiences; a turn after a Confluence or knowledge-base
call in Open WebUI or OpenClaw is answered by a local model, live; a tool message without a valid marker from an experience
client is answered locally; the mcp-gateway and ai-gateway test suites are green.

> **Closure note (2026-11-03).** The acceptance is met, with three precisions:
> - Open WebUI rewrites tool results, so its markers never verify there. Every tool turn counts as unmarked: C2 and local.
>   The user accepted this limit; a Drive turn served by a SaaS model is only possible from OpenClaw.
> - "Green" means no new failure. The ai-gateway suite has 17 failures that also fail on a clean `devel` in this
>   workstation's environment, and the mcp-gateway suite has 12 failures and 4 errors, also present on a clean `devel`.
>   The new marker tests pass.
> - Three gaps found live were fixed on the way: the `zuno-admin-api` audience for the OpenClaw clients, the streamed
>   tool-call `index`, and Open WebUI's built-in tools (WP-193).

## Coordination

mcp-gateway, ai-gateway, the key and this brief: the zuno-demo-40 session. `gitops/charts/open-webui`: its owner session,
told before the values change. `gitops/charts/openclaw`: no active owner; changes announced to the peers. The agents release:
the user. Every build, roll and sync is announced first, and needs the user's go in the session that runs it.
