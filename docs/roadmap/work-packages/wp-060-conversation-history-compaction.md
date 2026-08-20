# WP-060: Carry conversation history into agent prompts with budgeted compaction

- **State:** Operator pending (repo work merged)
- **ADRs:** ADR-0215 (Proposed -> Partially implemented -> Implemented)
- **Depends on:** WP-08 (checkpointing, merged), WP-30 (multi-shape runtime, merged), WP-31/WP-33 (Arkos/Comage slices, merged)
- **Blocks:** none
- **Estimated files touched:** ~18

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Make Tekos, Comage and Arkos genuinely multi-turn: reconstruct conversation
history server-side from the LangGraph checkpoints ADR-0103 already
persists, inject a token-budgeted window of it into every model call, and
auto-compact older turns into a running summary when the budget is
exceeded - without changing the frontend/BFF wire contract.

## ADR references

Primary: [docs/adr/0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md](../../adr/0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md)

Acceptance criteria: a fact stated in turn 1 is used correctly in turn 2 on
the same `run_id`, for Tekos and Arkos, streaming and non-streaming; a
forced small `token_budget` produces a summary plus exactly `max_turns`
verbatim turns under budget; a `history_classification` of C3 routes the
summarization call local-only only (security-negative); a summarization
outage still lets the user's turn succeed via sliding-window degradation;
no summary tokens ever appear in an SSE stream; the transcript endpoint's
output is unchanged.

## Preconditions (verify before starting)

- `components/agent-runtime/.venv` exists, built from that component's own
  `requirements.txt` (not system/user-site python - see this repo's own
  test-venv convention).
- `python3 platform/docs/check_docs.py` exits with only the pre-existing
  ADR-0212/ADR-0214 status drift (see WP-057/058/059) - confirm no new
  drift before you start.
- Read fully before editing: `components/agent-runtime/app/graph/state.py`,
  `app/graph/nodes.py` (`_make_reason_node`, `_escalate`),
  `app/graph/arkos_nodes.py` (`draft_node`), `app/main.py`
  (`_initial_state`, `_resolve_run_id`, `_build_transcript_structured`,
  `_stream_chat`, `agent_chat`), `app/registry.py` (`zuno.rag.top_k`
  parsing, for the pattern to follow), `app/clients/model_router.py`
  (`invoke_with_fallback`), `app/memory.py` (the C2/C3 local-only routing
  precedent this WP mirrors), and both
  `app/graph/shapes/{retrieve_reason_respond,plan_draft_write}.py`.

## Repo changes (step by step)

1. **`components/agent-runtime/app/graph/state.py`**: add `history: List[Dict[str, str]]`,
   `summary: str`, `history_classification: str` to `AgentState`, each with
   an ADR-0215 comment explaining why it is explicitly managed (not a
   reducer channel) and why it is safe on resume (`_initial_state` never
   touches these keys).
2. **`components/agent-runtime/app/graph/history.py` (new)**:
   `estimate_tokens(text) -> int` (char/4 heuristic), `append_turn(history,
   message, reply, max_entry_chars=4000) -> list`, `build_history_messages(history,
   token_budget, summary) -> List[BaseMessage]` (newest-to-oldest walk,
   deterministic hard cap), the compaction system prompt constant, `async
   def compact(model_router, summary, folded_turns, classification,
   local_only_required, bearer_token, request_id, agent_name, task_name) ->
   str` (routes per ADR-0034/0035, mirroring `app/memory.py:61`, tags the
   call `zuno-internal`, raises `ModelRouterError` upward - caller
   degrades), and `make_history_node(agent, task, model_router)` - the
   `record_history` node factory: appends the turn, escalates
   `history_classification` via `nodes.py`'s `_escalate`, triggers
   `compact()` when `estimate_tokens(summary + history) > token_budget and
   len(history) > 2 * max_turns`, catches `ModelRouterError` to degrade to
   a sliding window and append a `history_compaction:` entry to `errors`.
3. **`app/graph/nodes.py`**: in `_make_reason_node`, build the system
   message as `task.prompt` plus the delimited summary heading when
   `state.get("summary")` is set, and expand `messages` to `[system,
   *build_history_messages(state.get("history", []), agent.history_token_budget,
   state.get("summary", "")), human]` - the current-turn `human` message's
   `Context:...\n\nQuestion:` shape stays byte-identical to today.
