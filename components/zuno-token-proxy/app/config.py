"""Settings of the token proxy, read from the environment (ADR-0601)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple


def _headers(raw: str, name: str) -> Dict[str, str]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError(f"{name} must be a JSON object of string headers")
    return dict(value)


_ALT_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$")


@dataclass(frozen=True)
class AltGateway:
    """WP-297 (ADR-0619 clause 5): one alternative AI gateway this proxy also fronts.

    `url` is the gateway's OpenAI base URL, as the `altGateways` contract writes it
    (it ends with `/v1`): `/alt/<name>/v1/<path>` is relayed to `<url>/<path>`."""

    name: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_s: Optional[float] = None  # None: UPSTREAM_TIMEOUT_S


def _alt_gateways(raw: str) -> Tuple[AltGateway, ...]:
    """ALT_GATEWAYS: a JSON list of {name, url, headers?, timeout_s?}. Unset or empty: none,
    and the proxy behaves as before. A malformed list stops the proxy at start."""
    if not raw.strip():
        return ()
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("ALT_GATEWAYS must be a JSON list")
    found = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("ALT_GATEWAYS: every entry must be a JSON object")
        unknown = set(entry) - {"name", "url", "headers", "timeout_s"}
        if unknown:
            raise ValueError("ALT_GATEWAYS: unknown key(s) " + ", ".join(sorted(unknown)))
        name, url = entry.get("name"), entry.get("url")
        if not isinstance(name, str) or not _ALT_NAME.match(name):
            raise ValueError("ALT_GATEWAYS: name must be a DNS label of at most 40 characters")
        if not isinstance(url, str) or not re.match(r"^https?://[^/\s]+", url):
            raise ValueError(f"ALT_GATEWAYS: {name}: url must be an http(s) URL")
        if any(g.name == name for g in found):
            raise ValueError(f"ALT_GATEWAYS: {name} is listed twice")
        headers = _headers(json.dumps(entry.get("headers") or {}), f"ALT_GATEWAYS {name} headers")
        timeout = entry.get("timeout_s")
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0):
            raise ValueError(f"ALT_GATEWAYS: {name}: timeout_s must be a positive number")
        found.append(AltGateway(name=name, url=url.rstrip("/"), headers=headers,
                                timeout_s=float(timeout) if timeout is not None else None))
    return tuple(found)


def _inbound_keys(path: str) -> Tuple[str, ...]:
    """WP-225 lot C: the keys a caller of this proxy must present, one per line of
    INBOUND_KEYS_FILE (blank lines and `#` comments ignored). Unset: no inbound check,
    as before. Set but unreadable or empty: the proxy refuses to start rather than
    run open."""
    if not path:
        return ()
    with open(path, encoding="utf-8") as handle:
        keys = tuple(line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#"))
    if not keys:
        raise ValueError(f"INBOUND_KEYS_FILE {path} holds no key")
    if any(len(key) < 24 for key in keys):
        raise ValueError("every inbound key must be at least 24 characters")
    return keys


@dataclass(frozen=True)
class Settings:
    token_url: str
    client_id: str
    client_secret: str
    ai_gateway_url: str = "http://ai-gateway.zuno-ai-run.svc:8080"
    mcp_gateway_url: str = "http://mcp-gateway.zuno-ai-run.svc:8080"
    # Fixed headers set on every relayed request, per upstream; they replace any header of the same name.
    ai_headers: Dict[str, str] = field(default_factory=dict)
    mcp_headers: Dict[str, str] = field(default_factory=dict)
    scope: str = ""
    refresh_ratio: float = 0.7
    upstream_timeout_s: float = 300.0
    # WP-208 defect D1: an MCP call that gets no byte within this time fails fast instead of hanging for 300 s.
    mcp_timeout_s: float = 30.0
    token_timeout_s: float = 10.0
    ca_bundle: Optional[str] = None
    # WP-225 lot C (ADR-0602 clause 10): the keys a caller must send as
    # `Authorization: Bearer <key>`; empty means no inbound check (the default).
    inbound_keys: Tuple[str, ...] = ()
    # WP-297 (ADR-0619 clause 5): the alternative gateways reached at /alt/<name>/v1/...; empty by default.
    alt_gateways: Tuple[AltGateway, ...] = ()

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if env is None else env
        secret = env.get("CLIENT_SECRET", "")
        secret_file = env.get("CLIENT_SECRET_FILE", "")
        if not secret and secret_file:
            with open(secret_file, encoding="utf-8") as handle:
                secret = handle.read().strip()
        missing = [n for n, v in (("TOKEN_URL", env.get("TOKEN_URL", "")), ("CLIENT_ID", env.get("CLIENT_ID", "")),
                                  ("CLIENT_SECRET", secret)) if not v]
        if missing:
            raise ValueError("missing settings: " + ", ".join(missing))
        ratio = float(env.get("REFRESH_RATIO", "0.7"))
        if not 0.1 <= ratio <= 0.95:
            raise ValueError("REFRESH_RATIO must be between 0.1 and 0.95")
        return cls(
            token_url=env["TOKEN_URL"],
            client_id=env["CLIENT_ID"],
            client_secret=secret,
            ai_gateway_url=env.get("AI_GATEWAY_URL", cls.ai_gateway_url).rstrip("/"),
            mcp_gateway_url=env.get("MCP_GATEWAY_URL", cls.mcp_gateway_url).rstrip("/"),
            ai_headers=_headers(env.get("AI_HEADERS", ""), "AI_HEADERS"),
            mcp_headers=_headers(env.get("MCP_HEADERS", ""), "MCP_HEADERS"),
            scope=env.get("TOKEN_SCOPE", ""),
            refresh_ratio=ratio,
            upstream_timeout_s=float(env.get("UPSTREAM_TIMEOUT_S", "300")),
            mcp_timeout_s=float(env.get("MCP_TIMEOUT_S", "30")),
            token_timeout_s=float(env.get("TOKEN_TIMEOUT_S", "10")),
            ca_bundle=env.get("CA_BUNDLE") or None,
            inbound_keys=_inbound_keys(env.get("INBOUND_KEYS_FILE", "")),
            alt_gateways=_alt_gateways(env.get("ALT_GATEWAYS", "")),
        )
