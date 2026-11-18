"""ADR-0602 clause 10 / ADR-0603 M12 (WP-225 lot B, WP-250): the caller context.

A shared-credential MCP server (confluence, git-forge, salesforce, aap) acts with one technical identity for every
caller. To scope that identity to the caller it needs to know who the caller is, from something the caller cannot
write. Since WP-250 that something is the per-call assertion the gateway signs with Vault Transit
(app/call_assertion.py): for bindings declaring `caller_context: true` the assertion carries a `ctx` claim built here,

    {"groups": [...], "email": "...", "email_verified": bool, "username": "..."}

and each server reads it from the VERIFIED assertion only (`_assertion_caller` in its call-assertion block). The
earlier mechanism, an HMAC keyed by the shared MCP_GATEWAY_WORKLOAD_TOKEN and sent as X-Zuno-Caller-Context /
X-Zuno-Caller-Signature, and the token itself, are retired: nothing here is a secret any more.

Nothing here comes from a request argument or a request header: `groups`, `email` and `preferred_username` are read
from the validated identity only. `email_verified` is the token's claim as a JSON boolean true only: Keycloak lets a
user edit the email when the realm does not verify it, so an unverified address names nobody.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


def _claim(claims: Mapping[str, Any], name: str) -> str:
    value = claims.get(name)
    return value.strip() if isinstance(value, str) else ""


def assertion_context(*, groups: Optional[List[str]], claims: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The `ctx` claim of a tool-call assertion, from the validated identity only."""
    claims = claims or {}
    return {
        "groups": sorted({str(g) for g in (groups or []) if g}),
        "email": _claim(claims, "email").lower(),
        "email_verified": claims.get("email_verified") is True,
        "username": _claim(claims, "preferred_username"),
    }
