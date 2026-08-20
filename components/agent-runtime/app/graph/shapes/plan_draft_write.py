"""Arkos's LangGraph workflow shape (ADR-0342, WP-31): plan -> retrieve ->
draft -> write. Structurally distinct from retrieve_reason_respond.py's
retrieve -> tool_call (conditional) -> reason -> respond: this shape plans
what to draft BEFORE retrieving context (topic-driven retrieval, not the
raw user message), has no conditional live-tool-call branch, and ends in
a write side effect (Drive) rather than a respond node that only
assembles citations from what earlier nodes already fetched.

Only Arkos uses this shape today, so unlike retrieve_reason_respond.py
its nodes (app/graph/arkos_nodes.py) stay bound to Arkos's own
module-level singletons rather than being agent/task-parameterized -
build() still accepts `agent`/`task` for GraphFactory's uniform shape-
builder interface (ADR-0342/WP-33). A future second consumer of this
exact shape would need arkos_nodes.py's factories converted the same way
app/graph/nodes.py's were for WP-33's Comage reuse.

ADR-0215's `record_history` terminal node is the first real use of the
`agent`/`task` params above: it needs Arkos's own bundle-declared history
budget/max_turns (app/registry.py's `AgentDefinition.history_*` fields)
and task name, so - unlike plan/retrieve/draft/write - it is genuinely
factory-built per (agent, task) rather than a bare module-level function,
the same `make_history_node` factory retrieve_reason_respond.py's own
shape uses.
"""

from __future__ import annotations

from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.arkos_nodes import _model_router, draft_node, plan_node, retrieve_node, write_node
from app.graph.history import make_history_node
from app.graph.state import AgentState
from app.registry import AgentDefinition, TaskDefinition


def build(
    checkpointer: BaseCheckpointSaver,
    agent: Optional[AgentDefinition] = None,
    task: Optional[TaskDefinition] = None,
) -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("draft", draft_node)
    graph.add_node("write", write_node)
    # ADR-0215: mirrors retrieve_reason_respond.py's own terminal node -
    # this shape's `agent`/`task` params, previously unused (see this
    # file's own docstring), are now used for the first time, to bind
    # record_history's compaction budget/routing to Arkos's own bundle.
    graph.add_node("record_history", make_history_node(agent, task, _model_router))

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "write")
    graph.add_edge("write", "record_history")
    graph.add_edge("record_history", END)

    return graph.compile(checkpointer=checkpointer)
