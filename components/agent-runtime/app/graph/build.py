"""GraphFactory (ADR-0342): resolves, compiles and caches a LangGraph
workflow per agent, keyed off `AgentDefinition.graph_shape`/`primary_task`
rather than one hardcoded build function per agent. Before this ADR, v0
had exactly one graph shape (Tekos's) and this module WAS that one build
function - see app/graph/shapes/retrieve_reason_respond.py for where that
function moved verbatim; this module now only resolves a shape name to a
builder and compiles/caches the result.

ADR-0342/WP-33: a compiled graph is bound to one specific agent/task pair
(the shape builder closes its node functions over them, see
app/graph/nodes.py's `_make_*` factories) - two agents sharing a shape
name (e.g. Comage reusing Tekos's retrieve_reason_respond) each still get
their OWN compiled graph, cached by agent name, not by shape name alone.
A shape name mapping to the same builder function is what "reuse" means
here; the compiled *graph object* is never shared across agents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.graph.shapes import SHAPE_BUILDERS

if TYPE_CHECKING:
    from app.registry import AgentDefinition, TaskDefinition


class UnknownGraphShapeError(RuntimeError):
    pass


def known_shapes() -> Iterable[str]:
    return SHAPE_BUILDERS.keys()


def validate_shapes(agents: Iterable["AgentDefinition"]) -> None:
    """ADR-0342 Operational considerations / fail-fast startup: an
    `active` agent - the only kind this runtime is ever asked to actually
    serve a graph for (app/main.py's generic dispatch 404s on anything
    else before ever reaching GraphFactory) - must resolve to exactly one
    known graph shape AND a resolvable `primary_task` (WP-33: required so
    GraphFactory knows which of the agent's declared tasks to bind the
    shape's nodes to), or the app aborts startup with a clear error
    rather than discovering the misconfiguration on the first real
    request.

    A `placeholder` agent has no runtime workflow at all (ADR-0007) and may
    omit both fields entirely; if it names a shape anyway (e.g. metadata
    prepared ahead of going active), that name is still checked - a typo
    in unused-today metadata is still worth catching early.
    """
    for agent in agents:
        if agent.status != "active":
            if agent.graph_shape is not None and agent.graph_shape not in SHAPE_BUILDERS:
                raise UnknownGraphShapeError(
                    f"agent '{agent.name}' (status={agent.status}) declares unknown graph "
                    f"shape '{agent.graph_shape}' (known shapes: {sorted(SHAPE_BUILDERS)})"
                )
            continue
        if agent.graph_shape is None or agent.graph_shape not in SHAPE_BUILDERS:
            raise UnknownGraphShapeError(
                f"active agent '{agent.name}' does not resolve to a known graph shape "
                f"(declared: {agent.graph_shape!r}, known shapes: {sorted(SHAPE_BUILDERS)})"
            )
        if not agent.primary_task or agent.primary_task not in agent.tasks:
            raise UnknownGraphShapeError(
                f"active agent '{agent.name}' does not resolve to a declared task "
                f"(primary_task: {agent.primary_task!r}, declared tasks: {sorted(agent.tasks)})"
            )


class GraphFactory:
    """One instance per running Agent Runtime process
    (app.state.graph_factory), built against the process's single
    checkpointer at startup - the same async-connection-needs-an-event-loop
    constraint the old single build_graph() call already had (see
    app/main.py's lifespan). Compiles each agent's graph at most once,
    lazily, on first use.
    """

    def __init__(self, checkpointer: BaseCheckpointSaver):
        self._checkpointer = checkpointer
        self._compiled: Dict[str, CompiledStateGraph] = {}

    def graph_for_shape(
        self,
        shape: str,
        agent: Optional["AgentDefinition"] = None,
        task: Optional["TaskDefinition"] = None,
    ) -> CompiledStateGraph:
        """Lower-level entry point: builds/caches a graph for an explicit
        (shape, agent) pair, agent/task defaulting to None for shapes that
        don't need real OKF binding (test-only fixture shapes - see
        tests/test_graph_factory.py). Every real shape (retrieve_reason_
        respond, plan_draft_write) requires a real agent/task; use
        graph_for(agent) in production code instead, which resolves both
        from the agent's own bundle.
        """
        if shape not in SHAPE_BUILDERS:
            raise UnknownGraphShapeError(
                f"unknown graph shape '{shape}' (known shapes: {sorted(SHAPE_BUILDERS)})"
            )
        cache_key = f"{shape}:{agent.name}" if agent is not None else shape
        if cache_key not in self._compiled:
            self._compiled[cache_key] = SHAPE_BUILDERS[shape](self._checkpointer, agent, task)
        return self._compiled[cache_key]

    def graph_for(self, agent: "AgentDefinition") -> CompiledStateGraph:
        if agent.graph_shape is None:
            raise UnknownGraphShapeError(f"agent '{agent.name}' declares no graph shape")
        if not agent.primary_task or agent.primary_task not in agent.tasks:
            raise UnknownGraphShapeError(
                f"agent '{agent.name}' does not resolve to a declared task "
                f"(primary_task: {agent.primary_task!r}, declared tasks: {sorted(agent.tasks)})"
            )
        task = agent.tasks[agent.primary_task]
        return self.graph_for_shape(agent.graph_shape, agent, task)
