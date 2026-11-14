"""ADR-0036: loads the same OKF v0.2 Markdown bundles (ADR-0038,
agents/<name>/agent.okf.md + tasks/*.md) as Agent Runtime's
app/registry.py, but only the slice this gateway's policy check needs -
per-agent declared tools and per-task allowed tools - to enforce the
agent_declaration and task_rights factors of the ADR-0011 intersection.

Deliberately a separate, smaller module rather than importing Agent
Runtime's registry (retired in WP-156): the bundles are read from
AGENTS_DIR, which since WP-165 is the admitted zuno-demo-agents release the
okf-fetch init container extracts at pod start (/okf/agents, see the
Dockerfile and gitops/charts/mcp-gateway), matching this repo's established convention of duplicating small
well-specified parsing code across services rather than sharing a module
(see components/agent-bff/README.md's "Why standard library only" for the
same reasoning applied to JWKS parsing).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger("a2a_gateway.agent_declarations")

AGENTS_DIR = os.getenv("AGENTS_DIR", "/app/agents")


# ADR-0508 clause 3 / ADR-0615 clause 5: the versions this reader understands.
# Profile 1.0 is okf_version "0.2" (upstream OKF, a quoted string) plus
# zuno.profile "1.0"; the legacy okf_version values v0.2 and v0.3 carry no
# zuno.profile and stay readable until WP-268 removes them. A document declaring
# anything else (or nothing) is refused, so a bundle written for a newer schema
# is never read with older rules. This reader keeps its own copy of the rule
# (ADR-0508 clause 4); platform/okf/tests/test_okf_version_dispatch.py checks
# that every copy accepts and refuses the same documents.
UPSTREAM_OKF_VERSION = "0.2"
ZUNO_PROFILES = ("1.0",)
LEGACY_OKF_VERSIONS = ("v0.2", "v0.3")
SUPPORTED_OKF_VERSIONS_TEXT = (f'okf_version "{UPSTREAM_OKF_VERSION}" with zuno.profile '
                               f'{", ".join(ZUNO_PROFILES)}, or legacy {", ".join(LEGACY_OKF_VERSIONS)}')


def okf_document_version(frontmatter: Dict) -> str:
    """The version a document's frontmatter follows: "v0.2" or "v0.3" (legacy)
    or "1.0" (profile). ValueError, naming the cause, for any other pair."""
    version = frontmatter.get("okf_version")
    zuno = frontmatter.get("zuno")
    profile = zuno.get("profile") if isinstance(zuno, dict) else None
    if version is None:
        raise ValueError(f"missing okf_version (supported: {SUPPORTED_OKF_VERSIONS_TEXT})")
    if isinstance(version, str) and version in LEGACY_OKF_VERSIONS:
        if profile is not None:
            raise ValueError(f'zuno.profile is only valid with okf_version "{UPSTREAM_OKF_VERSION}" '
                             f"(this document says okf_version {version!r})")
        return version
    if isinstance(version, str) and version == UPSTREAM_OKF_VERSION:
        if isinstance(profile, str) and profile in ZUNO_PROFILES:
            return profile
        raise ValueError(f"unsupported zuno.profile {profile!r} (supported: {', '.join(ZUNO_PROFILES)})")
    raise ValueError(f"unsupported okf_version {version!r} (supported: {SUPPORTED_OKF_VERSIONS_TEXT})")


def _split_frontmatter(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: expected a leading '---' YAML frontmatter block")
    frontmatter = yaml.safe_load(parts[1]) or {}
    try:
        okf_document_version(frontmatter)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from None
    return frontmatter


@dataclass
class AgentDeclaration:
    name: str
    status: str
    tasks: Dict[str, List[str]] = field(default_factory=dict)  # task name -> allowed_tools
    # ADR-0040: zuno.access.groups, the Keycloak groups entitled to use this
    # agent. Checked by the /mcp front-door for callers that declare an agent
    # (ADR-0571); the REST contract's caller (agent-runtime) checks it itself.
    access_groups: List[str] = field(default_factory=list)
    # ADR-0403: zuno.model.preferred_classification, the floor this agent adds to a
    # delegation chain's effective classification (raise-only, ADR-0565).
    classification: str = ""
    # ADR-0401: zuno.delegation.targets as (agent, task); empty means the agent
    # may not delegate. ADR-0406: zuno.limits.delegation.max_depth, default 1.
    delegation_targets: List[Tuple[str, str]] = field(default_factory=list)
    max_depth: int = 1
    # What the A2A agent card shows (public, minimal) and what the executor needs to answer.
    title: str = ""
    description: str = ""
    primary_task: str = ""
    agent_dir: str = ""

    def system_prompt(self, task: str) -> str:
        """The task's system prompt from the admitted release, else the agent's description."""
        for name in (task, self.primary_task):
            path = Path(self.agent_dir) / "prompts" / f"{name}.md"
            if name and path.is_file():
                text = path.read_text(encoding="utf-8")
                parts = text.split("---", 2)
                body = parts[2] if text.lstrip().startswith("---") and len(parts) == 3 else text
                if body.strip():
                    return body.strip()
        return f"You are {self.title}. {self.description}".strip()

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
        access_groups = list((zuno.get("access") or {}).get("groups") or [])
        # A malformed delegation entry is skipped, never widened: fewer targets
        # can only mean fewer delegations (the schema refuses it upstream anyway).
        targets = [
            (str(t["agent"]), str(t["task"]))
            for t in ((zuno.get("delegation") or {}).get("targets") or [])
            if isinstance(t, dict) and t.get("agent") and t.get("task")
        ]
        depth = ((zuno.get("limits") or {}).get("delegation") or {}).get("max_depth")
        return AgentDeclaration(
            name=name,
            status=zuno.get("status", "placeholder"),
            tasks=tasks,
            access_groups=access_groups,
            classification=str((zuno.get("model") or {}).get("preferred_classification") or ""),
            delegation_targets=targets,
            max_depth=depth if isinstance(depth, int) and not isinstance(depth, bool) and depth >= 1 else 1,
            title=str(frontmatter.get("title") or name),
            description=" ".join(str(frontmatter.get("description") or "").split()),
            primary_task=str(zuno.get("primary_task") or next(iter(tasks), "")),
            agent_dir=str(index_path.parent),
        )

    @property
    def loaded(self) -> bool:
        return bool(self._agents) and self.load_error is None

    def get(self, name: str) -> Optional[AgentDeclaration]:
        return self._agents.get(name)
