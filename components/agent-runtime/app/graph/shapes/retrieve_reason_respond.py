"""The reference LangGraph workflow shape (ADR-0342): retrieve ->
{tool_call, code, reason} (conditional) -> respond. Originally executed by
Tekos alone; since WP-33, Comage reuses this exact shape for its own
agent/task bundle - `build()` closes the node functions over whichever
agent/task GraphFactory resolves for the caller (app/graph/nodes.py's
`_make_retrieve_node`/`_make_tool_call_node`/`_make_reason_node`
factories), so "reuse" means the same topology AND the same node
implementations, genuinely parameterized - not two copies that happen to
look alike.

ADR-0417 added the `code` branch (`_make_code_node`), selected by
`_make_route_after_retrieval` instead of the plain 2-way
`should_call_tools` - a genuine no-op for every agent whose bundle doesn't
declare a sibling `write-code` task (comage/advantage/finage/naveo today),
since that selector only ever returns "code" when one is declared.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.history import make_history_node
from app.graph.nodes import (
    _make_code_node,
    _make_reason_node,
    _make_retrieve_node,
    _make_route_after_retrieval,
    _make_tool_call_node,
    _model_router,
    respond_node,
)
from app.graph.state import AgentState
from app.registry import AgentDefinition, TaskDefinition


def build(checkpointer: BaseCheckpointSaver, agent: AgentDefinition, task: TaskDefinition) -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", _make_retrieve_node(agent, task))
    graph.add_node("tool_call", _make_tool_call_node(agent, task))
    # ADR-0417: no-op for any agent that doesn't declare a sibling
    # write-code task - see _make_route_after_retrieval/_make_code_node.
    graph.add_node("code", _make_code_node(agent, task))
    graph.add_node("reason", _make_reason_node(agent, task))
    graph.add_node("respond", respond_node)
    # ADR-0215: appends this finished turn to `history` (and compacts
    # older turns into `summary` once the token budget is exceeded) -
    # runs AFTER respond, so the compaction LLM call it may trigger never
    # delays the reply that already streamed to the user.
    graph.add_node("record_history", make_history_node(agent, task, _model_router))

    graph.add_edge(START, "retrieve")
    # ADR-0417: replaces the previously-unconditional should_call_tools
    # 2-way selector with a 3-way one that also considers a coding
    # request - a true no-op for every agent without a write-code task.
    graph.add_conditional_edges(
        "retrieve",
        _make_route_after_retrieval(agent),
        {"tool_call": "tool_call", "code": "code", "reason": "reason"},
    )
    graph.add_edge("tool_call", "reason")
    graph.add_edge("code", "respond")
    graph.add_edge("reason", "respond")
    graph.add_edge("respond", "record_history")
    graph.add_edge("record_history", END)

    # Compiled once per checkpointer (at app startup, or once per test); the
    # compiled graph is safe to reuse concurrently across requests -
    # per-invocation state is passed explicitly via `config`, never held on
    # the graph object itself.
    return graph.compile(checkpointer=checkpointer)
