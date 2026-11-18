"""WP-250 lot 2: test helper. The MCP servers trust the gateway's Vault-Transit-signed call assertion only
(the shared X-Zuno-Gateway-Token and the HMAC caller-context headers are retired), so a test that talks to a
server's app must send an assertion. This module mints them with a throwaway Ed25519 key and points the server
at the matching public key.

    from test_support.assertion_headers import headers_for        # after sys.path gets components/mcp-servers
    headers_for("confluence", "read_page", groups=["consultant"])  # -> {"Authorization": "Bearer ..."}

One assertion covers one session with ONE tools/call of the named tool (the server consumes its jti on the call).
`arguments` is bound when given (the `args` hash the server checks); leave it out and no `args` claim is minted,
which the server accepts. `groups=None` mints an assertion with no `ctx` claim (a caller the server cannot scope).
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY = Ed25519PrivateKey.generate()
PUBLIC_PEM = KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
os.environ["MCP_CALL_ASSERTION_PUBLIC_KEY"] = PUBLIC_PEM

_NO_ARGS = object()


def assertion(audience: str, tool: str, *, groups: Optional[List[str]] = None, email: str = "u1@example.com",
              email_verified: bool = False, username: str = "u-1", sub: str = "u-1", arguments: Any = _NO_ARGS,
              ctx: Optional[Dict[str, Any]] = None, now: Optional[float] = None, key: Ed25519PrivateKey = KEY) -> str:
    issued = int(now if now is not None else time.time())
    claims: Dict[str, Any] = {
        "iss": "mcp-gateway", "aud": audience, "sub": sub, "act": {"sub": "mcp-gateway"}, "tool": tool,
        "iat": issued, "exp": issued + 60, "jti": uuid.uuid4().hex,
    }
    if arguments is not _NO_ARGS:
        import hashlib
        import json
        canonical = json.dumps(arguments if arguments is not None else {}, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False)
        claims["args"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if ctx is not None:
        claims["ctx"] = ctx
    elif groups is not None:
        claims["ctx"] = {"groups": sorted(groups), "email": email.lower(), "email_verified": email_verified,
                         "username": username}
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"typ": "zuno-call+jwt"})


def headers_for(audience: str, tool: str, **kwargs: Any) -> Dict[str, str]:
    return {"Authorization": "Bearer " + assertion(audience, tool, **kwargs)}
