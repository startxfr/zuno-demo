"""ADR-0116 backend-binding registry - resolves an authorized logical tool
capability (``<domain>.<resource>.<verb>``, or a legacy alias kept during
migration) to the physical backend that serves it.

Loads ``platform/bindings/tools/tool-bindings.yaml`` (baked into the image
from the repo root, same pattern as app/policy.py's policy files) with the
same graceful-degradation contract as PolicyStore: a missing/malformed file
is not fatal at startup, but every resolution fails closed (``resolve()``
returns ``None``) and readiness reports the load error until the file is
present and the registry is reloaded (``/admin/reload-policy``).

Fail-closed invariants (ADR-0116 Security/Operational considerations):

- an unknown name never falls through to a default backend;
- a capability with zero or duplicate entries never loads;
- ``validate_policy_coverage()`` flags every policy-listed tool name that
  does not resolve to exactly one binding, for startup/readiness checks.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger("mcp_gateway.bindings")

TOOL_BINDINGS_PATH = os.getenv(
    "TOOL_BINDINGS_PATH", "/app/platform/bindings/tools/tool-bindings.yaml"
)

VALID_TRANSPORTS = {"streamable-http", "in-process"}


@dataclass
class Binding:
    capability: str
    backend: str
    transport: str
    provider_tool: str
    aliases: List[str] = field(default_factory=list)
    # streamable-http only: {env, default, path}
    endpoint: Optional[Dict[str, str]] = None
    # in-process only: handler module name under app/handlers/
    handler: Optional[str] = None

    def all_names(self) -> List[str]:
        """The capability plus its aliases - the equivalence set used for
        policy/agent-declaration matching during migration."""
        return [self.capability, *self.aliases]

    def endpoint_url(self) -> str:
        """Resolve the backend base URL at call time (environment first,
        registry default second) - binding data, never caller-supplied."""
        if not self.endpoint:
            raise ValueError(f"binding '{self.capability}' has no endpoint")
        base = os.getenv(self.endpoint.get("env", ""), "") or self.endpoint.get("default", "")
        return f"{base}{self.endpoint.get('path', '')}"


class BindingRegistry:
    def __init__(self, path: str = TOOL_BINDINGS_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._by_name: Dict[str, Binding] = {}
        self._bindings: List[Binding] = []
        self._load_error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        with self._lock:
            by_name: Dict[str, Binding] = {}
            bindings: List[Binding] = []
            errors: List[str] = []

            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    raw_doc = yaml.safe_load(fh) or {}
                for item in raw_doc.get("bindings", []):
                    binding = Binding(
                        capability=item["capability"],
                        backend=item["backend"],
                        transport=item["transport"],
                        provider_tool=item["provider_tool"],
                        aliases=list(item.get("aliases", [])),
                        endpoint=item.get("endpoint"),
                        handler=item.get("handler"),
                    )
                    problem = _validate(binding)
                    if problem:
                        errors.append(problem)
                        continue
                    for name in binding.all_names():
                        if name in by_name:
                            errors.append(
                                f"duplicate binding name '{name}' (capability "
                                f"'{binding.capability}' collides with "
                                f"'{by_name[name].capability}') - a capability must "
                                "have exactly one active binding"
                            )
                            break
                    else:
                        for name in binding.all_names():
                            by_name[name] = binding
                        bindings.append(binding)
            except FileNotFoundError:
                msg = (
                    f"tool bindings file not found at {self._path} "
                    "(platform/bindings/tools/tool-bindings.yaml, ADR-0116; every "
                    "tool invocation is denied until it is present and this "
                    "registry is reloaded)"
                )
                logger.error(msg)
                errors.append(msg)
            except Exception as exc:  # malformed YAML, missing keys, etc.
                msg = f"failed to parse tool bindings file {self._path}: {exc}"
                logger.error(msg)
                errors.append(msg)

            self._by_name = by_name
            self._bindings = bindings
            self._load_error = "; ".join(errors) if errors else None

    @property
    def loaded(self) -> bool:
        return bool(self._bindings) and self._load_error is None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def resolve(self, capability_or_alias: str) -> Optional[Binding]:
        """Canonical ID or migration alias -> its one binding; ``None`` for
        anything unknown (fail closed - the caller must deny, never guess a
        backend)."""
        return self._by_name.get(capability_or_alias)

    def capabilities(self) -> List[str]:
        return [b.capability for b in self._bindings]

    def validate_policy_coverage(self, policy_tool_names: List[str]) -> List[str]:
        """ADR-0116 Operational considerations: every enabled policy
        capability must have exactly one valid active binding. Returns one
        message per policy name that fails to resolve (duplicates are
        already rejected at load time)."""
        return [
            f"policy tool '{name}' has no binding in {self._path}"
            for name in policy_tool_names
            if self.resolve(name) is None
        ]


def _validate(binding: Binding) -> Optional[str]:
    if binding.transport not in VALID_TRANSPORTS:
        return (
            f"binding '{binding.capability}' has unknown transport "
            f"'{binding.transport}' (expected one of {sorted(VALID_TRANSPORTS)})"
        )
    if binding.transport == "streamable-http" and not binding.endpoint:
        return f"streamable-http binding '{binding.capability}' is missing its endpoint"
    if binding.transport == "in-process" and not binding.handler:
        return f"in-process binding '{binding.capability}' is missing its handler name"
    return None
