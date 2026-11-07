"""ADR-0602 clause 10 / ADR-0603 M14 (WP-225 lot C): the per-call assertion.

Until lot C the gateway forwarded the caller's own Keycloak bearer to every
streamable-HTTP backend. None of them uses it (each acts with its own technical
credential, after the gateway's ADR-0011 decision), so the user's token was only
exposure: a backend, or anything that reads its traffic, could replay it against
every other service that accepts the `zuno-admin-api` audience.

With `MCP_OUTBOUND_IDENTITY=assertion` the gateway sends, instead of that bearer,
a short-lived JWT it signs itself, one per tool call:

    Authorization: Bearer <compact JWS, EdDSA (Ed25519), typ zuno-call+jwt>

    {"iss": "mcp-gateway", "aud": "<the binding's backend>", "sub": "<caller sub>",
     "act": {"sub": "mcp-gateway"}, "tool": "<the backend's own tool name>",
     "args": "<sha256 of the canonical JSON of the tool arguments>",
     "iat": ..., "exp": <iat + at most 60 s>, "jti": "<uuid>"}

Only the gateway holds the private key (MCP_CALL_ASSERTION_KEY_FILE); each Zuno
server holds the public key and verifies it (`CallAssertionMiddleware`, the same
block in confluence, git-forge, salesforce and aap). Unlike the workload token and
the lot B caller context, a backend cannot mint one. A backend refuses an
assertion that is forged, expired, longer-lived than 60 s, addressed to another
backend, minted for another tool or other arguments, or replayed (its `jti` is consumed by the one
`tools/call` it was minted for).

Per binding (platform/bindings/tools/tool-bindings.yaml), in assertion mode:
- `user_token: true`: the backend needs the caller's own token (a
  provider-delegated backend); the bearer is forwarded, as before;
- `gateway_token: true` (a Zuno server): the assertion;
- otherwise (a third-party backend, kubernetes-mcp-server): no Authorization at all.

`MCP_OUTBOUND_IDENTITY=bearer` (the default) keeps today's forwarding. In
assertion mode a missing or unreadable key fails the call (502): the gateway never
falls back to the user's bearer.

RFC 8693 token exchange was the other option of clause 10. It was not chosen:
it needs a Keycloak round trip per tool call, one client (or audience) per
backend in a realm whose import is create-only, and Keycloak JWKS reachability
and CA trust in every backend; the assertion needs none of these and is verified
offline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger("mcp_gateway.call_assertion")

TYPE = "zuno-call+jwt"
ISSUER = "mcp-gateway"
ALGORITHM = "EdDSA"
MAX_TTL_SECONDS = 60
# The `sub` of an assertion the gateway mints for itself (a tools/list schema read),
# never a caller: it carries no `tool`, so no tools/call verifies with it.
SELF_SUBJECT = "system:mcp-gateway"

MODES = ("bearer", "assertion")

_KEY_CACHE: Dict[str, Tuple[float, Ed25519PrivateKey]] = {}


class AssertionUnavailable(RuntimeError):
    """Assertion mode is on but the signing key cannot be used."""


def mode() -> str:
    """MCP_OUTBOUND_IDENTITY, read per call: `bearer` (default) or `assertion`."""
    raw = (os.getenv("MCP_OUTBOUND_IDENTITY") or "bearer").strip().lower()
    if raw not in MODES:
        logger.error("MCP_OUTBOUND_IDENTITY=%r is not one of %s; using bearer", raw, MODES)
        return "bearer"
    return raw


def ttl_seconds() -> int:
    raw = (os.getenv("MCP_CALL_ASSERTION_TTL_SECONDS") or "").strip()
    try:
        value = int(raw) if raw else MAX_TTL_SECONDS
    except ValueError:
        value = MAX_TTL_SECONDS
    return max(5, min(value, MAX_TTL_SECONDS))


def signing_key() -> Ed25519PrivateKey:
    path = (os.getenv("MCP_CALL_ASSERTION_KEY_FILE") or "").strip()
    if not path:
        raise AssertionUnavailable("MCP_CALL_ASSERTION_KEY_FILE is not set")
    try:
        stamp = os.stat(path).st_mtime
        cached = _KEY_CACHE.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
        with open(path, "rb") as handle:
            key = serialization.load_pem_private_key(handle.read(), password=None)
    except (OSError, ValueError) as exc:
        raise AssertionUnavailable(f"call-assertion key {path} is unusable: {exc}") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise AssertionUnavailable(f"call-assertion key {path} is not an Ed25519 private key")
    _KEY_CACHE[path] = (stamp, key)
    return key


def args_hash(arguments: Any) -> str:
    """The `args` claim: sha256 of the canonical JSON of the tool arguments. The
    servers compute the same over the tools/call params.arguments they receive."""
    canonical = json.dumps(arguments if arguments is not None else {}, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mint(
    *,
    audience: str,
    sub: str,
    tool: str,
    arguments: Any = None,
    key: Optional[Ed25519PrivateKey] = None,
    ttl: Optional[int] = None,
    now: Optional[float] = None,
) -> str:
    if not audience:
        raise AssertionUnavailable("an assertion needs the backend name as its audience")
    issued = int(now if now is not None else time.time())
    lifetime = max(1, min(int(ttl if ttl is not None else ttl_seconds()), MAX_TTL_SECONDS))
    claims: Dict[str, Any] = {
        "iss": ISSUER,
        "aud": audience,
        "sub": sub or "",
        "act": {"sub": ISSUER},
        "tool": tool or "",
        "iat": issued,
        "exp": issued + lifetime,
        "jti": uuid.uuid4().hex,
    }
    if tool:
        # A schema-read assertion (no tool) carries no args; it can call nothing.
        claims["args"] = args_hash(arguments)
    return jwt.encode(claims, key or signing_key(), algorithm=ALGORITHM, headers={"typ": TYPE})


def authorization_for(
    binding: Any, bearer_token: str, *, sub: str, tool: str, arguments: Any = None
) -> Optional[str]:
    """The Authorization header of one streamable-HTTP tool call, or None for none."""
    if mode() == "bearer" or getattr(binding, "user_token", False):
        return f"Bearer {bearer_token}"
    if not getattr(binding, "gateway_token", True):
        return None  # a third-party backend: it receives no identity at all
    return "Bearer " + mint(audience=binding.backend, sub=sub, tool=tool, arguments=arguments)


def schema_authorization_for(backend: str, gateway_token: bool) -> Optional[str]:
    """The Authorization header of a tools/list schema read: none in bearer mode
    (as before), an assertion for the gateway itself in assertion mode."""
    if mode() == "bearer" or not gateway_token or not backend:
        return None
    return "Bearer " + mint(audience=backend, sub=SELF_SUBJECT, tool="")
