# ADR-0569: Close UnifAI parity gaps generically

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md) (adopt UnifAI as the agent platform)
- **Related:** [ADR-0209](0209-introduce-project-scoped-agent-memory.md), [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md), [ADR-0527](0527-introduce-the-project-as-the-sharing-and-context-boundary.md), [ADR-0544](0544-bound-every-model-call-at-both-ends.md), [ADR-0550](0550-demonstrate-sovereign-ai-through-classification-specialization-and-resilience.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

ADR-0561's parity table assigns several agent-runtime capabilities to "ADR-0569
addition". Each one is missing from UnifAI as read on the fork's `devel`
branch:

- **Project memory.** ADR-0209 and ADR-0527 give agents durable,
  cross-session, cross-agent facts scoped to a project. The runtime extracts
  them at a checkpoint (`POST /v1/agents/{agent}/runs/{run_id}/extract-memory`,
  `components/agent-runtime/app/main.py:447`), stores them through rag-service
  `/v1/project-memory/write`, and retrieves them fail-closed on project
  membership. UnifAI has no memory element:
  `multi-agent/lib/mas/elements/` holds `conditions`, `llms`, `nodes`,
  `providers`, `retrievers`, `sandboxes` and `tools` only.
- **History budget.** ADR-0215 injects history under a per-agent token budget
  (default 1800 estimated tokens, `max_turns` 6) and folds older turns into a
  running summary. That summary call is classification-aware and never
  streamed (`components/agent-runtime/app/graph/history.py`). UnifAI's
  `custom_agent` injects the last 20 workspace messages with no token
  estimate and no summary
  (`multi-agent/lib/mas/elements/nodes/custom_agent/custom_agent.py:208`). The
  local models' windows are narrow enough that ADR-0544 had to clamp prompts.
- **Routing metadata.** ADR-0550 clause 9 requires each response to expose the
  real routing decision: agent, task, project, effective classification,
  model, provider, local/external, fallback and reason. The ai-gateway returns
  `zuno_provider` on every completion (`components/ai-gateway/app/schemas.py:84`)
  and serves `GET /v1/routing-decisions/{request_id}`
  (`components/ai-gateway/app/main.py:362`). UnifAI's LLM elements surface
  neither, and a search of `multi-agent/lib/mas/elements/llms/` finds no
  response-metadata passthrough.
- **Quota exhaustion.** The ai-gateway answers an exhausted budget with an
  explicit 429 (`components/ai-gateway/app/main.py:289-292`). In UnifAI,
  `RateLimitError` is caught only in the connection validators
  (`multi-agent/lib/mas/elements/llms/openai_compatible/validator.py:107`).
  A search of `ui/client/src` finds no 429 handling.
- **Agent tiles.** The Zuno portal shows one tile per entitled agent, built
  from OKF `zuno.ui` (`components/agent-frontend/internal/portal/portal.go`,
  `BuildTiles`). UnifAI's UI has an agent repository page
  (`ui/client/src/pages/AgentRepository.tsx`, a workspace of resource
  elements) and a template catalog (`AgenticTemplates.tsx`). Neither
  filters by Keycloak group, as far as was read (**unverified**).

## Decision

**Every gap is closed by a generic, configurable UnifAI change, off by default
or defaulting to today's upstream behavior.** Each one is built as an
isolated commit on a branch from `main` and proposed upstream (ADR-0575).
Zuno-specific values (URLs, header names, budgets) are set by
`unifai-operator` from OKF (ADR-0564) or `UnifaiStack`, never hard-coded in
the change.

**1. A memory element: scoped, durable facts on UnifAI storage.** A new
element category provides `memory.write` (an extraction step) and
`memory.read` (injection as background context). A memory record carries
`scope_id`, author, agent, session, timestamp, `classification`,
`acl_groups`, content and metadata. These are the ADR-0209 record fields with
`project_id` generalized to `scope_id`. Storage is MongoDB for structured
state and a Qdrant collection for semantic recall, both UnifAI's own.
pgvector is not used (ADR-0568). Writes are explicit extraction (at session
end or on an explicit action), never verbatim turns.

- **Access fails closed.** A read or write without resolved scope membership
  is denied. Membership comes from UnifAI's team workspaces
  (`multi-agent/lib/mas/collaboration/`), so a Zuno project maps to a UnifAI
  team.
- **Grant model, unverified.** Whether team roles can express ADR-0527's
  read/write/clone/admin grants and its last-admin guard is **unverified**.
  The pilot answers it (ADR-0573). A shortfall is added here generically, or
  recorded as a residual.
- **Classification is inherited, never lowered.** A record's classification
  is the session's classification (ADR-0565). The extraction call runs with
  that classification in ADR-0563's headers, so the ai-gateway keeps C2/C3
  local.

**2. A token-budgeted history window with summary compaction in agent
nodes.** The agent node config gains `history.max_messages` (default 20,
today's value), an optional `history.token_budget` and `history.compaction`
(`none` by default, or `summary`).

- **Compaction.** With `summary`, the turns that overflow the budget are
  folded into a running summary stored in the session. The summary call uses
  the node's own LLM element and is tagged internal, so it is never emitted
  on the stream. The summary enters the system message as delimited
  background, never as instructions.
- **Failure.** A failed compaction degrades to the sliding window and is
  recorded, never failing the turn. This is ADR-0215's design, made generic.
- **Values.** The operator sets the budget from OKF `zuno.memory.history`.
  The ai-gateway pre-flight skip (ADR-0544 clause 5) stays the backstop when
  the estimate is wrong.

**3. LLM response metadata, passed through and displayable.** The
`openai_compatible` element keeps non-standard top-level response fields and a
configured allowlist of response headers on the assistant message as
`response_metadata`. An optional `metadata_lookup_url` template (for example
`{base_url}/routing-decisions/{header:X-Zuno-Request-Id}`) lets the UI fetch a
detailed record on demand. The UI renders `response_metadata` as an
expandable panel on the message. For Zuno, the operator configures the
template and the field allowlist so ADR-0550 clause 9's fields appear. The
UI computes nothing: it shows what the gateway decided.

**4. Rate-limit errors become a first-class, user-visible outcome.** At run
time, the LLM elements map HTTP 429 to a typed rate-limit error that carries
the response body's detail and `Retry-After`. The session ends that turn with
a distinct status and message ("quota exhausted, retry after ..."), never as
a generic failure. No silent retry is made beyond one bounded retry honoring
`Retry-After`, when configured. The UI shows the message and the retry time.

**5. Agent tiles become UnifAI catalog entries with group-gated visibility.**
The operator maps OKF `zuno.ui` (`displayName`, `tileDescription`, `color`,
`icon`) to `UnifaiTemplate` metadata (ADR-0564). The Zuno portal is not
rebuilt. If UnifAI cannot restrict a template or workflow to Keycloak groups,
this ADR adds a generic `visible_to_groups` read from the identity's `groups`
claim. That is UX only: enforcement stays server-side at the gateways
(ADR-0563). Citation rendering for retriever results is added under the same
rule if the pilot shows it missing.

## Planned supersession

At cutover (WP-156), per `docs/adr/README.md` "How a decision changes":

- **In full:** ADR-0215 (its design migrates into clause 2); ADR-0209 (its
  record shape, extraction rule, fail-closed membership and classification
  inheritance migrate into clause 1).
- **In part: ADR-0527.** Only clauses 1, 8 and 9 are retired: the
  `projects` tables in `agent-conversations`, the `project_memberships`
  projection, and the agent-frontend UI. Clauses 2-7 remain its own
  decisions, now implemented over UnifAI team workspaces and clause 1's
  memory element:
  - clauses 2 and 3, the roles and the last-admin guard, as far as the pilot
    proves team roles express them;
  - clause 5, the project context as background, which ADR-0565 also keeps.
- **Not superseded:** ADR-0550 clause 9 still stands, and clause 3 is its new
  implementation. ADR-0544 is handled by ADR-0561.

## Consequences

The parity gaps close in UnifAI itself, not in a Zuno side-car, so later
upstream releases carry them and Zuno has no agent-layer code left to
maintain. Each change has a default that leaves upstream behavior untouched,
which is the condition for upstream acceptance. If upstream declines a
change, it lives on `devel` and its rebase cost on `main` is bounded by
ADR-0575's isolation rule.

Project memory moves from pgvector to Qdrant and MongoDB. Existing
`knowledge.project` content is migrated with ADR-0568's RAG migration or
dropped, decided per project before cutover.

## Security considerations

The memory element is a new store of user-derived content. It fails closed
on scope membership, inherits classification, and is never readable across
scopes. Response metadata passes only allowlisted fields and headers, so a
provider error body or an internal header never reaches the browser by
default. The rate-limit message shows the gateway's detail, which must not
reveal another tenant's usage. The gateway already returns per-caller
detail. `visible_to_groups` is not an authorization control, and any review
that treats it as one is wrong.

## Operational considerations

Each clause has its own acceptance in WP-148:

- **Clause 1.** A fact written in a Tekos session is recalled in a new
  session and by Arkos, and a non-member is refused. This is ADR-0209's
  scenario.
- **Clause 2.** With a small budget, the captured prompt holds the summary
  plus the window, and a C3 session's summary call reaches the gateway
  marked C3.
- **Clause 3.** The panel shows the provider the gateway actually used.
- **Clause 4.** A forced quota exhaustion shows a clean message.

Langfuse and OpenTelemetry (ADR-0566) record compaction and memory calls as
internal spans.
