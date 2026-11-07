"""Settings of the Dify External Knowledge adapter, read from the environment (ADR-0599, WP-205)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional


def _knowledge_bases(raw: str) -> Dict[str, str]:
    """``id=tag,id=tag``: the knowledge_id Dify sends, and the tag it stands for."""
    bases: Dict[str, str] = {}
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        knowledge_id, _, tag = item.partition("=")
        if not knowledge_id.strip() or not tag.strip():
            raise ValueError("KNOWLEDGE_BASES must be a comma-separated list of id=tag")
        bases[knowledge_id.strip()] = tag.strip()
    if not bases:
        raise ValueError("KNOWLEDGE_BASES lists no knowledge base")
    return bases


def _read_optional(path: str) -> str:
    """The first non-comment line of `path`; "" when unset. Set but unreadable fails the start."""
    if not path:
        return ""
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip() and not line.lstrip().startswith("#"):
                return line.strip()
    raise ValueError(f"PROXY_KEY_FILE {path} holds no key")


@dataclass(frozen=True)
class Settings:
    api_key: str
    # The token proxy of the same namespace: it holds the client-credentials token (ADR-0601).
    mcp_url: str = "http://zuno-token-proxy:8080/mcp"
    tool_name: str = "knowledge.tech.search"  # the capability name of tools/list; the alias search_technical_docs also resolves
    # knowledge_id -> tag. The tool searches the tag configured on the mcp-gateway
    # (UNIFAI_RAG_TAG); the map only decides which ids this adapter admits.
    knowledge_bases: Optional[Dict[str, str]] = None
    max_top_k: int = 20
    upstream_timeout_s: float = 30.0
    # WP-225 lot C: the key the token proxy asks of its callers (INBOUND_KEYS_FILE there),
    # sent as `Authorization: Bearer <key>`; empty sends none (the default, as before).
    proxy_key: str = ""

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if env is None else env
        key = env.get("API_KEY", "")
        key_file = env.get("API_KEY_FILE", "")
        if not key and key_file:
            with open(key_file, encoding="utf-8") as handle:
                key = handle.read().strip()
        if not key:
            raise ValueError("missing settings: API_KEY or API_KEY_FILE")
        return cls(
            api_key=key,
            mcp_url=env.get("MCP_URL", cls.mcp_url).rstrip("/"),
            tool_name=env.get("TOOL_NAME", cls.tool_name),
            knowledge_bases=_knowledge_bases(env.get("KNOWLEDGE_BASES", "tech=knowledge.tech")),
            max_top_k=int(env.get("MAX_TOP_K", "20")),
            upstream_timeout_s=float(env.get("UPSTREAM_TIMEOUT_S", "30")),
            proxy_key=_read_optional(env.get("PROXY_KEY_FILE", "")),
        )
