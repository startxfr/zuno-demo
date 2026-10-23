# WP-148: UnifAI parity for project memory, routing display and quota UX

- **State:** Done
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

## Repo work done (2026-10-22, fork devel `5d318d4ca`, not pushed)

Three independent branches from `main`, merged into fork `devel`; 68 unit
tests pass in `tests/unit/llms` and `tests/unit/tools`, the rest of the suite
is unchanged (78 failed / 34 errors before and after, pre-existing).

- **`feat/project-memory`:** memory tool with `read`/`write` (text in Mongo,
  vector in Qdrant, dedup per scope) and `set_fact`/`get_fact`/`list_facts`
  (Mongo `facts`, unique `(scope_id, key)`, last write wins), provenance
  (author, agent, session, classification). `scope_id` comes from the tool
  config, never from model arguments.
- **`feat/llm-response-metadata`:** non-standard completion fields and the
  response id reach the message metadata (`llm_response`). The routing
  explanation is fetched **server side** after the call, with the caller's
  identity (`IdentityForwarder`), and attached as `llm_response.routing`; the
  browser never calls the gateway (it has no path to it and no JWT).
- **`feat/rate-limit-ux`:** HTTP 429 becomes `LLMRateLimitError`, carried as a
  structured `metadata.error {type, message, retry_after}` (no text marker);
  configurable `max_retries`/`timeout_seconds`, a 429 is never retried by the
  SDK. Non-fatal notice in the chat UI.

## Decisions taken

- Memory is extended in UnifAI (Mongo + Qdrant), behind ports, rather than
  delegated to OGX or Feast: neither documents a per-scope key/value store or
  access control. Remaining increments: LLM extraction node (local model for
  C2/C3), fail-closed scope membership check fed by the platform.
- Routing explanation: server-side embed (no CORS, no new proxy, token never
  in the browser). A thin authorised relay in multi-agent stays the fallback
  for past sessions.
- Per-agent route and sheet: needs group gating and an object-level
  authorisation audit in UnifAI first (ADR-0564 `EntitlementUnsupported`).
  Recorded as ADR-0582 (entry and sheet), ADR-0583 (prerequisites) and
  ADR-0584 (lifecycle, roles, revocation), all Proposed. Signing authority is
  settled by ADR-0578. Not started.

## Live proof (demo333, 2026-10-22, fork devel `e76c71cd0`)

Run on the pilot stack with throwaway objects (all removed afterwards), two
personas in a team workspace and one outside it:

- **Routing explanation:** the LLM element sends `X-Zuno-Request-Id` and
  fetches the gateway's decision server side; the message carries
  `llm_response.routing` (class, kind, provider, model, fallback) and
  `request_id`.
- **Rate limit:** a real HTTP 429 with `Retry-After: 7` from a throwaway
  server gives `metadata.error = {type: rate_limited, retry_after: 7}` on the
  message and the `agent_error` stream event, one request only (no SDK retry),
  the run completes. The ai-gateway now sends `Retry-After` on a quota 429.
- **Memory tool:** an agent calls `set_fact` and `write` (also both in one
  response), recalls the fact in a second session; a non-member is refused at
  the workspace and at the tool (`access.mode: team`, fail closed).
- **Extraction node:** `memory_extractor` writes validated facts and memories
  with provenance; a restricted classification without a local model writes
  nothing.
- **Distributed mode:** resources referenced by plain id reach the worker; a
  plain id without a config is refused at save time with a `$ref:<id>` hint.
- **Failure handling:** a session whose elements cannot be built ends FAILED
  with a structured `session_build_failed` error (run, stream and submit), no
  element configuration in any response, a chat message carrying the error, and
  the session can be run again.
- **Group-bound teams:** a team whose member is the group `agent_tekos` admits
  a second user through the verified token claim and refuses a user outside the
  group (identity `oidc-claims`, ADR-0583 clause 1).
- **UI build:** `vite build` passes with Node 20 (podman `node:20`, README.md of
  the repository root provided; the workstation's Node 16 is too old).

## Browser check (demo333, 2026-10-23, Playwright, bundles of release v0.1.1)

A real login as ai-ops-01 in team `agent-tekos`, chat with the `tekos` workflow
in the Collaboration Hub:

- The first run showed no routing information: the answers of bundle agents had
  empty message metadata (`{}`), because the LLM elements of the unifai chart did
  not send a request id nor ask for the routing decision. Fixed in the chart
  (zuno-demo `c5123c1a`, `gatewayLLM.routingLookup`): the message now carries
  `llm_response.routing` (class C2, provider `ovhcloud-gpt-oss-120b`, model
  `gpt-oss-120b`, no fallback), fetched from the ai-gateway's
  `/v1/routing-decisions/{id}`.
- With it, the chat shows the response badge under the final answer
  (`gpt-oss-120b`, collapsed); the expanded "Why this model" panel was not
  captured.
- A "Request failed with status 404" notice sat over the live workflow graph:
  the graph hook asked for the blueprint without the team id on the first render
  of a team workspace (the team is not resolved yet) and that stale request's
  error was shown after the second request had succeeded. Fixed in the fork (UI
  hook ignores a cancelled run, devel `777cccde4`, `vite build` and the type
  check pass); it needs a UI image to be seen fixed on the cluster.

## Not verified

- The rate-limit notice in a browser (a real 429 needs an exhausted budget;
  consultant-01's budget was not exhausted when tried), and the expanded
  "Why this model" panel.
- The memory tool against Qdrant with a large corpus, and the embedding model
  under load (functional checks only).
- The Temporal worker path for a build failure beyond the unit tests.

## Follow-ups

- Emit the group-bound `teamId` from the AgentBundle in the operator and chart
  (WP-154 / WP-155) instead of the hand-made pilot team.
- The per-agent entry and sheet: ADR-0582 to ADR-0584, Proposed.
- Is UnifAI's agent repository enough for per-agent landing pages? No: it is a
  generic element browser with no stable per-agent URL (see ADR-0582).
- The MaaS front answers 503 to most calls for the large local model under
  load; each costs a retry and a fallback hop (WP-157).
