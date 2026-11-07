"""ADR-0602 clause 10 / ADR-0603 M12 (WP-225 lot B): the signed caller context.

A shared-credential MCP server (confluence, git-forge, salesforce, aap) acts with
one technical identity for every caller. To scope that identity to the caller, it
needs to know who the caller is, from something the caller cannot write. This
module gives it that: two headers on every streamable-HTTP call the gateway makes,
after the ADR-0011 decision and from the token the gateway has already validated.

    X-Zuno-Caller-Context:   base64url(JSON {"v", "sub", "groups", "email",
                                             "username", "tool", "iat"})
    X-Zuno-Caller-Signature: hex HMAC-SHA256(key, <the X-Zuno-Caller-Context value>)

`key` is derived from MCP_GATEWAY_WORKLOAD_TOKEN, the secret every downstream server
already holds (ADR-0037), with a label of its own, so the context signature is never
the workload token itself. `tool` is the backend's own tool name, so a context minted
for one tool does not verify for another. `iat` bounds its age.

Nothing here comes from a request argument or a request header: `sub`, `groups`,
`email` and `preferred_username` are read from the validated identity only.

This is not the per-call assertion of ADR-0602 clause 10 (lot C, which replaces the
forwarded bearer). It is narrower: it only tells a server which groups and which
person to scope a call to. The forwarded bearer is unchanged.

The verifying half is duplicated in each server (`_verified_caller`), because each
server image is built from its own directory alone (ADR-0119).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Mapping, Optional

CONTEXT_HEADER = "X-Zuno-Caller-Context"
SIGNATURE_HEADER = "X-Zuno-Caller-Signature"
VERSION = 1
_KEY_LABEL = b"zuno-caller-context-v1"


def derive_key(workload_token: str) -> bytes:
    return hmac.new(workload_token.encode("utf-8"), _KEY_LABEL, hashlib.sha256).digest()


def _claim(claims: Mapping[str, Any], name: str) -> str:
    value = claims.get(name)
    return value.strip() if isinstance(value, str) else ""


def build(
    *,
    sub: str,
    groups: Optional[List[str]],
    claims: Optional[Mapping[str, Any]],
    tool: str,
    workload_token: str,
    now: Optional[float] = None,
) -> Dict[str, str]:
    """The two headers for one downstream call; empty without a workload token
    (the call then fails on X-Zuno-Gateway-Token anyway)."""
    if not workload_token:
        return {}
    claims = claims or {}
    payload = {
        "v": VERSION,
        "sub": sub or "",
        "groups": sorted({str(g) for g in (groups or []) if g}),
        "email": _claim(claims, "email").lower(),
        "username": _claim(claims, "preferred_username"),
        "tool": tool or "",
        "iat": int(now if now is not None else time.time()),
    }
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(derive_key(workload_token), raw.encode("ascii"), hashlib.sha256).hexdigest()
    return {CONTEXT_HEADER: raw, SIGNATURE_HEADER: signature}
