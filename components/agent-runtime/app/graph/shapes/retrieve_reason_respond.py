"""The reference LangGraph workflow shape (ADR-0342): retrieve ->
tool_call (conditional) -> reason -> respond. Currently executed by Tekos
alone; a future agent may declare this same shape name (`zuno.graph_shape:
retrieve_reason_respond` in its agent.okf.md) to reuse it verbatim rather
than adding a new one, per that ADR's "config-only switching" acceptance
bullet.

Moved here unchanged from the old app/graph/build.py, which held exactly
this one hardcoded graph before ADR-0342 - see app/graph/build.py's
GraphFactory for how a shape name now resolves to this module's build().
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import reason_node, respond_node, retrieve_node, should_call_tools, tool_call_node
from app.graph.state import AgentState


def build(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("tool_call", tool_call_node)
    graph.add_node("reason", reason_node)
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
