"""ADR-0039: AgentRegistry loads, validates and caches OKF v0.2 Markdown
bundles (ADR-0038, agents/<name>/agent.okf.md + tasks/*.md + prompts/*.md)
into typed AgentDefinition/TaskDefinition objects, so agent behavior
(prompts, allowed tools, RAG top_k, model classification ceiling) is driven
by the checked-in declarative bundle rather than hardcoded Python constants
in app/graph/nodes.py. Onboarding a sixth agent should mainly mean adding a
new bundle under agents/<name>/, not changing this module.

Schema validation here checks *shape* (required keys, matches directory
name). ADR-0106 (2026-08-14) is the signing pipeline "loads, validates and
caches signed OKF bundles" was aspirational for: when
`ZUNO_REQUIRE_SIGNED_BUNDLES` is enabled, a bundle additionally needs a
verifiable signature (`app/_sign_okf_bundle.py`, baked in from
`platform/supply-chain/sign_okf_bundle.py` - the exact same digest/verify
code CI uses, never duplicated, so the runtime can never disagree with CI
about what a bundle's digest is). Default OFF: no bundle has a real cosign
signature yet (WP-04 stage 2's credentialed CI run hasn't happened), so
requiring one today would refuse to start at all.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger("agent_runtime.registry")

AGENTS_DIR = os.getenv("AGENTS_DIR", "/app/agents")
REQUIRE_SIGNED_BUNDLES = os.getenv("ZUNO_REQUIRE_SIGNED_BUNDLES", "false").strip().lower() == "true"
OKF_SIGNATURES_DIR = os.getenv("ZUNO_OKF_SIGNATURES_DIR", "/app/okf-signatures")


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
    # ADR-0203: logical knowledge-domain IDs (knowledge/<domain>/domain.yaml)
    # this task may retrieve from - declared independently of allowed_tools,
    # same ceiling/narrowing semantics.
    allowed_knowledge: List[str] = field(default_factory=list)
    prompt: Optional[str] = None
    # ADR-0342/WP-33: which of this task's own allowed_tools entries
    # app/graph/nodes.py:_make_tool_call_node's conditional live-read
    # branch invokes (Tekos: confluence.page.search; Comage: a Salesforce
    # read) - explicit, git-reviewed configuration, never inferred or
    # derived from caller/state data. None means this task's shape never
    # attempts a live read (tool_call_node degrades to a no-op).
    live_read_tool: Optional[str] = None


@dataclass
class AgentDefinition:
    name: str
    status: str
    preferred_classification: str
    rag_top_k: int
    tasks: Dict[str, TaskDefinition] = field(default_factory=dict)
    # ADR-0342: name of the app/graph/shapes/<name>.py LangGraph workflow
    # this agent's active workflow executes, resolved by
    # app/graph/build.py:GraphFactory. None for a `placeholder` agent (no
    # runtime workflow exists yet, ADR-0007) - see that module's
    # validate_shapes() for the fail-fast rule this field feeds.
    graph_shape: Optional[str] = None
    # ADR-0342/WP-33: which of this agent's declared tasks its chat route
    # actually executes - required so two agents can share one shape
    # (e.g. Comage reusing Tekos's retrieve_reason_respond) with
    # GraphFactory still resolving the right task's prompt/allowed_tools/
    # allowed_knowledge for each. An agent may declare more tasks than
    # this (v1 catalog entries with no live route yet, same as Tekos's
    # own find-relevant-docs/check-my-drive-docs) - this field names only
    # the one the shape is built against. None for `placeholder` agents.
    primary_task: Optional[str] = None

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

    def declared_knowledge(self) -> List[str]:
        """Union of every task's allowed_knowledge - ADR-0203 factor 1
        (agent declaration): the knowledge-domain ceiling no task can widen.
        Mirrors declared_tools() exactly; there is no separate agent-level
        `zuno.allowed_knowledge` field, by the same design choice (see
        agents/tekos/agent.okf.md's body prose).
        """
        domains: List[str] = []
        for task in self.tasks.values():
            for domain in task.allowed_knowledge:
                if domain not in domains:
                    domains.append(domain)
        return domains


class AgentRegistry:
    def __init__(
        self,
        agents_dir: str = AGENTS_DIR,
        require_signed_bundles: bool = REQUIRE_SIGNED_BUNDLES,
        signatures_dir: str = OKF_SIGNATURES_DIR,
    ):
        self._agents_dir = Path(agents_dir)
        self._require_signed = require_signed_bundles
        self._signatures_dir = Path(signatures_dir)
        self._agents: Dict[str, AgentDefinition] = {}
        self.load_errors: List[str] = []

        if self._require_signed and shutil.which("cosign") is None:
            # Fail closed and loud at construction time, not per-agent: a
            # deployment that asks for enforcement but cannot possibly
            # verify anything is a fatal misconfiguration (ADR-0106 fail-
            # closed requirement), not a partial/degraded load.
            raise OkfError(
                "ZUNO_REQUIRE_SIGNED_BUNDLES is true but no 'cosign' binary is on PATH - "
                "cannot verify any bundle signature"
            )

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

    def _verify_signature(self, name: str, agent_dir: Path) -> None:
        """ADR-0106: only called when signature enforcement is on. Requires
        a `{name}.sig`/`{name}.pem` pair in the signatures directory (the
        exact output shape `platform/supply-chain/sign_okf_bundle.py sign`
        produces) and a successful `cosign verify-blob` against a freshly
        recomputed digest - the same verification path
        `verify_signatures.py`/CI would run, imported rather than
        duplicated (app/_sign_okf_bundle.py, baked in by the Dockerfile -
        imported here rather than at module top level so every normal,
        enforcement-off run - the default, including every local test -
        never needs that file to exist outside the built image)."""
        from app import _sign_okf_bundle  # noqa: PLC0415 - see docstring

        sig_path = self._signatures_dir / f"{name}.sig"
        cert_path = self._signatures_dir / f"{name}.pem"
        if not sig_path.is_file() or not cert_path.is_file():
            raise OkfError(
                f"agents/{name}: signature enforcement is on but no signature found at "
                f"{sig_path}/{cert_path}"
            )
        try:
            _sign_okf_bundle.verify_bundle(agent_dir, sig_path, cert_path)
        except _sign_okf_bundle.BundleError as exc:
            raise OkfError(f"agents/{name}: signature verification failed: {exc}") from exc

    def _load_agent(self, name: str, index_path: Path) -> AgentDefinition:
        if self._require_signed:
            self._verify_signature(name, index_path.parent)

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
            graph_shape=zuno.get("graph_shape"),
            primary_task=zuno.get("primary_task"),
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
            allowed_knowledge=list(zuno.get("allowed_knowledge", [])),
            prompt=prompt,
            live_read_tool=zuno.get("live_read_tool"),
        )

    def get(self, name: str) -> Optional[AgentDefinition]:
        return self._agents.get(name)

    def all(self) -> List[AgentDefinition]:
        """ADR-0342: iterated once at startup by GraphFactory's fail-fast
        validate_shapes() - every registered agent, not just one hardcoded
        name."""
        return list(self._agents.values())
