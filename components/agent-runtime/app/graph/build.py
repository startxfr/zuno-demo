"""Compiles the Tekos LangGraph workflow: an explicit graph of
retrieve -> tool_call (conditional) -> reason -> respond nodes, per
ADR-0018's decision to use LangGraph as the orchestration layer over the
OGX inference/retrieval substrate.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import reason_node, respond_node, retrieve_node, should_call_tools, tool_call_node
from app.graph.state import AgentState


def build_graph():
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

    return graph.compile()


# Compiled once at import time; LangGraph's compiled graph is safe to reuse
# concurrently across requests (per-invocation state is passed explicitly,
# not held on the graph object).
tekos_graph = build_graph()
