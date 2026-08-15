"""Registry of named LangGraph workflow shapes (ADR-0342). Each entry maps
a shape name - the exact string an OKF bundle declares in its
`zuno.graph_shape` field - to a `build(checkpointer) -> CompiledStateGraph`
function. `app/graph/build.py`'s `GraphFactory` is the only intended
consumer of this dict; it resolves an `AgentDefinition.graph_shape` value
through here rather than any per-agent hardcoding.

A new shape is added by writing a new module in this package (mirroring
retrieve_reason_respond.py's structure - a single `build()` function) and
registering it below. Tests may register additional, fixture-only shapes
directly into `SHAPE_BUILDERS` at runtime (see
tests/test_graph_factory.py) to prove the registry mechanism generalizes
without needing a second real, shipped shape.
"""

from __future__ import annotations

from typing import Callable, Dict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.graph.shapes import plan_draft_write, retrieve_reason_respond

ShapeBuilder = Callable[[BaseCheckpointSaver], CompiledStateGraph]

SHAPE_BUILDERS: Dict[str, ShapeBuilder] = {
    "retrieve_reason_respond": retrieve_reason_respond.build,
    # ADR-0342/WP-31: Arkos's shape - the first proof this registry holds
    # more than one workflow.
    "plan_draft_write": plan_draft_write.build,
}
