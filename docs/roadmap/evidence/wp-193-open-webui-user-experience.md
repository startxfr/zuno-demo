# WP-193: Open WebUI user experience

- **Date:** 2026-11-03, demo333, as consultant-01
- **Running versions:** ai-gateway build 39 (`0ede3b26`); Open WebUI values `66f753a1` and `df58107e`, Open WebUI 0.12.5
- **Brief:** [WP-193](../work-packages/wp-193-open-webui-user-experience.md)

## What was verified

1. **One model.**
   - `GET /v1/models` with an OpenClaw token returns `[("auto", "Zuno")]`.
   - Open WebUI's menu shows "Zuno" only, with the description "Zuno picks the model for you: internal data stays on local
     models." (user's screenshot, 12:01 local).
2. **Banner and suggestions.**
   - The info banner "Zuno chooses the model for each answer. Answers that use Confluence or the technical documentation are
     produced by a local model." shows on the home page.
   - The suggestions show; Open WebUI displayed three of the four.
3. **Tools on by default.**
   - A new chat shows the tools button with "1" selected; "Zuno tools" lists six tools.
   - A chat created before the change keeps its switch off: defaults apply when a chat is created.
4. **Built-in tools off.**
   - Before `df58107e` the model called `list_knowledge_bases`, `search_chats`, `search_notes` and `view_chat` and found
     nothing.
   - After it, the same question runs `zuno-mcp_confluence.page.search` and lists six onboarding pages (12:14 local).
5. **Streamed tool calls.** Build 39 sends `"index": 0` on a streamed tool call. Without it, Open WebUI dropped the call and
   showed a blank turn.
6. **Routing.** All calls of the turn are served by the local `qwen36-27b-instruct` (ai-gateway log, 11:14 UTC).

## Notes

- The interface language follows the browser or the user's setting (French here); `DEFAULT_LOCALE=en-US` is only the default.
- Background tasks: the title is still generated. Tags, follow-ups and autocomplete are off by configuration
  (`ENABLE_*_GENERATION=False`, in the pod's environment); this run did not count them call by call.
- Marker verification in Open WebUI: see the accepted limit in the
  [WP-191 evidence](wp-191-same-mcp-tools-live-proof.md).
