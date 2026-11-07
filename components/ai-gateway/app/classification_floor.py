"""Classification floor per (agent, task) and the level of a header-less call (ADR-0565 clause 5, WP-209).

The gateway no longer trusts a caller's `X-Zuno-Data-Classification` alone:

    effective = max(declared, floor(agent, task))

`declared` is the header, or `CLASSIFICATION_DEFAULT_WHEN_ABSENT` (C1 unless the
chart sets it) when the caller sends none. The floors are generated from the
admitted agents release by platform/okf/generate_stack_config.py
(gitops/charts/ai-gateway/files/classification-floors.generated.yaml) and
mounted at CLASSIFICATION_FLOORS_PATH; without the file there is no floor and
the declared level is used as before. A floor can only raise a level, never
lower it, the same way `local_only_for` can only add a restriction.

The (agent, task) key comes from `X-Zuno-Agent` / `X-Zuno-Task`. A known agent
with an unknown or missing task gets the agent's own floor; an unknown agent
(an experience client, a hand-written UnifAI workflow) gets none. A header that
is not a known level is returned unchanged, so routing still refuses it (422).

The module has no FastAPI dependency so other gateway code (WP-225) can import it.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger("ai_gateway.classification_floor")

# The routing table knows C1 to C3; tool markers may carry C4 (app/tool_markers.py).
RANK = {"C1": 1, "C2": 2, "C3": 3, "C4": 4}
# Levels a header-less call may be given: the ones routing can serve.
DEFAULT_LEVELS = ("C1", "C2", "C3")
FALLBACK_DEFAULT = "C1"


def default_when_absent() -> str:
    """The level of a call without a classification header (chart `classification.defaultWhenAbsent`).

    Read on every call so a test or a restart with another value needs no reload.
    An unknown value falls back to C1 with an error log, never to something laxer than C1."""
    raw = os.getenv("CLASSIFICATION_DEFAULT_WHEN_ABSENT", FALLBACK_DEFAULT).strip().upper()
    if raw not in DEFAULT_LEVELS:
        logger.error("CLASSIFICATION_DEFAULT_WHEN_ABSENT=%r is not one of %s; using %s",
                     raw, ", ".join(DEFAULT_LEVELS), FALLBACK_DEFAULT)
        return FALLBACK_DEFAULT
    return raw


def declared_level(header: Optional[str]) -> str:
    """The caller's declared level: the header, upper-cased, or the default when it is absent or blank."""
    value = (header or "").strip().upper()
    return value or default_when_absent()


def higher(a: str, b: Optional[str]) -> str:
    """The higher of two levels; `a` unchanged when `b` is empty or unknown, or when `a` is unknown."""
    if not b or b not in RANK or a not in RANK:
        return a
    return b if RANK[b] > RANK[a] else a


@dataclass(frozen=True)
class FloorDecision:
    declared: str
    floor: Optional[str]
    effective: str

    @property
    def raised(self) -> bool:
        return self.effective != self.declared


class ClassificationFloors:
    """The generated floors, reloadable (app/routing_watch.py watches `path`)."""

    def __init__(self, path: Optional[str] = None):
        self.path = os.getenv("CLASSIFICATION_FLOORS_PATH", "") if path is None else path
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.info("no classification floors at %s; the declared level is used as is", self.path)
            return
        except Exception as exc:  # noqa: BLE001 - keep the floors already loaded
            logger.error("failed to read classification floors %s: %s", self.path, exc)
            return
        self.agents = self._parse(doc.get("agents"))
        logger.info("loaded classification floors from %s (%d agent(s))", self.path, len(self.agents))

    @staticmethod
    def _level(raw: Any, where: str) -> Optional[str]:
        level = str(raw or "").strip().upper()
        if level not in RANK:
            logger.warning("ignoring unknown classification floor %r for %s", raw, where)
            return None
        return level

    @classmethod
    def _parse(cls, raw: Any) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for agent, entry in (raw or {}).items() if isinstance(raw, dict) else []:
            if not isinstance(entry, dict):
                continue
            agent = str(agent).strip()
            tasks = {}
            for task, level in (entry.get("tasks") or {}).items() if isinstance(entry.get("tasks"), dict) else []:
                parsed = cls._level(level, f"{agent}/{task}")
                if parsed:
                    tasks[str(task).strip()] = parsed
            out[agent] = {"floor": cls._level(entry.get("floor"), agent), "tasks": tasks}
        return out

    def floor_for(self, agent: str, task: str) -> Optional[str]:
        entry = self.agents.get((agent or "").strip())
        if entry is None:
            return None
        return entry["tasks"].get((task or "").strip()) or entry["floor"]

    def effective(self, declared: str, agent: str, task: str) -> FloorDecision:
        floor = self.floor_for(agent, task)
        return FloorDecision(declared=declared, floor=floor, effective=higher(declared, floor))


floors = ClassificationFloors()
