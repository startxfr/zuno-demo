"""Arkos's LangGraph workflow shape (ADR-0342, WP-31): plan -> retrieve ->
draft -> write. Structurally distinct from retrieve_reason_respond.py's
retrieve -> tool_call (conditional) -> reason -> respond: this shape plans
what to draft BEFORE retrieving context (topic-driven retrieval, not the
raw user message), has no conditional live-tool-call branch, and ends in
a write side effect (Drive) rather than a respond node that only
assembles citations from what earlier nodes already fetched.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.arkos_nodes import draft_node, plan_node, retrieve_node, write_node
from app.graph.state import AgentState


def build(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("draft", draft_node)
    graph.add_node("write", write_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "write")
    graph.add_edge("write", END)

    return graph.compile(checkpointer=checkpointer)
