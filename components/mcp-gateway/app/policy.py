"""ADR-0011 policy intersection, as far as the MCP Gateway can enforce it.

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
                    raw = yaml.safe_load(fh) or []
                for item in raw:
                    entries[item["tool"]] = ToolPolicyEntry(
                        tool=item["tool"],
                        mcp_server=item["mcp_server"],
                        min_classification=item["min_classification"],
                        allowed_groups=list(item.get("allowed_groups", [])),
                    )
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
        return list(self._entries.keys())

    def classification_map(self) -> Dict[str, str]:
        return dict(self._classification)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    mcp_server: Optional[str] = None


def evaluate(
    store: PolicyStore,
    tool_name: str,
    caller_groups: List[str],
    request_classification: str,
) -> PolicyDecision:
    """The ADR-0011 intersection, scoped to what this gateway can check
    authoritatively:

        tool-policy.yaml (routing + allowed_groups + min_classification)
        x caller's Keycloak groups (from the validated JWT)
        x the request's declared data classification

    The agent's OKF tool declaration and the current task's declared rights
    (the other two terms of ADR-0011's intersection) are enforced upstream
    by the Agent Runtime, which should only ever call a tool its OKF/task
    actually grants. Track E has not authored per-agent OKF tool
    declarations yet (agents/tekos/tasks, agents/tekos/tools are still
    stubs), so an independent second check here is a v1 hardening item, not
    a v0 gap in the layers this service owns.
    """
    if store.load_error:
        return PolicyDecision(allowed=False, reason=f"policy store unavailable: {store.load_error}")

    entry = store.get_tool(tool_name)
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

    return PolicyDecision(allowed=True, reason="allowed", mcp_server=entry.mcp_server)
