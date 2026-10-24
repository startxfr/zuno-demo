"""Runtime settings of the A2A gateway, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Where the agents' A2A cards say they can be reached (the URL UnifAI's A2A client posts to).
    public_base_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://a2a-gateway.zuno-ai-run.svc:8080").rstrip("/")
    )
    ai_gateway_url: str = field(
        default_factory=lambda: os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc:8080").rstrip("/")
    )
    mcp_gateway_url: str = field(
        default_factory=lambda: os.getenv("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai-run.svc:8080").rstrip("/")
    )
    # Tool use through the mcp-gateway (its five-factor policy applies to the caller's own token).
    tools_enabled: bool = field(default_factory=lambda: os.getenv("A2A_TOOLS_ENABLED", "true").lower() == "true")
    max_tool_rounds: int = field(default_factory=lambda: int(os.getenv("A2A_MAX_TOOL_ROUNDS", "3")))
    request_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("A2A_REQUEST_TIMEOUT", "120")))
    max_message_chars: int = field(default_factory=lambda: int(os.getenv("A2A_MAX_MESSAGE_CHARS", "20000")))
    agents_dir: str = field(default_factory=lambda: os.getenv("AGENTS_DIR", "/okf/agents"))
    limits_policy_path: str = field(
        default_factory=lambda: os.getenv("LIMITS_POLICY_PATH", "/okf/policies/limits/limits-policy.yaml")
    )
    version: str = field(default_factory=lambda: os.getenv("A2A_GATEWAY_VERSION", "0.1.0"))
