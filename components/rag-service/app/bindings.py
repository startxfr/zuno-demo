"""ADR-0204 knowledge-domain backend-binding registry: resolves a logical
knowledge domain (already authorized by Agent Runtime's
app/knowledge.py:evaluate_knowledge(), ADR-0203) to the physical
PostgreSQL database/schema/credential-env-prefix that serves it. Mirrors
components/mcp-gateway/app/bindings.py's ADR-0116 tool-binding registry:
same fail-closed loader shape, same "platform-controlled, never
caller-supplied" posture.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger("rag_service.bindings")

KNOWLEDGE_BINDINGS_PATH = os.getenv(
    "KNOWLEDGE_BINDINGS_PATH", "/app/platform/bindings/knowledge/bindings.yaml"
)


@dataclass
class KnowledgeBinding:
    domain: str
    database_name: str
    schema: str
    credential_env_prefix: str

    @property
    def pguser_env(self) -> str:
        return f"{self.credential_env_prefix}_PGUSER"

    @property
    def pgpassword_env(self) -> str:
        return f"{self.credential_env_prefix}_PGPASSWORD"


class KnowledgeBindingRegistry:
    def __init__(self, path: str = KNOWLEDGE_BINDINGS_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._bindings: Dict[str, KnowledgeBinding] = {}
        self._load_error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        with self._lock:
            bindings: Dict[str, KnowledgeBinding] = {}
            error: Optional[str] = None
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    doc = yaml.safe_load(fh) or {}
                raw = doc.get("bindings", [])
                for item in raw:
                    domain = item["domain"]
                    if domain in bindings:
                        raise ValueError(f"duplicate binding for domain '{domain}'")
                    database = item.get("database") or {}
                    for required in ("name", "schema", "credential_env_prefix"):
                        if required not in database:
                            raise ValueError(f"binding for '{domain}' missing database.{required}")
                    bindings[domain] = KnowledgeBinding(
                        domain=domain,
                        database_name=database["name"],
                        schema=database["schema"],
                        credential_env_prefix=database["credential_env_prefix"],
                    )
            except FileNotFoundError:
                error = (
                    f"knowledge bindings file not found at {self._path} "
                    "(platform/bindings/knowledge/bindings.yaml is authored by Track B; "
                    "every domain query fails closed until it is present)"
                )
                logger.error(error)
            except Exception as exc:  # malformed YAML, missing keys, duplicates
                error = f"failed to parse knowledge bindings file {self._path}: {exc}"
                logger.error(error)

            self._bindings = bindings
            self._load_error = error

    @property
    def loaded(self) -> bool:
        return bool(self._bindings) and self._load_error is None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def resolve(self, domain: str) -> Optional[KnowledgeBinding]:
        return self._bindings.get(domain)

    def domains(self) -> List[str]:
        return sorted(self._bindings.keys())
