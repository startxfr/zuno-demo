# WP-193: Open WebUI user experience: one Zuno model, the tools on by default, a quiet chat

- **State:** Not started (2026-11-03: decisions recorded; ai-gateway code next)
- **ADRs:** [ADR-0588](../../adr/0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md)
- **Depends on:** [WP-191](wp-191-same-mcp-tools-in-the-three-experiences.md)
- **Target:** v0.13
- **Estimated files touched:** ~6 (ai-gateway `/v1/models` and tests, its README, `gitops/charts/open-webui/values.yaml`, docs)

> Why: the first Open WebUI test of WP-191 on 2026-11-03 showed a menu of eleven models, while the ai-gateway routes
> on the classification and never on the model name. The user picked codestral and was served by a local qwen model. The
> Confluence turns came back blank, because the streamed tool calls had no `index` (fixed in the ai-gateway, WP-191).
> User decisions of 2026-11-03:
> - one model, enforced by the ai-gateway and set in Open WebUI, shown as "Zuno";
> - the Zuno tools on in every new chat;
> - only the title as a background task;
> - an information banner;
> - Zuno prompt suggestions;
> - the interface in English;
> - the open-webui values pushed by that chart's owner session.

## Goal

A user opens Open WebUI and sees one model, "Zuno". The tools are already on, and four suggestions show what the platform
does. A banner says that Zuno picks the model and that internal content stays on local models. No background call other
than the conversation title spends the user's budget.

## Steps

1. **ai-gateway.** `GET /v1/models` returns `auto` alone to an experience client: the token's `azp` matches
   `MARKER_FAIL_CLOSED_CLIENTS`, the list that `tool_markers.is_fail_closed_client` already reads. `auto` carries
   `"name": "Zuno"` (`AUTO_MODEL_NAME`) for every caller. UnifAI keeps the full list.
   - Tests: Open WebUI and an OpenClaw client get `auto` alone, named Zuno; another client gets the full list.
   - Same build as the WP-191 streamed tool-call `index` fix.
2. **Open WebUI values** (sent to the chart's owner session, pushed with its user's go):
   - `DEFAULT_MODELS=auto`.
   - `DEFAULT_MODEL_METADATA` with `toolIds: [server:mcp:zuno-mcp]` and a description.
   - `DEFAULT_MODEL_PARAMS` with `function_calling: native`.
   - `ENABLE_TITLE_GENERATION=True`. The tags, follow-up, autocomplete, search-query and retrieval-query generations are off.
   - `WEBUI_BANNERS`: one dismissible info banner.
   - `DEFAULT_PROMPT_SUGGESTIONS`: four suggestions (Confluence, Drive, OpenShift documentation, a general question).
   - `DEFAULT_LOCALE=en-US`.
   - `OPENAI_API_CONFIGS` gets no `model_ids`. Open WebUI would then name the model by its id ("auto") and drop the
     ai-gateway's name.
3. **Prove it live**, as a consultant:
   - the model menu shows only Zuno;
   - the banner and the suggestions show;
   - a new chat has the tools on;
   - "Find our onboarding pages in Confluence" lists pages, with a `tools/call` in the mcp-gateway log and "classification
     raised by tool results … client=open-webui" in the ai-gateway log, served by a local provider;
   - the logs show one title call per new chat and no tags or follow-up call.
4. **Close.** Evidence file `docs/roadmap/evidence/wp-193-*.md`, demo script updated.

## Acceptance

On demo333, all of the following hold:
- Open WebUI lists only the Zuno model;
- a new conversation has the Zuno tools on;
- a Confluence question is answered with pages by a local model;
- no background generation other than the title reaches the ai-gateway;
- the ai-gateway test suite has no new failure.

## Coordination

- The ai-gateway code, the build and this brief belong to the zuno-demo-40 session.
- `gitops/charts/open-webui` belongs to its owner session. It gets the diff, pushes it with its user's go, and runs
  `make d2 check open-webui`.
- Every build, roll and sync is announced first and needs the user's go in the session that runs it.
