"""Compiles the Tekos LangGraph workflow: an explicit graph of
retrieve -> tool_call (conditional) -> reason -> respond nodes, per
ADR-0018's decision to use LangGraph as the orchestration layer over the
OGX inference/retrieval substrate.

ADR-0039's "GraphFactory" for v0: there is exactly one graph shape today
(Tekos's), so this module doesn't select among alternatives yet - what
ADR-0039 requires (prompts/tools/RAG/classification coming from the OKF
contract rather than code) is satisfied by app/graph/nodes.py resolving
those values from app/registry.py's AgentRegistry at import time. A second
agent's graph shape would add a second build function here plus a
selector keyed on AgentDefinition.name.

ADR-0103: `build_graph` now takes an explicit `checkpointer` (any
`BaseCheckpointSaver` - `MemorySaver` for the in-memory default, or an
`AsyncPostgresSaver` for persistent, resumable runs) instead of compiling
once at import time. A Postgres-backed checkpointer needs a live async
connection, which cannot be opened at plain module-import time (no event
loop yet) - so the compiled graph is now built during app startup
(app/main.py's lifespan) and stored on `app.state`, not as a module-level
constant.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import reason_node, respond_node, retrieve_node, should_call_tools, tool_call_node
from app.graph.state import AgentState


def build_graph(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
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
