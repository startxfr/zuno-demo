"""ADR-0039: AgentRegistry loads, validates and caches OKF v0.2 Markdown
bundles (ADR-0038, agents/<name>/agent.okf.md + tasks/*.md + prompts/*.md)
into typed AgentDefinition/TaskDefinition objects, so agent behavior
(prompts, allowed tools, RAG top_k, model classification ceiling) is driven
by the checked-in declarative bundle rather than hardcoded Python constants
in app/graph/nodes.py. Onboarding a sixth agent should mainly mean adding a
new bundle under agents/<name>/, not changing this module.

Schema validation here checks *shape* (required keys, matches directory
name). ADR-0106/ADR-0420 is the signing pipeline "loads, validates and
caches signed OKF bundles" was aspirational for: when
`ZUNO_REQUIRE_SIGNED_BUNDLES` is enabled, a bundle additionally needs a
verifiable signature (`app/_sign_okf_bundle.py`, baked in from
`platform/supply-chain/sign_okf_bundle.py` - the exact same digest/verify
code the in-cluster signing Job uses, never duplicated, so the runtime can
never disagree with it about what a bundle's digest is), signed by the
in-cluster Vault Transit key (ADR-0420) and verified here against the
committed public key alone - no Vault access needed at verify time. Default
OFF until WP-069 populates every agent's signature.
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

# ADR-0215: fleet-wide defaults for a bundle that declares no zuno.memory.
# history block at all (every field there is optional - see
# platform/okf/schema/zuno-okf-v0.2.schema.json). HISTORY_TOKEN_BUDGET's
# default (1800) predates ADR-0518: it was sized against the old chat
# model's --max-model-len=8192, with headroom for the system prompt
# (~500) and RAG context (~2500). There are FOUR local chat models now,
# and they do NOT share one window: qwen3.6-27b-instruct, gpt-oss-20b and
# qwen3.5-9b-wesh serve 32768, but qwen3.5-9b - the fleet-wide default
# since ADR-0531 - serves 8192 (gitops/charts/models/values.yaml's
# qwen35Model.maxModelLen, reduced to fit 19.3GB of bf16 weights on a
# 24GB MIG slice). So 1800 is conservative against the widest window and
# roughly right against the narrowest, which is the one the default model
# actually has. An agent wanting a larger window declares it explicitly in
# its own bundle rather than this shared default silently inflating every
# agent's per-turn token spend.
#
# ADR-0544 is the real backstop this default alone was never enough to be:
# app/graph/prompt_budget.py clamps the WHOLE assembled prompt (this
# budget, project context, and RAG/live context, none of which shared a
# common ceiling before) against the fleet's actual narrowest reachable
# window at assembly time - a bundle raising this value no longer needs
# to hand-check it against 8192 itself, though it still should for its
# OWN sake (a larger declared budget is more likely to trigger the
# clamp's sacrifice order on the narrow-window path).
HISTORY_TOKEN_BUDGET_DEFAULT = int(os.getenv("HISTORY_TOKEN_BUDGET", "1800"))
HISTORY_MAX_TURNS_DEFAULT = 6
# ADR-0527 clause 5: the project context's own token budget, separate from
# the history budget above so a long engagement briefing can never crowd
# out the conversation itself. The 54000-character storage ceiling is an
# INPUT limit; this is what actually reaches the model, and a maximal
# context (~13500 tokens) is truncated hard to fit here. Overridable per
# bundle via zuno.memory.project_context.token_budget, exactly like
# history's.
PROJECT_CONTEXT_TOKEN_BUDGET_DEFAULT = int(os.getenv("PROJECT_CONTEXT_TOKEN_BUDGET", "1200"))
# Operational kill switch (ADR-0215): forces every agent's history off
# regardless of bundle content, for a rollback that needs no image
# rebuild.
HISTORY_DISABLED = os.getenv("ZUNO_HISTORY_DISABLED", "false").strip().lower() == "true"


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
class PromptSlot:
    """ADR-0419: a named call within a task that needs its own prompt text
    and/or its own classification ceiling, distinct from the task's
    primary/implicit call - formalizes what app/graph/arkos_nodes.py's
    reflect_node hardcoded in Python (ADR-0416's fixed "C2" literal and an
    inline system-prompt string) as declarative OKF config instead.

    Deliberately has no preference-list fields of its own (an earlier draft
    of ADR-0419 had `preferred`/`fallback` here, corrected before any code
    was built against it): ai-gateway resolves model preference server-side
    purely from the `(agent, task)` routing key, and a slot shares its
    task's `task_name` by design (see the ADR's "Alternatives considered" -
    a slot is one step of a task, not a second task), so there is no
    existing mechanism for a slot to supply its own preference list. This
    doesn't cost reflect_node anything: preference applies after
    classification-eligibility filtering, so the same shared preference
    list already produces a different effective chain at a slot's own
    (lower) ceiling than at the task's ambient one.
    """

    name: str
    prompt: Optional[str] = None
    classification_ceiling: Optional[str] = None


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
    # ADR-0512/WP-55: whether this task demands a Salesforce-verified
    # project binding as mandatory session context before any tool call,
    # retrieval or model action - checked against agent_def.primary_task
    # in main.py:agent_chat before the graph is ever invoked. False for
    # every task that doesn't declare zuno.project_required: true.
    project_required: bool = False
    # ADR-0419: `zuno.prompts` - named prompt slots keyed by slot name (see
    # PromptSlot above). Empty for every task that doesn't declare any -
    # today, only arkos's draft-architecture-testimonial does.
    prompts: Dict[str, PromptSlot] = field(default_factory=dict)
    # ADR-0544: per-request generation ceiling, forwarded to ai-gateway as
    # X-Zuno-Max-Tokens (app/clients/model_router.py) and, on this side,
    # fed to app/graph/prompt_budget.py as the assembled prompt's output
    # reserve - a task that promises N tokens of reply must have N tokens
    # of the model's window held back for them, or the clamp guarantees a
    # truncated answer. None means no cap (today's exact behavior) and no
    # reserve override (prompt_budget.OUTPUT_RESERVE_TOKENS applies).
    max_tokens: Optional[int] = None


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
    # ADR-0215: whether this agent carries conversation history into its
    # prompts at all - `zuno.memory.history.enabled`, defaulting true and
    # additionally forced off fleet-wide by ZUNO_HISTORY_DISABLED
    # regardless of what the bundle itself declares (see _load_agent).
    history_enabled: bool = True
    # `zuno.memory.history.max_turns` - most recent turn pairs kept
    # verbatim after compaction folds everything older into `summary`.
    history_max_turns: int = HISTORY_MAX_TURNS_DEFAULT
    # `zuno.memory.history.token_budget` - approximate (char/4 heuristic,
    # app/graph/history.py) token budget for summary + verbatim history
    # combined.
    history_token_budget: int = HISTORY_TOKEN_BUDGET_DEFAULT
    # ADR-0527: `zuno.memory.project_context.enabled` - whether this agent
    # carries its conversation's project context into its prompts at all.
    project_context_enabled: bool = True
    # `zuno.memory.project_context.token_budget` - same char/4 heuristic
    # as the history budget (app/graph/history.py's
    # truncate_to_token_budget).
    project_context_token_budget: int = PROJECT_CONTEXT_TOKEN_BUDGET_DEFAULT
    # ADR-0416: `zuno.model.local_only` - an agent-declared, unconditional
    # local-only restriction, independent of the turn's own computed
    # classification (ADR-0034). Distinct from the existing per-tool-call
    # `local_only_required` graph-state flag (ADR-0035, set from a tool
    # result's `external_model_policy.allow_context: false`): that
    # mechanism only fires when a specific restricted source was actually
    # touched this turn, so an agent with no such tool wired yet (or one
    # whose C1/C2 turns simply never touch one) could still reach an
    # external provider. This field is the coarser, agent-level guarantee
    # for an agent that must never do that, full stop - Finage's case.
    local_only: bool = False

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
        """ADR-0106/ADR-0420: only called when signature enforcement is on.
        Requires a `{name}.sig` file plus the one shared `cosign.pub` in the
        signatures directory (the exact output shape the in-cluster Vault
        Transit signing Job produces - see WP-069) and a successful
        `cosign verify-blob` against a freshly recomputed digest, using only
        the committed public key - no Vault access, no network - the same
        verification path `verify_signatures.py`/the signing Job would run,
        imported rather than duplicated (app/_sign_okf_bundle.py, baked in
        by the Dockerfile - imported here rather than at module top level so
        every normal, enforcement-off run - the default, including every
        local test - never needs that file to exist outside the built
        image)."""
        from app import _sign_okf_bundle  # noqa: PLC0415 - see docstring

        sig_path = self._signatures_dir / f"{name}.sig"
        public_key_path = self._signatures_dir / "cosign.pub"
        if not sig_path.is_file() or not public_key_path.is_file():
            raise OkfError(
                f"agents/{name}: signature enforcement is on but no signature found at "
                f"{sig_path} (or no public key at {public_key_path})"
            )
        try:
            _sign_okf_bundle.verify_bundle(agent_dir, sig_path, public_key_path)
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
        # ADR-0215: zuno.memory.history is entirely optional - a bundle
        # that omits it (or omits individual fields within it) rides the
        # module-level defaults above, following zuno.rag.top_k's own
        # parse-with-default pattern immediately above this block.
        memory = zuno.get("memory") or {}
        history = memory.get("history") or {}
        # ADR-0527: zuno.memory.project_context is optional in exactly the
        # same way zuno.memory.history is.
        project_context = memory.get("project_context") or {}
        return AgentDefinition(
            name=name,
            status=zuno.get("status", "placeholder"),
            preferred_classification=model.get("preferred_classification", "C1"),
            rag_top_k=int(rag.get("top_k", 5)),
            tasks=tasks,
            graph_shape=zuno.get("graph_shape"),
            primary_task=zuno.get("primary_task"),
            history_enabled=bool(history.get("enabled", True)) and not HISTORY_DISABLED,
            history_max_turns=int(history.get("max_turns", HISTORY_MAX_TURNS_DEFAULT)),
            history_token_budget=int(history.get("token_budget", HISTORY_TOKEN_BUDGET_DEFAULT)),
            project_context_enabled=bool(project_context.get("enabled", True)),
            project_context_token_budget=int(
                project_context.get("token_budget", PROJECT_CONTEXT_TOKEN_BUDGET_DEFAULT)
            ),
            local_only=bool(model.get("local_only", False)),
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

        prompts: Dict[str, PromptSlot] = {}
        for slot_name, slot_zuno in (zuno.get("prompts") or {}).items():
            slot_zuno = slot_zuno or {}
            # ADR-0419: `<task-name>--<slot>.md` alongside the primary
            # `<task-name>.md` convention above. Silently None if missing -
            # same graceful-degradation posture the primary prompt already
            # has (a stricter validator is noted as future work in the ADR).
            slot_prompt_path = agent_dir / "prompts" / f"{task_name}--{slot_name}.md"
            slot_prompt = None
            if slot_prompt_path.is_file():
                _, slot_prompt = _split_frontmatter(slot_prompt_path)
            prompts[slot_name] = PromptSlot(
                name=slot_name,
                prompt=slot_prompt,
                classification_ceiling=slot_zuno.get("classification_ceiling"),
            )

        return TaskDefinition(
            name=task_name,
            title=frontmatter.get("title", task_name),
            description=body,
            allowed_tools=list(zuno.get("allowed_tools", [])),
            allowed_knowledge=list(zuno.get("allowed_knowledge", [])),
            prompt=prompt,
            live_read_tool=zuno.get("live_read_tool"),
            project_required=bool(zuno.get("project_required", False)),
            prompts=prompts,
            max_tokens=int(zuno["max_tokens"]) if zuno.get("max_tokens") else None,
        )

    def get(self, name: str) -> Optional[AgentDefinition]:
        return self._agents.get(name)

    def all(self) -> List[AgentDefinition]:
        """ADR-0342: iterated once at startup by GraphFactory's fail-fast
        validate_shapes() - every registered agent, not just one hardcoded
        name."""
        return list(self._agents.values())
