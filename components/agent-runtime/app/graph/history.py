"""ADR-0215: conversation history carried into agent prompts, with a
token-budgeted, Claude-Code-like compaction (recent turns verbatim, older
turns folded into a running summary by an explicit LLM call) - the
mechanism that fixes agent chat being stateless per turn despite full
history already being checkpointed by ADR-0103.

Three AgentState channels this module owns end-to-end: `history` (verbatim
recent turns), `summary` (the running compacted summary of everything
folded out of `history`), and `history_classification` (the monotonic
maximum classification across every turn seen so far - distinct from
`effective_classification`, which app/graph/nodes.py's retrieve_node
recomputes, and can downgrade, every turn). All three are explicitly
managed LastValue channels (app/graph/state.py), not reducer-accumulated:
compaction must be able to rewrite `history` wholesale, the same
explicit-management style app/graph/nodes.py's own `errors` channel
already uses.

Classification escalation (`_escalate`) is imported from
app/graph/classification.py rather than app/graph/nodes.py directly:
nodes.py itself imports `build_history_messages` from this module for
prompt injection, so importing the other way around would be circular -
classification.py holds no graph/state imports of its own precisely so
both modules can depend on it safely.

`make_history_node` builds the `record_history` node both graph shapes
(app/graph/shapes/retrieve_reason_respond.py, plan_draft_write.py) append
as their terminal step, running AFTER the turn's reply has already
streamed to the user (ADR-0045) - so the compaction LLM call this may
trigger costs a delayed SSE `done` event on the rare turns that trigger
it, never delayed first-token latency.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.clients.model_router import ModelRouter, ModelRouterError
from app.graph.classification import _escalate
from app.graph.state import AgentState
from app.registry import AgentDefinition, TaskDefinition

logger = logging.getLogger("agent_runtime.graph.history")

# A char/4 approximation, not a real tokenizer - components/agent-runtime
# has no tiktoken dependency, and it would be the wrong tokenizer for the
# local qwen/gpt-oss models regardless. A conservative budget
# compensates for the approximation; build_history_messages's own hard
# cap is the real backstop, not this estimate's precision.
_CHARS_PER_TOKEN = 4

# Each history entry (one turn's user text or reply) is capped so a
# single very long turn - e.g. Arkos's inline-draft-on-write-failure
# fallback (app/graph/arkos_nodes.py:write_node returning the full draft
# as `reply`) - can't alone blow the token budget or checkpoint size.
HISTORY_ENTRY_MAX_CHARS = 4000

_COMPACTION_SYSTEM_PROMPT = """\
You maintain a running summary of an ongoing conversation between a user \
and an assistant. You will be given the current summary (which may be \
empty) and the next turns to fold into it.

Update the summary to preserve: facts the user stated, decisions made, \
constraints given, open questions, and user preferences. Do not preserve \
small talk or the literal wording of the turns.

