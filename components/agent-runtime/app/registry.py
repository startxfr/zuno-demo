"""ADR-0039: AgentRegistry loads, validates and caches OKF v0.2 Markdown
bundles (ADR-0038, agents/<name>/agent.okf.md + tasks/*.md + prompts/*.md)
into typed AgentDefinition/TaskDefinition objects, so agent behavior
(prompts, allowed tools, RAG top_k, model classification ceiling) is driven
by the checked-in declarative bundle rather than hardcoded Python constants
in app/graph/nodes.py. Onboarding a sixth agent should mainly mean adding a
new bundle under agents/<name>/, not changing this module.

Schema validation here checks *shape* (required keys, matches directory
name) rather than a cryptographic signature - "loads, validates and caches
signed OKF bundles" per the ADR text is aspirational for a future signing
pipeline (see ADR-0038's Security considerations on provenance); this is the
v0 slice of that requirement.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

AGENTS_DIR = os.getenv("AGENTS_DIR", "/app/agents")


class OkfError(Exception):
    pass


def _split_frontmatter(path: Path) -> tuple[Dict, str]:
    """Splits a "---\\n<yaml>\\n---\\n<body>" Markdown bundle. Splitting on
    every '---' occurrence and keeping only the first two (parts[0] is
    always empty, parts[1] is the frontmatter) mirrors
    components/agent-frontend/internal/okf/okf.go's splitFrontmatter and
    ansible/roles/agents/tasks/check.yml's Jinja .split('---') - the same
    small parsing logic duplicated across independently deployed
    services/tools rather than shared, matching this repo's established
    convention (see components/agent-bff/README.md's "Why standard library
    only" for the same reasoning applied to JWKS parsing).
    """
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise OkfError(f"{path}: expected a leading '---' YAML frontmatter block")
    frontmatter = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return frontmatter, body


@dataclass
class TaskDefinition:
    name: str
    title: str
    description: str
    allowed_tools: List[str]
    prompt: Optional[str] = None


@dataclass
class AgentDefinition:
    name: str
    status: str
    preferred_classification: str
    rag_top_k: int
    tasks: Dict[str, TaskDefinition] = field(default_factory=dict)

    def declared_tools(self) -> List[str]:
        """Union of every task's allowed_tools - ADR-0011 factor 1 (agent
        declaration): the ceiling no task can widen.
        """
        tools: List[str] = []
        for task in self.tasks.values():
            for tool in task.allowed_tools:
                if tool not in tools:
                    tools.append(tool)
        return tools


class AgentRegistry:
    def __init__(self, agents_dir: str = AGENTS_DIR):
        self._agents_dir = Path(agents_dir)
        self._agents: Dict[str, AgentDefinition] = {}
        self.load_errors: List[str] = []
        self._load_all()

    def _load_all(self) -> None:
        if not self._agents_dir.is_dir():
            self.load_errors.append(f"agents directory not found: {self._agents_dir}")
            return
        for entry in sorted(self._agents_dir.iterdir()):
            index_path = entry / "agent.okf.md"
            if not index_path.is_file():
                continue
            try:
                self._agents[entry.name] = self._load_agent(entry.name, index_path)
            except OkfError as exc:
                self.load_errors.append(str(exc))

    def _load_agent(self, name: str, index_path: Path) -> AgentDefinition:
        frontmatter, _ = _split_frontmatter(index_path)
        if frontmatter.get("okf_version") != "v0.2" or frontmatter.get("type") != "agent":
            raise OkfError(f"{index_path}: expected okf_version v0.2 / type agent")
        zuno = frontmatter.get("zuno") or {}
        if zuno.get("name") != name:
            raise OkfError(f"{index_path}: zuno.name {zuno.get('name')!r} does not match directory {name!r}")

        agent_dir = index_path.parent
        tasks: Dict[str, TaskDefinition] = {}
        for task_name in zuno.get("tasks", []):
            tasks[task_name] = self._load_task(task_name, agent_dir)

        model = zuno.get("model") or {}
        rag = zuno.get("rag") or {}
        return AgentDefinition(
            name=name,
            status=zuno.get("status", "placeholder"),
            preferred_classification=model.get("preferred_classification", "C1"),
            rag_top_k=int(rag.get("top_k", 5)),
            tasks=tasks,
        )

    def _load_task(self, task_name: str, agent_dir: Path) -> TaskDefinition:
        task_path = agent_dir / "tasks" / f"{task_name}.md"
        if not task_path.is_file():
            raise OkfError(f"{task_path}: task declared in agent index but bundle not found")
        frontmatter, body = _split_frontmatter(task_path)
        if frontmatter.get("type") != "task":
            raise OkfError(f"{task_path}: expected type task")
        zuno = frontmatter.get("zuno") or {}

        prompt_path = agent_dir / "prompts" / f"{task_name}.md"
        prompt = None
        if prompt_path.is_file():
            _, prompt = _split_frontmatter(prompt_path)

        return TaskDefinition(
            name=task_name,
            title=frontmatter.get("title", task_name),
            description=body,
            allowed_tools=list(zuno.get("allowed_tools", [])),
            prompt=prompt,
        )

    def get(self, name: str) -> Optional[AgentDefinition]:
        return self._agents.get(name)
