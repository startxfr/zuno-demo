"""ADR-0203 knowledge-authorization policy intersection: the same shape as
components/mcp-gateway/app/policy.py's ADR-0011 tool intersection, but for
RAG retrieval. This runs runtime-side rather than gateway-side because
there is no central gateway between Agent Runtime and rag-service - this
module is the only place that holds agent/task declarations and the
caller's validated JWT groups at the same time. rag-service's own
`app/search.py` ACL filter remains defense in depth underneath it
(document-level ACL/classification, factor 4 below - not duplicated here).

Loads ``policies/knowledge/knowledge-policy.yaml``, authored by Track B, the
same graceful-degradation posture as mcp-gateway's PolicyStore: the store
loads what it can, records a clear error, and every domain fails closed
until the file is present and the store is reloaded.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger("agent_runtime.knowledge")

KNOWLEDGE_POLICY_PATH = os.getenv(
    "KNOWLEDGE_POLICY_PATH", "/app/policies/knowledge/knowledge-policy.yaml"
)


@dataclass
class KnowledgePolicyEntry:
    domain: str
    allowed_groups: List[str]
    # Informational only today (see knowledge-policy.yaml's schema comment) -
    # not yet independently enforced; chunk-level classification (factor 4)
    # is the enforced mechanism until WP-24 wires classification-aware
    # freshness/trust scoring on top of this field.
    min_classification: Optional[str] = None
    source_restrictions: List[str] = field(default_factory=list)


class KnowledgePolicyStore:
    def __init__(self, path: str = KNOWLEDGE_POLICY_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._entries: Dict[str, KnowledgePolicyEntry] = {}
        self._load_error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        with self._lock:
            entries: Dict[str, KnowledgePolicyEntry] = {}
            error: Optional[str] = None
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    doc = yaml.safe_load(fh) or {}
                domains = doc.get("domains", {})
                if not isinstance(domains, dict):
                    raise ValueError(
                        "knowledge-policy.yaml's top-level 'domains' must be a mapping "
                        "keyed by domain id (matches platform/supply-chain/validate_okf_bundle.py's "
                        "_known_knowledge_domains(), which reads it the same way)"
                    )
                for domain_id, spec in domains.items():
                    spec = spec or {}
                    entries[domain_id] = KnowledgePolicyEntry(
                        domain=domain_id,
                        allowed_groups=list(spec.get("allowed_groups", [])),
                        min_classification=spec.get("min_classification"),
                        source_restrictions=list(spec.get("source_restrictions", [])),
                    )
            except FileNotFoundError:
                error = (
                    f"knowledge policy file not found at {self._path} "
                    "(policies/knowledge/knowledge-policy.yaml is authored by Track B; "
                    "every knowledge-domain retrieval is denied until it is present and "
                    "this store is reloaded)"
                )
                logger.error(error)
            except Exception as exc:  # malformed YAML, missing keys, etc.
                error = f"failed to parse knowledge policy file {self._path}: {exc}"
                logger.error(error)

            self._entries = entries
            self._load_error = error

    @property
    def loaded(self) -> bool:
        return bool(self._entries) and self._load_error is None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def get(self, domain: str) -> Optional[KnowledgePolicyEntry]:
        return self._entries.get(domain)


@dataclass
class KnowledgeDecision:
    # Domains authorized for this call - possibly empty, meaning "retrieve
    # from nothing" (the caller must skip the retrieval call entirely, not
    # silently fall back to an unauthorized domain).
    authorized_domains: List[str]
    denied: Dict[str, str]  # domain -> reason


def evaluate_knowledge(
    store: KnowledgePolicyStore,
    agent_declared: List[str],
    task_allowed: List[str],
    caller_groups: List[str],
) -> KnowledgeDecision:
    """The full ADR-0203 intersection (document ACL/classification, factor
    4, is enforced separately downstream by rag-service):

        agent knowledge declaration  (agent_declared - the ceiling)
      x task allowed_knowledge       (task_allowed - narrows, never widens)
      x user business-role rights    (caller_groups intersect allowed_groups)
      x platform knowledge policy    (store)

    Evaluated per domain, independently: ADR-0203's second acceptance bullet
    ("a task that declares knowledge.sales cannot retrieve
    knowledge.sxa-legacy unless both the agent ceiling and platform/user
    policy also allow it") means a task requesting multiple domains can end
    up with some authorized and others denied in the same call, not one
    all-or-nothing verdict for the whole turn.
    """
    authorized: List[str] = []
    denied: Dict[str, str] = {}

    ceiling = set(agent_declared)

    for domain in task_allowed:
        if domain not in ceiling:
            denied[domain] = (
                f"domain '{domain}' is not in the agent's declared knowledge ceiling "
                "(ADR-0203 agent_declaration) - a task can only narrow, never widen it"
            )
            continue

        if store.load_error:
            denied[domain] = f"knowledge policy unavailable: {store.load_error}"
            continue

        entry = store.get(domain)
        if entry is None:
            denied[domain] = f"unknown domain '{domain}' (not present in knowledge-policy.yaml)"
            continue

        if not (set(caller_groups) & set(entry.allowed_groups)):
            denied[domain] = (
                f"caller groups {caller_groups} do not intersect domain '{domain}' "
                f"allowed_groups {entry.allowed_groups}"
            )
            continue

        authorized.append(domain)

    return KnowledgeDecision(authorized_domains=authorized, denied=denied)
