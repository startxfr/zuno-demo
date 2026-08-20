#!/usr/bin/env python3
"""ADR-0215 tests for conversation history carried into agent prompts with
budgeted compaction: app/graph/history.py's pure helpers, the two-turn
prompt-content regression this ADR fixes (no prior test exercised a
second turn's actual model-call payload), compaction triggering/failure
degradation, the ADR-0034/ADR-0035 classification-routing security
negative, and pre-ADR-0215 checkpoint resume/backfill.

Same MemorySaver + monkeypatched-ModelRouter style as
tests/test_project_memory_e2e.py - no live AI Gateway needed.

Run directly:

    cd components/agent-runtime && python3 tests/test_history.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml")
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from app.clients.model_router import ModelRouterError, ProviderCandidate  # noqa: E402
from app.graph import history as history_mod  # noqa: E402
from app.graph.arkos_nodes import _ARKOS, _DRAFT_TASK  # noqa: E402
from app.graph.arkos_nodes import _model_router as _arkos_model_router  # noqa: E402
from app.graph.nodes import _ANSWER_TASK, _TEKOS, _model_router  # noqa: E402
from app.graph.shapes.plan_draft_write import build as _build_arkos  # noqa: E402
from app.graph.shapes.retrieve_reason_respond import build as _build  # noqa: E402
from app.main import _seed_history_backfill  # noqa: E402


def build_graph(checkpointer):
    return _build(checkpointer, _TEKOS, _ANSWER_TASK)


def build_arkos_graph(checkpointer):
    return _build_arkos(checkpointer, _ARKOS, _DRAFT_TASK)


class _FakeModelResult:
    def __init__(self, content: str):
        self.content = content


_BASE_STATE = {
    "session_id": "s1",
    "user_sub": "alice",
    "groups": ["consultant"],
    "bearer_token": "t",
    "request_id": "req-1",
    "retrieved_docs": [],
    "tool_results": {},
    "errors": [],
}


def _state(message: str) -> dict:
    state = dict(_BASE_STATE)
    state["message"] = message
    return state


# --------------------------------------------------------------------------
# Pure-function unit tests (no graph/model involved)
# --------------------------------------------------------------------------


def test_estimate_tokens_is_a_char_over_four_heuristic() -> None:
    assert history_mod.estimate_tokens("") == 0
    assert history_mod.estimate_tokens("abcd") == 2  # 4//4 + 1
    assert history_mod.estimate_tokens("a" * 40) == 11  # 40//4 + 1


def test_append_turn_returns_a_new_list_and_caps_long_entries() -> None:
    history = [{"role": "user", "content": "first"}]
    appended = history_mod.append_turn(history, "second question", "second reply")
    assert history == [{"role": "user", "content": "first"}], "must not mutate the input list"
    assert appended == [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "second reply"},
    ]

    huge = "x" * (history_mod.HISTORY_ENTRY_MAX_CHARS + 500)
    capped = history_mod.append_turn([], huge, "")
    assert len(capped[0]["content"]) == history_mod.HISTORY_ENTRY_MAX_CHARS
    assert capped[0]["content"].endswith("…")


def test_build_history_messages_converts_roles_to_proper_message_types() -> None:
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]
    messages = history_mod.build_history_messages(history, token_budget=1000)
    assert [type(m) for m in messages] == [HumanMessage, AIMessage]
    assert [m.content for m in messages] == ["q1", "a1"]


def test_build_history_messages_hard_cap_keeps_newest_turns_under_budget() -> None:
    """Belt-and-braces backstop: even an un-compacted, oversized history
    must fit the budget at prompt-build time, keeping the most recent
    turns and dropping the oldest."""
    history = [{"role": "user", "content": f"turn {i} " + "x" * 40} for i in range(20)]
    messages = history_mod.build_history_messages(history, token_budget=50)
    assert len(messages) < len(history), "an oversized history must be truncated"
    assert messages[-1].content == history[-1]["content"], "the newest turn must always be kept"
    total = sum(history_mod.estimate_tokens(m.content) for m in messages)
    assert total <= 50 or len(messages) == 1, "must respect budget except for a single always-kept newest turn"


def test_build_history_messages_always_keeps_at_least_the_newest_turn() -> None:
    history = [{"role": "user", "content": "x" * 4000}]
    messages = history_mod.build_history_messages(history, token_budget=1)
    assert len(messages) == 1, "a single oversized turn must still be included, not dropped entirely"


def test_history_from_transcript_keeps_only_user_and_assistant_roles() -> None:
    transcript = [
        {"role": "user", "content": "hi", "ts": "t1"},
        {"role": "assistant", "content": "hello", "ts": "t2"},
        {"role": "system", "content": "should be ignored", "ts": "t3"},
    ]
    history = history_mod.history_from_transcript(transcript)
    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


# --------------------------------------------------------------------------
# Two-turn prompt content - the core regression this ADR fixes
# --------------------------------------------------------------------------


async def test_second_turn_prompt_carries_the_first_turns_history() -> None:
    """Before ADR-0215, reason_node sent only [system, human] every turn -
    no test asserted on a SECOND turn's actual message list, which is
    exactly how this bug shipped unnoticed. This proves turn 2's captured
    `messages` contains turn 1's user text as a HumanMessage and turn 1's
    reply as an AIMessage, positioned before the final (current-turn)
    human message, with the system prompt still first."""
    graph = build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "run-two-turn"}}

    captured_calls = []

    async def fake_invoke(**kwargs):
        captured_calls.append(kwargs)
        return _FakeModelResult(f"reply #{len(captured_calls)}"), ProviderCandidate(name="ai-gateway")

    saved_invoke = _model_router.invoke_with_fallback
    _model_router.invoke_with_fallback = fake_invoke
    try:
        await graph.ainvoke(_state("What is OpenShift AI?"), config=config)
        await graph.ainvoke(_state("And how does it differ from vanilla OpenShift?"), config=config)
    finally:
        _model_router.invoke_with_fallback = saved_invoke

    assert len(captured_calls) == 2
    turn2_messages = captured_calls[1]["messages"]

    assert isinstance(turn2_messages[0], SystemMessage), "system prompt must still be first"
    assert isinstance(turn2_messages[-1], HumanMessage)
    assert "And how does it differ" in turn2_messages[-1].content

    history_messages = turn2_messages[1:-1]
    assert any(
        isinstance(m, HumanMessage) and m.content == "What is OpenShift AI?" for m in history_messages
    ), f"turn 1's question missing from turn 2's prompt: {[m.content for m in history_messages]}"
    assert any(
        isinstance(m, AIMessage) and m.content == "reply #1" for m in history_messages
    ), f"turn 1's reply missing from turn 2's prompt: {[m.content for m in history_messages]}"

    # And turn 1's own prompt had no history yet - byte-identical to the
    # pre-ADR-0215 [system, human] shape.
    turn1_messages = captured_calls[0]["messages"]
    assert len(turn1_messages) == 2


async def test_arkos_second_turn_prompt_carries_the_first_turns_history() -> None:
    """ADR-0215 applies identically to Arkos's structurally different
    plan_draft_write shape (draft_node, not reason_node) - a follow-up
    like "make it shorter" must see the document just drafted."""
    from app.graph import arkos_nodes

    graph = build_arkos_graph(MemorySaver())
    config = {"configurable": {"thread_id": "run-arkos-two-turn"}}

    captured_calls = []

    async def fake_invoke(**kwargs):
        captured_calls.append(kwargs)
        return _FakeModelResult(f"draft #{len(captured_calls)}"), ProviderCandidate(name="ai-gateway")

    async def fake_search(**kwargs):
        return []

    saved_invoke = arkos_nodes._model_router.invoke_with_fallback
    saved_search = arkos_nodes.search
    arkos_nodes._model_router.invoke_with_fallback = fake_invoke
    arkos_nodes.search = fake_search
    try:
        base = {
            "session_id": "s1", "user_sub": "alice", "groups": ["consultant"], "bearer_token": "t",
            "request_id": "req-1", "retrieved_docs": [], "tool_results": {}, "errors": [],
        }
        await graph.ainvoke({**base, "message": "draft a DAT for the OpenShift AI GPU sizing project"}, config=config)
        await graph.ainvoke({**base, "message": "make section 2 shorter"}, config=config)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved_invoke
        arkos_nodes.search = saved_search

    # ADR-0416: each turn now makes two model_router calls - draft_node,
    # then reflect_node's self-review pass over that draft (which is what
    # actually becomes document_draft/reply, since reflect runs last) -
    # so 2 turns produce 4 captured calls, and turn 2's draft prompt is
    # captured_calls[2], not [1].
    assert len(captured_calls) == 4
    turn2_messages = captured_calls[2]["messages"]
    history_messages = turn2_messages[1:-1]
    assert any(
        isinstance(m, HumanMessage) and "GPU sizing project" in m.content for m in history_messages
    ), f"turn 1's request missing from turn 2's draft prompt: {[m.content for m in history_messages]}"
    assert any(
        isinstance(m, AIMessage) and m.content == "draft #2" for m in history_messages
    ), f"turn 1's reflected draft missing from turn 2's prompt: {[m.content for m in history_messages]}"


# --------------------------------------------------------------------------
# Compaction trigger + failure degradation
# --------------------------------------------------------------------------


async def test_compaction_triggers_under_a_small_budget_and_folds_old_turns() -> None:
    config = {"configurable": {"thread_id": "run-compaction"}}

    # Tiny budget/max_turns forces compaction well before a real
    # conversation would - monkeypatch the module-level AgentDefinition
    # fields the same way test_checkpointing.py monkeypatches main_module
    # constants, restored in `finally`. MUST happen BEFORE build_graph():
    # make_history_node's closure reads agent.history_token_budget/
    # history_max_turns once, at graph-build time, not per-invocation.
    saved_budget, saved_max_turns = _TEKOS.history_token_budget, _TEKOS.history_max_turns
    _TEKOS.history_token_budget = 20
    _TEKOS.history_max_turns = 1
    graph = build_graph(MemorySaver())

    summarize_calls = []

    async def fake_invoke(**kwargs):
        messages = kwargs.get("messages") or []
        system_text = messages[0].content if messages else ""
        if "running summary" in system_text:
            summarize_calls.append(kwargs)
            return _FakeModelResult("Summary: discussed OpenShift AI basics."), ProviderCandidate(name="ai-gateway")
        return _FakeModelResult("a reasonably long reply about the platform"), ProviderCandidate(name="ai-gateway")

    saved_invoke = _model_router.invoke_with_fallback
    _model_router.invoke_with_fallback = fake_invoke
    try:
        for i in range(4):
            await graph.ainvoke(_state(f"question number {i} about the platform"), config=config)
    finally:
        _model_router.invoke_with_fallback = saved_invoke
        _TEKOS.history_token_budget = saved_budget
        _TEKOS.history_max_turns = saved_max_turns

    assert summarize_calls, "compaction never triggered under a forced-small budget"
    tuple_ = await graph.checkpointer.aget_tuple(config)
    channel_values = tuple_.checkpoint.get("channel_values") or {}
    assert channel_values.get("summary"), "summary channel was not populated"
    assert len(channel_values.get("history", [])) <= 2, "history was not trimmed after compaction"


async def test_compaction_failure_degrades_to_sliding_window_without_failing_the_turn() -> None:
    config = {"configurable": {"thread_id": "run-compaction-failure"}}

    # See the ordering note in the previous test - must patch before
    # build_graph().
    saved_budget, saved_max_turns = _TEKOS.history_token_budget, _TEKOS.history_max_turns
    _TEKOS.history_token_budget = 20
    _TEKOS.history_max_turns = 1
    graph = build_graph(MemorySaver())

    async def failing_invoke(**kwargs):
        messages = kwargs.get("messages") or []
        system_text = messages[0].content if messages else ""
        if "running summary" in system_text:
            raise ModelRouterError("gateway unreachable")
        return _FakeModelResult("a reasonably long reply about the platform"), ProviderCandidate(name="ai-gateway")

    saved_invoke = _model_router.invoke_with_fallback
    _model_router.invoke_with_fallback = failing_invoke
    try:
        final = None
        for i in range(4):
            final = await graph.ainvoke(_state(f"question number {i} about the platform"), config=config)
    finally:
        _model_router.invoke_with_fallback = saved_invoke
        _TEKOS.history_token_budget = saved_budget
        _TEKOS.history_max_turns = saved_max_turns

    assert final["reply"], "the user's own turn must still succeed despite a compaction failure"
    assert any(e.startswith("history_compaction:") for e in final.get("errors", [])), final.get("errors")
    assert len(final.get("history", [])) <= 2, "must still degrade to a sliding window on failure"


# --------------------------------------------------------------------------
# Security-negative: classification routing of the compaction call
# --------------------------------------------------------------------------


async def test_compaction_call_is_local_only_for_a_c3_conversation() -> None:
    """ADR-0034/ADR-0035, mirroring app/memory.py:extract_memory - a
    summary of C2/C3 conversation content must never be eligible for a
    SaaS provider."""
    saved_budget, saved_max_turns = _TEKOS.history_token_budget, _TEKOS.history_max_turns
    _TEKOS.history_token_budget = 20
    _TEKOS.history_max_turns = 1

    captured = {}

    async def fake_invoke(**kwargs):
        captured.update(kwargs)
        return _FakeModelResult("a summary"), ProviderCandidate(name="ai-gateway")

    node = history_mod.make_history_node(_TEKOS, _ANSWER_TASK, _model_router)
    saved_invoke = _model_router.invoke_with_fallback
    try:
        state = {
            "message": "m2",
            "reply": "reply about a restricted topic that is fairly long to exceed budget",
            "bearer_token": "t",
            "request_id": "req-1",
            "history": [
                {"role": "user", "content": "m1 " + "x" * 40},
                {"role": "assistant", "content": "reply1 " + "x" * 40},
            ],
            "history_classification": "C3",
            "effective_classification": "C3",
            "local_only_required": False,
            "errors": [],
        }
        _model_router.invoke_with_fallback = fake_invoke
        await node(state)
    finally:
        _model_router.invoke_with_fallback = saved_invoke
        _TEKOS.history_token_budget = saved_budget
        _TEKOS.history_max_turns = saved_max_turns

    assert captured, "compaction call never fired"
    assert captured["local_only"] is True
    assert captured["classification"] == "C3"
    assert captured["tags"] == ["zuno-internal"]


async def test_history_classification_never_downgrades_across_turns() -> None:
    node = history_mod.make_history_node(_TEKOS, _ANSWER_TASK, _model_router)
    state_c2 = {
        "message": "m1", "reply": "r1", "bearer_token": "t", "request_id": "req-1",
        "history": [], "history_classification": "C1", "effective_classification": "C2",
        "local_only_required": False, "errors": [],
    }
    result_1 = await node(state_c2)
    assert result_1["history_classification"] == "C2"

    state_c1_next = {
        "message": "m2", "reply": "r2", "bearer_token": "t", "request_id": "req-1",
        "history": result_1["history"], "history_classification": result_1["history_classification"],
        "effective_classification": "C1", "local_only_required": False, "errors": [],
    }
    result_2 = await node(state_c1_next)
    assert result_2["history_classification"] == "C2", "must not downgrade even though this turn's own retrieval was only C1"


# --------------------------------------------------------------------------
# Backward compatibility / backfill
# --------------------------------------------------------------------------


class _FakeCheckpointer:
    """A minimal stand-in exposing just the two BaseCheckpointSaver methods
    `_seed_history_backfill`/`_build_transcript_structured` actually call
    (`aget_tuple`, `alist`) - lets this test hand-construct a checkpoint
    whose `channel_values` genuinely lacks a `history` key, the way a
    real pre-ADR-0215 checkpoint would. Using a real MemorySaver-backed
    graph.ainvoke() instead would be self-defeating: the graph under test
    now ALWAYS runs record_history, so it could never produce a
    checkpoint missing `history` in the first place."""

    def __init__(self, checkpoints_newest_first):
        self._checkpoints = checkpoints_newest_first

    async def aget_tuple(self, config):
        return self._checkpoints[0] if self._checkpoints else None

    async def alist(self, config):
        for c in self._checkpoints:
            yield c


def _fake_checkpoint(channel_values, source=None, ts="t"):
    return SimpleNamespace(checkpoint={"channel_values": channel_values, "ts": ts}, metadata={"source": source})


async def test_resume_without_a_history_channel_does_not_crash_and_backfills() -> None:
    """A checkpoint written before ADR-0215 has no `history` channel at
    all - resuming it must not crash, and (per this ADR's Operational
    considerations) the first post-upgrade turn seeds `history` from the
    existing transcript reconstruction."""
    # Newest-first, matching alist()'s real contract: the "input"
    # checkpoint that opened the turn, then the checkpoint left once
    # message/reply were both written - channel_values here deliberately
    # has no "history" key, simulating a pre-ADR-0215 checkpoint schema.
    checkpoints_newest_first = [
        _fake_checkpoint({"message": "an old pre-upgrade question", "reply": "an old reply"}),
        _fake_checkpoint({}, source="input"),
    ]
    graph = SimpleNamespace(checkpointer=_FakeCheckpointer(checkpoints_newest_first))

    initial_state = {"message": "new question", "bearer_token": "t"}
    await _seed_history_backfill(graph, "run-pre-adr-0215", True, initial_state, _TEKOS)

    assert initial_state.get("history"), "backfill did not seed history from the transcript"
    assert any(h["content"] == "an old pre-upgrade question" for h in initial_state["history"])
    assert any(h["content"] == "an old reply" for h in initial_state["history"])
    assert initial_state.get("history_classification")


async def test_resume_with_an_existing_history_channel_is_left_alone() -> None:
    """Once a conversation has been through record_history at least once,
    its checkpoint DOES carry a `history` key - backfill must not
    overwrite it (record_history, not this backfill path, owns it from
    then on)."""
    checkpoints_newest_first = [
        _fake_checkpoint({"message": "m", "reply": "r", "history": [{"role": "user", "content": "already tracked"}]}),
    ]
    graph = SimpleNamespace(checkpointer=_FakeCheckpointer(checkpoints_newest_first))

    initial_state = {"message": "new question", "bearer_token": "t"}
    await _seed_history_backfill(graph, "run-already-tracked", True, initial_state, _TEKOS)

    assert "history" not in initial_state, "must not overwrite a checkpoint that already tracks history"


async def test_backfill_is_a_no_op_for_a_brand_new_conversation() -> None:
    graph = build_graph(MemorySaver())
    initial_state = {"message": "hi", "bearer_token": "t"}
    await _seed_history_backfill(graph, "run-brand-new", False, initial_state, _TEKOS)
    assert "history" not in initial_state
    assert "history_classification" not in initial_state


TESTS = [
    test_estimate_tokens_is_a_char_over_four_heuristic,
    test_append_turn_returns_a_new_list_and_caps_long_entries,
    test_build_history_messages_converts_roles_to_proper_message_types,
    test_build_history_messages_hard_cap_keeps_newest_turns_under_budget,
    test_build_history_messages_always_keeps_at_least_the_newest_turn,
    test_history_from_transcript_keeps_only_user_and_assistant_roles,
    test_second_turn_prompt_carries_the_first_turns_history,
    test_arkos_second_turn_prompt_carries_the_first_turns_history,
    test_compaction_triggers_under_a_small_budget_and_folds_old_turns,
    test_compaction_failure_degrades_to_sliding_window_without_failing_the_turn,
    test_compaction_call_is_local_only_for_a_c3_conversation,
    test_history_classification_never_downgrades_across_turns,
    test_resume_without_a_history_channel_does_not_crash_and_backfills,
    test_resume_with_an_existing_history_channel_is_left_alone,
    test_backfill_is_a_no_op_for_a_brand_new_conversation,
]


async def _run_all() -> int:
    failures = 0
    for test in TESTS:
        try:
            result = test()
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
