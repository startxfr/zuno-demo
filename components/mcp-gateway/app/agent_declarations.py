"""ADR-0036: loads the same OKF v0.2 Markdown bundles (ADR-0038,
agents/<name>/agent.okf.md + tasks/*.md) as Agent Runtime's
app/registry.py, but only the slice this gateway's policy check needs -
per-agent declared tools and per-task allowed tools - to enforce the
agent_declaration and task_rights factors of the ADR-0011 intersection.

Deliberately a separate, smaller module rather than importing Agent
Runtime's registry: the two services are independently deployed/versioned
and each bakes its own copy of agents/ into its own image (see Dockerfile),
matching this repo's established convention of duplicating small
well-specified parsing code across services rather than sharing a module
(see components/agent-bff/README.md's "Why standard library only" for the
same reasoning applied to JWKS parsing).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger("mcp_gateway.agent_declarations")

AGENTS_DIR = os.getenv("AGENTS_DIR", "/app/agents")


def _split_frontmatter(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: expected a leading '---' YAML frontmatter block")
    return yaml.safe_load(parts[1]) or {}


@dataclass
class AgentDeclaration:
    name: str
    status: str
    tasks: Dict[str, List[str]] = field(default_factory=dict)  # task name -> allowed_tools

    def declared_tools(self) -> List[str]:
        tools: List[str] = []
        for allowed in self.tasks.values():
            for tool in allowed:
                if tool not in tools:
                    tools.append(tool)
        return tools


class AgentDeclarationStore:
    def __init__(self, agents_dir: str = AGENTS_DIR):
        self._agents_dir = Path(agents_dir)
        self._agents: Dict[str, AgentDeclaration] = {}
        self.load_error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        agents: Dict[str, AgentDeclaration] = {}
        if not self._agents_dir.is_dir():
            self.load_error = f"agents directory not found: {self._agents_dir}"
            self._agents = agents
            return
        try:
            for entry in sorted(self._agents_dir.iterdir()):
                index_path = entry / "agent.okf.md"
                if not index_path.is_file():
                    continue
                agents[entry.name] = self._load_agent(entry.name, index_path)
        except Exception as exc:  # malformed bundle, missing keys, etc.
            self.load_error = f"failed to load OKF bundles from {self._agents_dir}: {exc}"
            logger.error(self.load_error)
            self._agents = {}
            return
        self.load_error = None
        self._agents = agents

    def _load_agent(self, name: str, index_path: Path) -> AgentDeclaration:
        frontmatter = _split_frontmatter(index_path)
        zuno = frontmatter.get("zuno") or {}
        tasks: Dict[str, List[str]] = {}
        for task_name in zuno.get("tasks", []):
            task_path = index_path.parent / "tasks" / f"{task_name}.md"
            task_frontmatter = _split_frontmatter(task_path)
            task_zuno = task_frontmatter.get("zuno") or {}
            tasks[task_name] = list(task_zuno.get("allowed_tools", []))
        return AgentDeclaration(name=name, status=zuno.get("status", "placeholder"), tasks=tasks)

    @property
    def loaded(self) -> bool:
        return bool(self._agents) and self.load_error is None

    def get(self, name: str) -> Optional[AgentDeclaration]:
        return self._agents.get(name)
