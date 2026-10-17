# WP-148: UnifAI parity for project memory, routing display and quota UX

- **State:** Not started
- **ADRs:** [ADR-0569](../../adr/0569-close-unifai-parity-gaps-generically.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)
- **Depends on:** [WP-146](wp-146-unifai-identity-and-context-header-forwarding.md)
- **Related:** [ADR-0209](../../adr/0209-introduce-project-scoped-agent-memory.md), [ADR-0528](../../adr/0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md), [WP-135](wp-135-routing-decision-explainability.md), [WP-154](wp-154-tekos-pilot-on-demo333.md)
- **Target:** v0.11
- **Estimated files touched:** ~18 in `startx-unifai` — a new MAS memory element, LLM response-metadata plumbing, chat UI components, error handling for 429, tests. None in `zuno-demo`.

> The three user-visible features the zuno agent layer has and UnifAI lacks.
> Each is built generically so that it can go upstream; nothing in this WP
> names zuno.

## Goal

UnifAI agents can read and write project-scoped memory stored in UnifAI's own
storage; the chat UI shows which provider answered and why (when the endpoint
returns that metadata); a 429 or quota rejection from the model endpoint is
shown as a clear, non-fatal message instead of a failed run.

## Steps

Work in `/home/cl/ClaudeCode/startx-unifai`, one feature branch per feature,
each from `main` (`make feature-start BRANCH=feat/<name>`), merged into
`devel` with `make feature-to-devel`. Keep the three branches independent so
each can be proposed upstream alone.

1. **Study the zuno behaviour to port (read-only).** In zuno-demo, read
   `components/rag-service/app/project_memory.py` (endpoint
   `POST /v1/project-memory/write` in `components/rag-service/app/main.py`),
   `components/agent-runtime/app/clients/project_memory_client.py` and the
   tests `components/agent-runtime/tests/test_project_memory_e2e.py` and
   `test_memory_extraction.py`. List the behaviours (scope key, write
   trigger, read-back into the prompt, deduplication) in the PR description.

2. **Memory element (`feat/project-memory`).** Add a memory element under
   `multi-agent/lib/mas/elements/tools/` (look at `builtin/` for the
   registration pattern) with `read` and `write` operations scoped by a
   generic `scope_id` (the project id is passed through the
   `{project_id}` placeholder of WP-146). Store text in Mongo and its
   embedding in Qdrant, reusing the RAG embedding client configuration; do
   not add a new datastore. Unit tests under `multi-agent/tests/unit/`
   covering scope isolation (one scope never reads another's entries).

3. **Response metadata (`feat/llm-response-metadata`).** In
   `multi-agent/lib/mas/elements/llms/openai_compatible/openai_compatible.py`
   and `stream_aggregator.py`, keep any non-standard top-level fields of the
   completion response (the ai-gateway returns `zuno_provider`, see
   `components/ai-gateway/app/main.py` in zuno-demo) and the response id, and
   attach them to the node's execution record. Expose them through the
   existing session/execution API without renaming them. Optional config
   `metadata_lookup_url` (template with `{response_id}`) lets the UI fetch a
   routing explanation; for zuno this will be
   `/v1/routing-decisions/{request_id}` on the ai-gateway.

4. **UI.** In `ui/client/src/components/agentic-ai/chat/ChatInterface.tsx`
   and `ui/client/src/components/agentic-ai/ExecutionTab.tsx`, show the
   metadata as a small, collapsible per-message badge (provider, model) and,
   when `metadata_lookup_url` is set, a "why this model" panel loaded on
   demand. Nothing is shown when no metadata is present.

5. **429 / quota UX (`feat/rate-limit-ux`).** In the `openai_compatible`
   element, map HTTP 429 (and a `Retry-After` header if present) to a typed
   error, not a generic failure. In the chat UI, render it as a non-fatal
   message with the retry delay. Unit test the mapping with a mocked 429.

6. **Agent tiles.** Do not port the zuno agent tiles from
   `components/agent-frontend/web`. UnifAI's agent repository
   (`ui/client/src/pages/AgentRepository.tsx`) replaces them; note any gap
   found while reviewing it as an open question here rather than coding it.

7. **Checks and images.** `make contrib-check` on each branch, then
   `make images-devel` from `devel`. No operator change is expected; if one
   becomes necessary, follow the operator release flow (`make test` envtest
   first, bump `VERSION` in `fork/unifai-operator/Makefile`, coordinate with
   the startx-unifai session before releasing, because OLM rolls it out to
   both demo333 stacks).

8. **Upstream.** Contact the upstream maintainers before any PR (ADR-0575,
   fork `MEMORY.md`); do not open PRs without the user's go-ahead.

## Acceptance

Unit tests for memory scope isolation, metadata passthrough and 429 mapping
pass; the UI builds (`ui/` package scripts); with no metadata and no 429 the
UI renders exactly as before. Live behaviour is checked in
[WP-154](wp-154-tekos-pilot-on-demo333.md).

## Open questions

- Should memory extraction (deciding what to remember) be an LLM node in a
  blueprint, or a feature of the element? Port the zuno behaviour first,
  then decide.
- Is UnifAI's agent repository enough for the per-agent landing pages the
  demo scripts use? Unverified until step 6.
