"""ADR-0208 (WP-26): delegated-user credential resolution.

`delegated-user` auth_mode requires the CALLER's own delegated credential
for the specific downstream provider (ADR-0014: per-user delegated OAuth2,
never domain-wide service-account impersonation) - a missing delegated
credential is a deterministic denial, never a silent fallback to the
gateway's own service identity (that would defeat the entire point of the
mode: a user whose Google permission was revoked must lose access even
though Zuno's own policy still allows the logical capability).

The real credential source is Keycloak's Google identity-provider broker
(`storeToken: true`, `gitops/charts/keycloak/files/realm-zuno.json`),
resolved via `/realms/zuno/broker/google/token` - no component in this
repository calls that endpoint yet, because no live Google Workspace
tenant is reachable from this environment (see app/handlers/drive.py's
own docstring, and components/mcp-servers/google-workspace/, which is
still only a placeholder). This module is therefore a deliberate,
documented seam rather than a finished integration: the CONTRACT (deny
without a token, never fall back to a shared credential) is what ADR-0208
requires and is fully enforced today; the concrete broker-token call
arrives with a live Google Workspace/Keycloak integration, at which point
only `_resolve_via_keycloak_broker` below needs implementing - every
caller of `get_delegated_token` is already correct.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("mcp_gateway.delegation")

# Test-only injection point (set_token_resolver) - production code never
# calls this; get_delegated_token falls back to the real (currently
# unimplemented) broker resolution below. A resolver is
# (provider, caller_sub) -> delegated token or None.
_test_resolver: Optional[Callable[[str, str], Optional[str]]] = None


def set_token_resolver(resolver: Optional[Callable[[str, str], Optional[str]]]) -> None:
    """Test-only hook: injects a fake delegated-token source so
    delegated-user enforcement can be exercised without a live Keycloak
    broker (ADR-0208's acceptance criteria explicitly call for this -
    "revoked-Google-permission behavior asserted at the mock level; real
    revocation is the operator check"). Never called from production
    startup code."""
    global _test_resolver
    _test_resolver = resolver


def _resolve_via_keycloak_broker(provider: str, caller_sub: str) -> Optional[str]:
    """Not yet implemented - see module docstring. Returning None here is
    correct today: it makes every delegated-user call deny closed, which
    is right when no real broker integration exists (delegated-user
    binding NEVER falls back to a shared credential, so "no token
    resolvable" and "user's Google permission was revoked" both look
    identical, deliberately - the same fail-closed outcome ADR-0208
    requires for a revoked token)."""
    return None


def get_delegated_token(provider: str, caller_sub: str) -> Optional[str]:
    """Returns the caller's delegated credential for `provider`, or None
    if none is available - callers must treat None as a deterministic
    denial (app/main.py's invoke_tool), never as "fall back to
    service-identity"."""
    if _test_resolver is not None:
        return _test_resolver(provider, caller_sub)
    return _resolve_via_keycloak_broker(provider, caller_sub)
