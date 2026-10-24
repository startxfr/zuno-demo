"""ADR-0403 / ADR-0401 / ADR-0406: the agent delegation chain.

When an agent delegates to another over A2A (ADR-0402), the call reaches this
gateway as the *target* agent's call (`X-Zuno-Agent`/`X-Zuno-Task` name the target)
carrying the initiating user's own JWT (ADR-0403 clause 1) and two headers that
declare who delegated, outermost delegator first:

    X-Zuno-Delegated-By: tekos:answer-technical-question[,arkos:...]
    X-Zuno-Delegation-Depth: <number of entries>

`parse_chain` reads them, `verify_chain` checks them against the signed OKF
declarations. A call with neither header is a direct call (an empty chain) and is
evaluated exactly as before. This module is not `app/delegation.py`, which is OAuth
credential delegation for tools.

What `verify_chain` does NOT do is authenticate the headers: like `X-Zuno-Agent`
they are not bound to the token (ADR-0403, Residual risk). It constrains them by the
signed declarations, the agents' state and the user's groups.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import yaml

from app.agent_declarations import AgentDeclarationStore

logger = logging.getLogger("mcp_gateway.agent_chain")

LIMITS_POLICY_PATH = os.getenv("LIMITS_POLICY_PATH", "/okf/policies/limits/limits-policy.yaml")

# A syntactic bound on the header, well above any real ceiling: it only stops an
# absurd value being parsed. The real limit is min(max_depth, corp ceiling).
MAX_PARSED_HOPS = 8

_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


class ChainError(ValueError):
    """The delegation headers are malformed or inconsistent."""


@dataclass(frozen=True)
class Hop:
    agent: str
    task: str


@dataclass(frozen=True)
class Chain:
    """The delegators of a call, outermost first. Empty for a direct call."""

    hops: Tuple[Hop, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.hops)

    @property
    def depth(self) -> int:
        return len(self.hops)

    def render(self) -> str:
        return ",".join(f"{h.agent}:{h.task}" for h in self.hops)


def parse_chain(delegated_by: Optional[str], depth: Optional[str]) -> Chain:
    delegated_by, depth = (delegated_by or "").strip(), (depth or "").strip()
    if not delegated_by and not depth:
        return Chain()
    if not delegated_by or not depth:
        raise ChainError("X-Zuno-Delegated-By and X-Zuno-Delegation-Depth must be sent together")
    hops: List[Hop] = []
    for part in delegated_by.split(","):
        agent, sep, task = part.strip().partition(":")
        if not sep or not _NAME.match(agent) or not _NAME.match(task):
            raise ChainError(f"malformed X-Zuno-Delegated-By entry {part.strip()!r}, expected agent:task")
        hops.append(Hop(agent, task))
    if len(hops) > MAX_PARSED_HOPS:
        raise ChainError(f"X-Zuno-Delegated-By lists {len(hops)} entries, more than {MAX_PARSED_HOPS}")
    if not depth.isdigit() or int(depth) != len(hops):
        raise ChainError(
            f"X-Zuno-Delegation-Depth {depth!r} does not match the {len(hops)} entries of X-Zuno-Delegated-By"
        )
    return Chain(tuple(hops))


class DelegationLimits:
    """The corp delegation limits (policies/limits/limits-policy.yaml, ADR-0406).

    A missing or unreadable file yields the safe defaults - a ceiling of 1 and no
    delegated writes - never a looser value."""

    def __init__(self, path: str = LIMITS_POLICY_PATH):
        self._path = path
        self.ceiling = 1
        self.allow_write = False
        self.load_error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        ceiling, allow_write, error = 1, False, None
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
            value = doc.get("max_delegation_depth", 1)
            ceiling = value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else 1
            allow_write = (doc.get("delegation") or {}).get("allow_write") is True
        except FileNotFoundError:
            error = f"limits policy not found at {self._path}; delegation uses the safe defaults"
            logger.warning(error)
        except Exception as exc:  # malformed YAML
            error = f"failed to parse limits policy {self._path}: {exc}; delegation uses the safe defaults"
            logger.error(error)
        self.ceiling, self.allow_write, self.load_error = ceiling, allow_write, error


def verify_chain(
    chain: Chain,
    executing_agent: str,
    executing_task: str,
    caller_groups: List[str],
    agents: AgentDeclarationStore,
    limits: DelegationLimits,
) -> Optional[str]:
    """None when the chain is acceptable, else the reason it is refused.

    ADR-0403 clause 3, in order: every agent exists, is active and is one the
    user is entitled to; no agent repeats; the depth is within min(the origin
    agent's max_depth, the corp ceiling); each hop is a target the previous agent
    declares. Does not touch the tools: those are the target's own, ADR-0011."""
    if not chain:
        return None
    path: List[Tuple[str, str]] = [(h.agent, h.task) for h in chain.hops] + [(executing_agent, executing_task)]
    names = [name for name, _ in path]
    if len(set(names)) != len(names):
        repeated = next(n for n in names if names.count(n) > 1)
        return f"delegation cycle: agent '{repeated}' appears twice in the chain (ADR-0406)"

    declarations = {}
    for name, task in path:
        declaration = agents.get(name)
        if declaration is None:
            return f"unknown agent '{name}' in the delegation chain"
        if declaration.status != "active":
            return f"agent '{name}' is '{declaration.status}', not active (ADR-0584)"
        if task not in declaration.tasks:
            return f"agent '{name}' has no task '{task}' (delegation chain)"
        if not set(declaration.access_groups) & set(caller_groups):
            return f"caller is not entitled to agent '{name}' in the delegation chain (ADR-0040)"
        declarations[name] = declaration

    limit = min(declarations[names[0]].max_depth, limits.ceiling)
    if chain.depth > limit:
        return (
            f"delegation depth {chain.depth} exceeds the limit {limit} "
            f"(agent '{names[0]}' max_depth {declarations[names[0]].max_depth}, corp ceiling {limits.ceiling}; ADR-0406)"
        )

    for (agent, _), (target, target_task) in zip(path, path[1:]):
        if (target, target_task) not in declarations[agent].delegation_targets:
            return f"agent '{agent}' does not declare '{target}/{target_task}' as a delegation target (ADR-0401)"
    return None
