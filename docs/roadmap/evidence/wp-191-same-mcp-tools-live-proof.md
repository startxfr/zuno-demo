# WP-191: the same MCP tools in the three experiences, behind signed classification markers

- **Date:** 2026-11-03, demo333
- **Decision:** [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md)
- **Running versions:**
  - agents release v0.10.0, promoted by zuno-demo PR #19 and on main through PR #20;
  - mcp-gateway with the marker key, rolled by AAP job 1287 (`make d2 install mcp`);
  - ai-gateway build 38 (`4adf47a1`), then build 39 (`0ede3b26`);
  - Keycloak sync `325f9c28`;
  - Open WebUI values `d097e790` (MCP connection at C2), `66f753a1` and `df58107e` (WP-193);
  - OpenClaw chart `e2dc9cd9` (MCP connection at C2, on main).

## What was verified

1. **Key.**
   - ExternalSecret `zuno-tool-marker-key` in `zuno-ai-run` is `SecretSynced`.
   - Both gateways load `ZUNO_MARKER_KEY`, and the SHA-256 of the value is the same in both pods. The value itself was
     never printed.
   - Trap: the first mcp-gateway pod started a few seconds before the Secret existed. The reference is optional, so it ran
     with an empty key until the role recreated it.
2. **Same tools, filtered by groups**, from `tools/list` on `/mcp` through each OpenClaw assistant's proxy:
   - consultant-02 gets six tools: `drive.document.search`, `gmail.message.read`, `diagram.generation.create`,
     `confluence.page.search`, `confluence.page.read`, `knowledge.tech.search`;
   - sale-01 gets the first three only.
   - Open WebUI, signed in as consultant-01, lists the same six "Zuno tools" (user's screenshots, 12:01 local).
3. **Markers.**
   - `confluence.page.search "onboarding"` returns real SXSI pages followed by `[zuno-classification level=C2 external=0 sig=…]`.
   - `knowledge.tech.search` returns 3 C2 chunks (Confluence) and 2 C1 chunks (Red Hat documentation) under a `level=C2`
     marker, the highest level in the result.
4. **Raise, OpenClaw** (consultant-02, 09:17-09:18 UTC):
   - a turn carrying the real marker is logged `classification raised by tool results: C1 -> C2, local_only False -> True
     (marker C2, marker external=0) client=openclaw-consultant-02`;
   - the same turn with the marker rewritten to `C1 external=1` fails the signature and is logged `unmarked tool result`,
     so it stays C2 and local.
5. **Open WebUI end to end** (consultant-01, 11:14 UTC):
   - the suggestion "Find our onboarding pages in Confluence" runs `zuno-mcp_confluence.page.search` and the answer lists
     six onboarding pages;
   - every model call goes to `qwen36-27b-instruct` (local), logged `classification raised by tool results: C1 -> C2,
     local_only False -> True (unmarked tool result) client=open-webui`.

## Findings fixed on the way

- **401 on the technical-docs search for OpenClaw.** The rag-server checks `aud` against `zuno-admin-api`, and the
  `openclaw-*` clients had no audience mapper. Fixed by `325f9c28`, the same `maas-gateway-audience` mapper as open-webui.
- **Blank Open WebUI turns.** Open WebUI drops a streamed `tool_call` delta that has no `index`. Fixed in the ai-gateway by
  `080d8b1c` (build 39); a streamed tool call now carries `"index": 0`.
- **The model chose Open WebUI's built-in tools** (`list_knowledge_bases`, `search_chats`, …) over the Zuno tools. Fixed by
  turning off `builtin_tools` (`df58107e`, WP-193).

## Accepted limit (user decision 2026-11-03)

Open WebUI rewrites MCP results before it sends them back to the model:
- the marked text is no longer JSON, so `utils/mcp/client.py:193-227` adds the structured content beside it;
- `utils/middleware.py:854-931` then dumps the list as indented JSON.

The marker reaches the ai-gateway, but the text it signs does not, so in Open WebUI it never verifies. Every tool turn there
counts as unmarked: C2 and local, the fail-closed direction ADR-0594 planned for. OpenClaw passes the text through, so its
markers verify. A Drive turn answered by a SaaS model is therefore only possible from OpenClaw. Today the routing serves
both on local models while they are ready, so the user sees no difference.