4. **`app/graph/arkos_nodes.py`**: identical injection in `draft_node`,
   reading `_ARKOS.history_token_budget`/`_ARKOS.history_max_turns` (module
   singletons, matching this file's existing pattern - no factory
   conversion needed, only `plan_draft_write.py`'s `record_history`
   instantiation needs `(agent, task)`, both already threaded through
   `build()`).
5. **Shape wiring**: `app/graph/shapes/retrieve_reason_respond.py` adds
   `graph.add_node("record_history", make_history_node(agent, task,
   _model_router))` and rewires `respond -> record_history -> END`.
   `app/graph/shapes/plan_draft_write.py` does the same with
   `write -> record_history -> END`, using its `agent`/`task` params
   (currently unused there per that file's own docstring - now used).
6. **`app/clients/model_router.py`**: add optional `tags:
   Optional[List[str]] = None` to `invoke_with_fallback`, passed as
   `config={"tags": tags}` to `model.ainvoke` when set; `None`/omitted
   keeps today's exact call shape for every existing caller.
7. **`app/main.py`**: in `_stream_chat`, skip `on_chat_model_stream` events
   whose `event.get("tags")` contains `"zuno-internal"` (no `token` SSE
   frame for those). In `agent_chat`'s resume path, when the resolved
   `run_id` already had a checkpoint (i.e. this is not a fresh mint) and
   its stored `channel_values` lack a `history` key, seed
   `initial_state["history"]` once from `_build_transcript_structured`
   (capped by the same per-entry limit) and
   `initial_state["history_classification"]` from the stored
   `effective_classification` escalated against the agent baseline.
8. **`app/registry.py`**: parse `zuno.memory.history.{enabled, max_turns,
   token_budget}` into new `AgentDefinition` fields
   (`history_enabled: bool = True`, `history_max_turns: int = 6`,
   `history_token_budget: int`, defaulting from env `HISTORY_TOKEN_BUDGET`
   or `1800`), following `zuno.rag.top_k`'s existing parse-with-default
   style. Apply the `ZUNO_HISTORY_DISABLED=true` env kill switch by
   forcing `history_enabled=False` regardless of bundle content.
9. **`platform/okf/schema/zuno-okf-v0.2.schema.json`**: add an optional
   `memory` property (with a nested `history` object: `enabled` boolean,
   `max_turns`/`token_budget` integers) to the `zuno` block, which is
   `additionalProperties: false` today.
10. **`agents/arkos/agent.okf.md`**: add an explicit `zuno.memory.history`
    block with a larger `token_budget` (Arkos routes local-only to
    gpt-oss-20b's 32768-token context). Leave `agents/tekos` and
    `agents/comage` on defaults (no bundle edit needed).
11. **Tests**: new `components/agent-runtime/tests/test_history.py`
    covering: two-turn prompt content (turn 2's captured `messages`
    contain turn 1's user text as `HumanMessage` and reply as `AIMessage`
    before the final human message, `messages[0]` still the system
    prompt - no existing test asserts this); compaction trigger under a
    tiny forced budget; summarization failure degrading to sliding window
    without failing the user turn; the security-negative classification
    routing assertion (`local_only=True`, `classification="C3"`,
    `tags=["zuno-internal"]`); monotonic `history_classification` across a
    C2-then-C1 turn sequence; the prompt-build hard cap on oversized
    history; resume of a checkpoint lacking `history` (backfill path);
    `estimate_tokens`/entry-cap unit checks. Add a two-turn assertion to
    `tests/test_arkos_nodes.py`. Add a tagged-stream-event filter test to
    `tests/test_checkpoint_retry.py`. Re-run
    `test_checkpointing.py::test_transcript_has_no_duplicate_turns_across_multiple_checkpoints`
    unchanged (the extra `record_history` super-step must not duplicate
    turns in the reconstructed transcript). Verify
    `test_project_memory_e2e.py`'s `fake_invoke` (dispatches on
    `messages[0].content`) still matches - its sessions use distinct
    `run_id`s so `summary` stays empty and the system text is unchanged.
12. **Evaluation**: ADR-0027 fixes Tekos's suite at exactly twenty
    scenarios, so a new 21st scenario is not available - instead extend
    existing scenario 7 (`chat_basic_qa`,
    `evaluations/tekos/scenarios.yaml`) with an optional `follow_up`
    field; its handler in `evaluations/tekos/run_scenarios.py` sends the
    follow-up on the SAME `run_id` the first turn returned and asserts
    the resumed turn still completes with a non-empty reply - the live
    proof that resume + history-carrying works end to end. Deeper
    semantic-recall assertions belong in
    `components/agent-runtime/tests/test_history.py`'s prompt-content
    tests (step 11), which a scripted smoke check with no LLM judge
    cannot itself make.
13. **Do NOT fix unrelated drift found along the way** (WP-057/058/059
    convention) - in particular, leave the pre-existing ADR-0212/ADR-0214
    index-status drift untouched; it is out of scope here.

## What NOT to touch

- `_resolve_run_id`'s ownership/fail-closed semantics.
- `_build_transcript_structured`'s grouping logic or its two existing
  callers' behavior.
- The `conversations`/`conversation_stars` tables, schema, or endpoints
  (ADR-0212) - metadata-only stays metadata-only.
- `app/memory.py`'s extraction path or its endpoint.
- Decision text of any existing ADR.
- Any file another concurrent session is actively editing - re-check
  `git status` before staging (multiple sessions may be active on this
  repo).

## Acceptance checks (run from repo root; all must pass)

- `cd components/agent-runtime && .venv/bin/python3 tests/test_history.py && .venv/bin/python3 tests/test_checkpointing.py && .venv/bin/python3 tests/test_arkos_nodes.py && .venv/bin/python3 tests/test_project_memory_e2e.py && .venv/bin/python3 tests/test_checkpoint_retry.py && .venv/bin/python3 tests/test_graph_factory.py`
- `python3 platform/supply-chain/validate_okf_bundle.py agents/tekos agents/comage agents/arkos` → `RESULT: PASS`
- `python3 platform/okf/generate_authorization_matrix.py --check --all` → `RESULT: PASS` (memory config must not alter any authorization matrix)
- `python3 platform/docs/check_docs.py` → only the pre-existing ADR-0212/ADR-0214 drift, nothing new

## Operator / human follow-up

Live two-turn verification on the real cluster, one conversation per
agent (Tekos, Comage, Arkos): state a fact turn 1, confirm it is used
correctly turn 2 on the same `run_id`, both via the UI and via a raw
`run_id`-resume API call. Optionally raise `HISTORY_TOKEN_BUDGET` via
`gitops/charts/agent-runtime/values.yaml` once real conversation lengths
and the gpt-oss-20b routing share are observed in production traffic.

## Status updates (then re-run check_docs.py)

- `docs/adr/0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md`:
  `Status:` line -> `Partially implemented (2026-08-20)` done, enumerating
  the residual live-cluster verification gap (ADR-0115 gap-list pattern);
  flips to `Implemented (<date>)` once that verification actually happens,
  the same evidence-prose convention ADR-0212's status line uses.
- `docs/adr/README.md`: ADR-0215 row -> `Partially implemented` done;
  -> `Implemented` once the operator step above closes.
- `docs/roadmap/v0.1-v0.3-implementation-roadmap.md`: WP-060 tracker row ->
  `Operator pending (repo work merged)` done; add a one-line scope note
  next to the existing "later additions" note (ADR-0119/0120/0121)
  recording ADR-0215 as a fourth later addition - done.
- `MEMORY.md`: one dated bullet describing multi-turn history + compaction
  as implemented state, across which agents, and the residual operator
  gap - done.

## Out of scope / deferred

- Cross-conversation/shared memory (ADR-0404, v0.4 stub) - this WP is
  strictly within-conversation continuity.
- Any frontend/BFF change - the wire contract (`{session_id, message,
  run_id?}`) is unchanged by design.
- Exact tokenization (`tiktoken` or a model-specific tokenizer) - the
  character heuristic is a deliberate, documented approximation.
- Backfilling history for conversations that are archived and never
  resumed again.
- A third agent adopting this mechanism (none exists yet beyond
  Tekos/Comage/Arkos).
