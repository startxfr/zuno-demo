"""ADR-0034: classification-escalation helper shared by every module that
needs "highest classification contributed so far, never downgraded".
Originally defined directly in app/graph/nodes.py; split out here once
app/graph/history.py (ADR-0215) also needed it, to avoid a circular
import between the two (history.py needs nodes.py's _escalate for
history_classification; nodes.py needs history.py's
build_history_messages for prompt injection). app/graph/nodes.py imports
and re-exposes both names by their original spelling, so every existing
import (app/graph/arkos_nodes.py's own
`from app.graph.nodes import _LIVE_READ_CLASSIFICATION, _escalate`) keeps
working unchanged.
"""

from __future__ import annotations

# Mirrors policies/data-classification/classification.yaml's data_domains
# ranking (Track B is the source of truth; not independently authored
# here).
_CLASSIFICATION_RANK = {"C1": 1, "C2": 2, "C3": 3}


def _escalate(current: str, candidate: str) -> str:
    """Highest-sensitivity-wins, never downgrades (ADR-0034 Security
    considerations): once a turn's effective classification is raised, no
    later source can lower it back down.
    """
    if _CLASSIFICATION_RANK.get(candidate, 0) > _CLASSIFICATION_RANK.get(current, 0):
        return candidate
    return current