Respond with ONLY the updated summary text, at most about 250 words. No \
preamble, no headings, no JSON."""


def _cap(text: str, limit: int = HISTORY_ENTRY_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def estimate_tokens(text: str) -> int:
    """Deliberately approximate - see module docstring."""
    if not text:
        return 0
    return len(text) // _CHARS_PER_TOKEN + 1


def _history_size(summary: str, history: List[Dict[str, str]]) -> int:
    total = estimate_tokens(summary)
    for turn in history:
        total += estimate_tokens(turn.get("content", ""))
    return total


def append_turn(history: List[Dict[str, str]], message: str, reply: str) -> List[Dict[str, str]]:
    """Returns a NEW list - `history` is an explicitly managed channel
    (module docstring), never mutated in place, so record_history always
    returns a full replacement rather than relying on a reducer."""
    appended = list(history)
    if message:
        appended.append({"role": "user", "content": _cap(message)})
    if reply:
        appended.append({"role": "assistant", "content": _cap(reply)})
    return appended


def history_from_transcript(transcript: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """ADR-0215 backfill (app/main.py:agent_chat): turns
    `_build_transcript_structured`'s `[{role, content, ts}]` shape into
    this module's own `history` entries, for a resumed conversation whose
    checkpoint predates this ADR and so has no `history` channel yet -
    reuses the existing transcript reconstruction rather than re-deriving
    turns a second, different way."""
    history: List[Dict[str, str]] = []
    for turn in transcript:
        role = turn.get("role")
        if role not in ("user", "assistant"):
            continue
        history.append({"role": role, "content": _cap(turn.get("content", ""))})
    return history


def build_history_messages(
    history: List[Dict[str, str]], token_budget: int, summary: str = ""
) -> List[BaseMessage]:
    """Converts stored turns into proper role messages, walking
    newest-to-oldest and stopping once `token_budget` (minus what the
    summary itself already costs) is spent - the deterministic hard cap
    ADR-0215 calls for even when record_history's own compaction has
    fallen behind or failed repeatedly. Always keeps at least the single
    newest turn, even if it alone exceeds what's left of the budget - an
    empty result would silently discard the most relevant context instead
    of merely running over budget by one turn.

    `summary` only affects how much of the budget is left for verbatim
    turns here; the summary text itself is injected into the system
    message by the caller (app/graph/nodes.py, app/graph/arkos_nodes.py),
    not returned by this function.
    """
    remaining = max(token_budget - estimate_tokens(summary), 0)
    kept: List[Dict[str, str]] = []
    for turn in reversed(history):
        cost = estimate_tokens(turn.get("content", ""))
        if kept and cost > remaining:
            break
        remaining -= cost
        kept.append(turn)
    kept.reverse()

    messages: List[BaseMessage] = []
    for turn in kept:
        content = turn.get("content", "")
        if turn.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


async def compact(
    model_router: ModelRouter,
    *,
    summary: str,
    folded_turns: List[Dict[str, str]],
    classification: str,
    local_only_required: bool,
    bearer_token: str,
    request_id: Optional[str],
    agent_name: str,
    task_name: str,
) -> str:
    """Runs the one compaction LLM call and returns the new summary text.
    Raises ModelRouterError on failure - the caller (record_history below)
    decides how to degrade (ADR-0215: fall back to a plain sliding window,
    keep the old summary, record the failure, never fail the user's own
    turn - the reply has already streamed to them by the time this runs).

    Routes exactly like app/memory.py's own extract_memory: local-only is
    forced for C2/C3 (a summary of restricted content is still restricted
    content, ADR-0034/ADR-0035) - `local_only_required` additionally
    covers a source that declared external_model_policy.allow_context:
    false even at a lower classification (the same flag reason_node/
    draft_node's own model call already honors).

    Tagged "zuno-internal" so app/main.py:_stream_chat can filter this
    call's tokens out of the user-visible SSE stream - it runs as a
    nested model call inside the same graph invocation astream_events
    observes, and must never leak into the chat.
    """
    local_only = local_only_required or classification.upper() in ("C2", "C3")
    folded_text = "\n".join(
        f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in folded_turns
    )
    human_content = f"Current summary:\n{summary or '(none yet)'}\n\nNew turns to fold in:\n{folded_text}"

    result, _ = await model_router.invoke_with_fallback(
        classification=classification,
        messages=[SystemMessage(content=_COMPACTION_SYSTEM_PROMPT), HumanMessage(content=human_content)],
        bearer_token=bearer_token,
        local_only=local_only,
        request_id=request_id,
        agent_name=agent_name,
        task_name=f"{task_name}#history-compaction",
        tags=["zuno-internal"],
    )
    text = result.content if hasattr(result, "content") else str(result)
    return text.strip()


def make_history_node(agent: AgentDefinition, task: TaskDefinition, model_router: ModelRouter):
    """Builds the `record_history` node factory-bound to one agent/task
    pair, following app/graph/nodes.py's `_make_*` factory pattern -
    appended as the terminal node of both graph shapes
    (`respond -> record_history -> END`, `write -> record_history ->
    END`).
    """
    max_turns = agent.history_max_turns
    token_budget = agent.history_token_budget

    async def record_history(state: AgentState) -> Dict[str, Any]:
        if not agent.history_enabled:
            return {"history": state.get("history", [])}

        history = append_turn(state.get("history", []), state.get("message", ""), state.get("reply", ""))
        history_classification = _escalate(
            state.get("history_classification", agent.preferred_classification),
            state.get("effective_classification", agent.preferred_classification),
        )
        summary = state.get("summary", "")

        keep_from = 2 * max_turns
        if _history_size(summary, history) > token_budget and len(history) > keep_from:
            folded, keep = history[:-keep_from], history[-keep_from:]
            try:
                summary = await compact(
                    model_router,
                    summary=summary,
                    folded_turns=folded,
                    classification=history_classification,
                    # ADR-0416: agent.local_only (e.g. Finage) applies here
                    # too - an agent-level restriction, not just a per-turn
                    # source restriction.
                    local_only_required=state.get("local_only_required", False) or agent.local_only,
                    bearer_token=state["bearer_token"],
                    request_id=state.get("request_id"),
                    agent_name=agent.name,
                    task_name=task.name,
                )
                history = keep
            except ModelRouterError as exc:
                logger.warning(
                    "history compaction failed for agent=%s, degrading to a sliding window: %s",
                    agent.name, exc,
                )
                history = keep  # still trim - bounds checkpoint growth even without a fresh summary
                return {
                    "history": history,
                    "summary": summary,
                    "history_classification": history_classification,
                    "errors": state.get("errors", []) + [f"history_compaction: {exc}"],
                }

        return {"history": history, "summary": summary, "history_classification": history_classification}

    return record_history


def truncate_to_token_budget(text: str, token_budget: int) -> str:
    """ADR-0527 clause 5: bound the project context before it reaches the
    prompt. Uses the same deliberately-approximate char/4 heuristic as
    estimate_tokens above - a project context is background, and spending
    a real tokenizer call per turn to bound background would cost more
    than it saves.

    Cuts on the last whitespace boundary inside the budget so the block
    never ends mid-word, and marks the cut so a reader (and the model) can
    tell the context was shortened rather than authored that way. A budget
    of 0 or less disables injection entirely by returning "".
    """
    if not text or token_budget <= 0:
        return ""
    max_chars = token_budget * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    cut = head.rfind(" ")
    if cut > 0:
        head = head[:cut]
    return head.rstrip() + " […truncated]"
