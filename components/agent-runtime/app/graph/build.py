"""GraphFactory (ADR-0342): resolves, compiles and caches a LangGraph
workflow per named shape, keyed off `AgentDefinition.graph_shape` rather
than one hardcoded build function per agent. Before this ADR, v0 had
exactly one graph shape (Tekos's) and this module WAS that one build
function - see app/graph/shapes/retrieve_reason_respond.py for where that
function moved verbatim; this module now only resolves a shape name to a
builder and compiles/caches the result.

A compiled graph is safe to reuse concurrently across every agent that
declares the same shape name (per-invocation state flows through `config`,
never held on the graph object) - so two agents sharing a shape (e.g. a
future agent reusing `retrieve_reason_respond`) share one compiled graph
object, compiled at most once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.graph.shapes import SHAPE_BUILDERS

if TYPE_CHECKING:
    from app.registry import AgentDefinition


class UnknownGraphShapeError(RuntimeError):
    pass


def known_shapes() -> Iterable[str]:
    return SHAPE_BUILDERS.keys()


def validate_shapes(agents: Iterable["AgentDefinition"]) -> None:
    """ADR-0342 Operational considerations / fail-fast startup: an
    `active` agent - the only kind this runtime is ever asked to actually
    serve a graph for (app/main.py's generic dispatch 404s on anything
    else before ever reaching GraphFactory) - must resolve to exactly one
    known graph shape, or the app aborts startup with a clear error rather
    than discovering the misconfiguration on the first real request.

    A `placeholder` agent has no runtime workflow at all (ADR-0007) and may
    omit `graph_shape` entirely; if it names one anyway (e.g. metadata
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


class GraphFactory:
    """One instance per running Agent Runtime process
    (app.state.graph_factory), built against the process's single
    checkpointer at startup - the same async-connection-needs-an-event-loop
    constraint the old single build_graph() call already had (see
    app/main.py's lifespan). Compiles each shape at most once, lazily, on
    first use, and reuses the compiled graph across every agent sharing
    that shape name.
    """

    def __init__(self, checkpointer: BaseCheckpointSaver):
        self._checkpointer = checkpointer
        self._compiled: Dict[str, CompiledStateGraph] = {}

    def graph_for_shape(self, shape: str) -> CompiledStateGraph:
        if shape not in SHAPE_BUILDERS:
            raise UnknownGraphShapeError(
                f"unknown graph shape '{shape}' (known shapes: {sorted(SHAPE_BUILDERS)})"
            )
        if shape not in self._compiled:
            self._compiled[shape] = SHAPE_BUILDERS[shape](self._checkpointer)
        return self._compiled[shape]

    def graph_for(self, agent: "AgentDefinition") -> CompiledStateGraph:
        if agent.graph_shape is None:
            raise UnknownGraphShapeError(f"agent '{agent.name}' declares no graph shape")
        return self.graph_for_shape(agent.graph_shape)
