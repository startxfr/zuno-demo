"""The reference LangGraph workflow shape (ADR-0342): retrieve ->
tool_call (conditional) -> reason -> respond. Originally executed by
Tekos alone; since WP-33, Comage reuses this exact shape for its own
agent/task bundle - `build()` closes the node functions over whichever
agent/task GraphFactory resolves for the caller (app/graph/nodes.py's
`_make_retrieve_node`/`_make_tool_call_node`/`_make_reason_node`
factories), so "reuse" means the same topology AND the same node
implementations, genuinely parameterized - not two copies that happen to
look alike.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import (
    _make_reason_node,
    _make_retrieve_node,
    _make_tool_call_node,
    respond_node,
    should_call_tools,
)
from app.graph.state import AgentState
from app.registry import AgentDefinition, TaskDefinition


def build(checkpointer: BaseCheckpointSaver, agent: AgentDefinition, task: TaskDefinition) -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", _make_retrieve_node(agent, task))
    graph.add_node("tool_call", _make_tool_call_node(agent, task))
    graph.add_node("reason", _make_reason_node(agent, task))
    graph.add_node("respond", respond_node)

    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        should_call_tools,
        {"tool_call": "tool_call", "reason": "reason"},
    )
    graph.add_edge("tool_call", "reason")
    graph.add_edge("reason", "respond")
    graph.add_edge("respond", END)

    # Compiled once per checkpointer (at app startup, or once per test); the
    # compiled graph is safe to reuse concurrently across requests -
    # per-invocation state is passed explicitly via `config`, never held on
    # the graph object itself.
    return graph.compile(checkpointer=checkpointer)
