"""Arkos's LangGraph workflow shape (ADR-0342, WP-31): plan -> retrieve ->
draft -> reflect -> write. Structurally distinct from
retrieve_reason_respond.py's retrieve -> tool_call (conditional) -> reason
-> respond: this shape plans what to draft BEFORE retrieving context
(topic-driven retrieval, not the raw user message), has no conditional
live-tool-call branch, and ends in a write side effect (Drive) rather than
a respond node that only assembles citations from what earlier nodes
already fetched.

ADR-0416 added `reflect` between draft and write: a self-review pass over
draft_node's own output only (never the raw retrieved context), which is
what lets it be evaluated at a fixed C2 ceiling even on an ambient-C3
Arkos turn - see arkos_nodes.py:reflect_node's own docstring for the full
safety argument.

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

from app.graph.arkos_nodes import (
    _model_router,
    code_node,
    demo_node,
    draft_node,
    plan_node,
    reflect_node,
    retrieve_node,
    route_after_plan,
    write_node,
)
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
    # ADR-0417: early-exit branch for a coding request - never touches
    # retrieve/draft/reflect/write, see route_after_plan below.
    graph.add_node("code", code_node)
    # Same early-exit shape as "code" above, for a demo-narrative request.
    graph.add_node("demo", demo_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("draft", draft_node)
    # ADR-0416: self-review pass over draft_node's own output, before write.
    graph.add_node("reflect", reflect_node)
    graph.add_node("write", write_node)
    # ADR-0215: mirrors retrieve_reason_respond.py's own terminal node -
    # this shape's `agent`/`task` params, previously unused (see this
    # file's own docstring), are now used for the first time, to bind
    # record_history's compaction budget/routing to Arkos's own bundle.
    graph.add_node("record_history", make_history_node(agent, task, _model_router))

    graph.add_edge(START, "plan")
    # ADR-0417: replaces the previously-unconditional plan -> retrieve edge.
    graph.add_conditional_edges(
        "plan", route_after_plan, {"code": "code", "demo": "demo", "retrieve": "retrieve"}
    )
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "reflect")
    graph.add_edge("reflect", "write")
    graph.add_edge("write", "record_history")
    graph.add_edge("code", "record_history")
    graph.add_edge("demo", "record_history")
    graph.add_edge("record_history", END)

    return graph.compile(checkpointer=checkpointer)
