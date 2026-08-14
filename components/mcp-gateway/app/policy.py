"""ADR-0011 policy intersection - all five factors, enforced by this
gateway (ADR-0036): agent_declaration and task_rights (from the OKF
bundles under AGENTS_DIR, see app/agent_declarations.py) plus
user_group_rights/classification/platform_policy (from the two files
below).

Loads two files authored by a parallel track (Track B) that this gateway
only *consumes*:

- ``policies/tools/tool-policy.yaml`` -- list of
  ``{tool, mcp_server, min_classification, allowed_groups}`` entries.
- ``policies/data-classification/classification.yaml`` -- flat mapping of
  data domains to C1/C2/C3 (loaded for completeness/future use; the
  gateway's own classification check compares a tool's declared
  ``min_classification`` against the caller-declared
  ``X-Zuno-Data-Classification`` request header rather than re-deriving a
  domain classification itself).

Track B may not have authored these files yet at the time this module is
first deployed. We do not treat that as fatal: the store loads what it can,
records a clear error, and every ``/v1/tools/*/invoke`` call fails closed
(403/503) with that error until the files are present and the store is
reloaded (see ``/admin/reload-policy`` in main.py).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

import yaml

from app.agent_declarations import AgentDeclarationStore

logger = logging.getLogger("mcp_gateway.policy")

TOOL_POLICY_PATH = os.getenv("TOOL_POLICY_PATH", "/app/policies/tools/tool-policy.yaml")
DATA_CLASSIFICATION_PATH = os.getenv(
    "DATA_CLASSIFICATION_PATH", "/app/policies/data-classification/classification.yaml"
)

CLASSIFICATION_RANK = {"C1": 1, "C2": 2, "C3": 3}


@dataclass
class ToolPolicyEntry:
    tool: str
    mcp_server: str
    min_classification: str
    allowed_groups: List[str]
    # ADR-0035: source-level restriction independent of min_classification.
    # False means this tool's result must only ever reach local inference,
    # regardless of what min_classification's own SaaS-eligibility would
    # otherwise permit. Defaults true (no source-level restriction beyond
    # classification) for every tool that doesn't declare otherwise.
    allow_external_context: bool = True
    # ADR-0116: the canonical `<domain>.<resource>.<verb>` capability ID
    # this entry also answers to. `tool` keeps the legacy name as an
    # explicit migration alias; the entry is indexed under both.
    capability: Optional[str] = None


class PolicyStore:
    def __init__(
        self,
        tool_policy_path: str = TOOL_POLICY_PATH,
        classification_path: str = DATA_CLASSIFICATION_PATH,
    ):
        self._tool_policy_path = tool_policy_path
        self._classification_path = classification_path
        self._lock = threading.Lock()
        self._entries: Dict[str, ToolPolicyEntry] = {}
        self._classification: Dict[str, str] = {}
        self._load_error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        with self._lock:
            entries: Dict[str, ToolPolicyEntry] = {}
            classification: Dict[str, str] = {}
            errors: List[str] = []

            try:
                with open(self._tool_policy_path, "r", encoding="utf-8") as fh:
                    raw_doc = yaml.safe_load(fh) or {}
                # tool-policy.yaml's real top-level shape is {"tools": [...]}
                # (see its own header comment) - this used to iterate raw_doc
                # itself (a dict) rather than its "tools" list, which raised
                # "string indices must be integers" on every real load and
                # meant every tool call failed closed (a latent bug this
                # ADR-0036 pass surfaced while adding the agent_declaration/
                # task_rights checks, not something those checks caused).
                raw = raw_doc.get("tools", [])
                for item in raw:
                    entry = ToolPolicyEntry(
                        tool=item["tool"],
                        mcp_server=item["mcp_server"],
                        min_classification=item["min_classification"],
                        allowed_groups=list(item.get("allowed_groups", [])),
                        allow_external_context=bool(
                            (item.get("external_model_policy") or {}).get("allow_context", True)
                        ),
                        capability=item.get("capability"),
                    )
                    # ADR-0116: one entry, two names during migration - the
                    # legacy tool name and the canonical capability ID both
                    # resolve to the same policy decision.
                    entries[entry.tool] = entry
                    if entry.capability:
                        entries[entry.capability] = entry
            except FileNotFoundError:
                msg = (
                    f"tool policy file not found at {self._tool_policy_path} "
                    "(policies/tools/tool-policy.yaml is authored by Track B; "
                    "every tool invocation is denied until it is present and "
                    "this store is reloaded)"
                )
                logger.error(msg)
                errors.append(msg)
            except Exception as exc:  # malformed YAML, missing keys, etc.
                msg = f"failed to parse tool policy file {self._tool_policy_path}: {exc}"
                logger.error(msg)
                errors.append(msg)

            try:
                with open(self._classification_path, "r", encoding="utf-8") as fh:
                    classification = yaml.safe_load(fh) or {}
            except FileNotFoundError:
                msg = (
                    f"data classification file not found at {self._classification_path} "
                    "(policies/data-classification/classification.yaml is authored by "
                    "Track B)"
                )
                logger.warning(msg)
                # Non-fatal: the gateway's own classification check runs off
                # each tool's min_classification, not this file directly.
            except Exception as exc:
                msg = f"failed to parse data classification file {self._classification_path}: {exc}"
                logger.warning(msg)

            self._entries = entries
            self._classification = classification
            self._load_error = "; ".join(errors) if errors else None

    @property
    def loaded(self) -> bool:
        return bool(self._entries) and self._load_error is None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def get_tool(self, tool_name: str) -> Optional[ToolPolicyEntry]:
        return self._entries.get(tool_name)

    def known_tools(self) -> List[str]:
        """Primary (legacy) tool names only - one per policy entry."""
        return sorted({entry.tool for entry in self._entries.values()})

    def policy_names(self) -> List[str]:
        """Every name an entry answers to (legacy tool + canonical
        capability) - the set ADR-0116's binding-coverage validation must
        resolve."""
        return sorted(self._entries.keys())

    def classification_map(self) -> Dict[str, str]:
        return dict(self._classification)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    mcp_server: Optional[str] = None
    # ADR-0035: mirrors the matched entry's allow_external_context so the
    # caller (main.py) can report it back to the Agent Runtime. True when
    # no entry matched (denied calls never reach a model anyway).
    allow_external_context: bool = True


def evaluate(
    store: PolicyStore,
    agents: AgentDeclarationStore,
    tool_name: str,
    agent_name: str,
    task_name: str,
    caller_groups: List[str],
    request_classification: str,
    equivalent_names: Optional[List[str]] = None,
) -> PolicyDecision:
    """The full ADR-0011 intersection, now enforced entirely in this
    gateway (ADR-0036 - previously only the last three of five factors were
    checked here; the agent_declaration and task_rights factors were
    aspirational, deferred to "once Track E authors per-agent OKF tool
    declarations"):

        agent_declaration (agents/<agent>/agent.okf.md, union of its tasks' tools)
        x task_rights      (agents/<agent>/tasks/<task>.md's allowed_tools - narrows, never widens, the agent's own declaration)
        x tool-policy.yaml (routing + allowed_groups + min_classification)
        x caller's Keycloak groups (from the validated JWT)
        x the request's declared data classification

    agent_name/task_name come from the caller-declared X-Zuno-Agent/
    X-Zuno-Task headers (main.py) - required, not optional: a missing or
    unknown declaration fails closed per this ADR's Security
    considerations, the same "any single no is a no" rule as every other
    factor below.

    equivalent_names (ADR-0116): the requested tool's full name-equivalence
    set - its canonical capability ID plus migration aliases, from the
    binding registry. An OKF declaration or policy entry matching ANY name
    in the set matches the tool; this lets bundles/policy migrate from
    legacy names to canonical IDs without a flag day. Defaults to just
    [tool_name] (pre-ADR-0116 behavior).
    """
    names = set(equivalent_names or [tool_name])

    if not agent_name or not task_name:
        return PolicyDecision(allowed=False, reason="missing X-Zuno-Agent/X-Zuno-Task declaration")

    if agents.load_error:
        return PolicyDecision(allowed=False, reason=f"agent declarations unavailable: {agents.load_error}")

    agent = agents.get(agent_name)
    if agent is None:
        return PolicyDecision(allowed=False, reason=f"unknown calling agent '{agent_name}'")

    if not (names & set(agent.declared_tools())):
        return PolicyDecision(
            allowed=False,
            reason=(
                f"agent '{agent_name}' does not declare tool '{tool_name}' in any task "
                "(ADR-0011 agent_declaration)"
            ),
        )

    task_tools = agent.tasks.get(task_name)
    if task_tools is None:
        return PolicyDecision(allowed=False, reason=f"agent '{agent_name}' has no task '{task_name}'")
    if not (names & set(task_tools)):
        return PolicyDecision(
            allowed=False,
            reason=(
                f"task '{task_name}' does not allow tool '{tool_name}' (ADR-0011 task_rights) - "
                "a task can only narrow, never widen, its agent's declaration"
            ),
        )

    if store.load_error:
        return PolicyDecision(allowed=False, reason=f"policy store unavailable: {store.load_error}")

    entry = next((e for e in (store.get_tool(n) for n in names) if e is not None), None)
    if entry is None:
        return PolicyDecision(
            allowed=False, reason=f"unknown tool '{tool_name}' (not present in tool-policy.yaml)"
        )

    if request_classification not in CLASSIFICATION_RANK:
        return PolicyDecision(
            allowed=False,
            reason=(
                f"invalid X-Zuno-Data-Classification '{request_classification}'; "
                "expected one of C1/C2/C3"
            ),
        )
    if entry.min_classification not in CLASSIFICATION_RANK:
        return PolicyDecision(
            allowed=False,
            reason=(
                f"tool-policy.yaml entry for '{tool_name}' has invalid "
                f"min_classification '{entry.min_classification}'"
            ),
        )

    if CLASSIFICATION_RANK[request_classification] < CLASSIFICATION_RANK[entry.min_classification]:
        return PolicyDecision(
            allowed=False,
            reason=(
                f"tool '{tool_name}' requires a request context cleared for at least "
                f"{entry.min_classification}, caller declared {request_classification}"
            ),
        )

    if not (set(caller_groups) & set(entry.allowed_groups)):
        return PolicyDecision(
            allowed=False,
            reason=(
                f"caller groups {caller_groups} do not intersect tool '{tool_name}' "
                f"allowed_groups {entry.allowed_groups}"
            ),
        )

    return PolicyDecision(
        allowed=True,
        reason="allowed",
        mcp_server=entry.mcp_server,
        allow_external_context=entry.allow_external_context,
    )
