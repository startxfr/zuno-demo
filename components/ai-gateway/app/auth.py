"""JWT validation for the AI Inference Gateway (ADR-0009, ADR-0012, ADR-0013).

Structurally identical to components/mcp-gateway/app/auth.py and
components/agent-runtime/app/auth.py - three independently deployable
services, so the ~60 lines are duplicated rather than factored into a
shared package the repo doesn't otherwise have (see agent-runtime's copy
for the fuller rationale). This gateway only needs authenticated-caller
verification (`sub`) - unlike mcp-gateway, it has no per-caller
authorization decision keyed on `groups` (routing is classification-driven,
not group-driven), but `groups` is still extracted for consistency and
future use (e.g. per-group budgets, ADR-0009's deferred scope).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import jwt
from fastapi import Header, HTTPException, status
from jwt import PyJWKClient

logger = logging.getLogger("ai_gateway.auth")

KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER", "https://keycloak.apps.mycluster.example.com/realms/zuno"
)
KEYCLOAK_JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL", f"{KEYCLOAK_ISSUER}/protocol/openid-connect/certs"
)
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE") or None


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# ADR-0602 / WP-222: with JWT_AUDIENCE unset, any token the realm signs is
# accepted, whichever client it was minted for. JWT_AUDIENCE_REQUIRED=true
# turns that silent default into a startup failure. The charts set both
# (audience zuno-admin-api, carried by every experience client through the
# maas-gateway-audience mapper); the code default stays off for local runs.
if _truthy(os.getenv("JWT_AUDIENCE_REQUIRED")) and not JWT_AUDIENCE:
    raise RuntimeError("JWT_AUDIENCE_REQUIRED is set but JWT_AUDIENCE is empty; refusing to start.")


def admin_groups() -> List[str]:
    """Groups allowed to call /admin/* (ADR-0602). Read per call."""
    raw = os.getenv("ADMIN_GROUPS", "ocp-paas-ops,ocp-ai-ops")
    return [g.strip() for g in raw.split(",") if g.strip()]
JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "30"))


def allowed_clients() -> List[str]:
    """ADR-0602 clause 10 (WP-225 lot C): the Keycloak clients (`azp`) whose tokens
    this gateway accepts, from JWT_ALLOWED_CLIENTS (comma-separated, read per call;
    an entry ending in `*` is a prefix). Empty, the default, accepts every client
    the audience admits, as before. Set, a token from another client, or without
    `azp`, is refused with a 401: on top of the `zuno-admin-api` audience
    (WP-222), each experience is then admitted by name."""
    raw = os.getenv("JWT_ALLOWED_CLIENTS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


# WP-225 lot C review: a bare "*" would turn the allowlist into "every client" while
# looking like a control; refuse to start instead.
if "*" in allowed_clients():
    raise RuntimeError("JWT_ALLOWED_CLIENTS contains a bare '*'; list the clients (a prefix like 'openclaw-*' is fine).")


def client_allowed(azp: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        if pattern == "*":
            continue  # a bare "*" would admit every client: refused at start, never a match
        if pattern.endswith("*"):
            if azp.startswith(pattern[:-1]) and len(azp) > len(pattern) - 1:
                return True
        elif azp == pattern:
            return True
    return False


def trusted_platform_clients() -> set:
    """Keycloak clients (the token's `azp`) whose calls may set the
    platform-side request context: a non-standard quota class and a project
    id (ADR-0511, ADR-0528). Comma-separated TRUSTED_PLATFORM_CLIENTS, read
    per call; empty (the default) trusts no client, so those headers are
    ignored on every call."""
    raw = os.getenv("TRUSTED_PLATFORM_CLIENTS", "")
    return {c.strip() for c in raw.split(",") if c.strip()}

# ADR-0593: the token claim that names the persona a client acts for, and the
# clients allowed to carry it (an entry ending in `*` is a prefix). Read per
# call; only the OpenClaw clients by default.
PERSONA_CLAIM = "persona"
SERVICE_ACCOUNT_PREFIX = "service-account-"


def persona_claim_clients() -> List[str]:
    raw = os.getenv("PERSONA_CLAIM_CLIENTS", "openclaw-*")
    return [c.strip() for c in raw.split(",") if c.strip()]


def _client_matches(azp: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("*"):
            if azp.startswith(pattern[:-1]) and len(azp) > len(pattern) - 1:
                return True
        elif azp == pattern:
            return True
    return False


_jwks_client: Optional[PyJWKClient] = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(KEYCLOAK_JWKS_URL, cache_keys=True, lifespan=300)
    return _jwks_client


@dataclass
class CallerIdentity:
    sub: str
    groups: List[str]
    raw_claims: dict
    token: str

    @property
    def client(self) -> str:
        """The Keycloak client the token was issued to (`azp`), "" if absent.
        ADR-0587: names the user experience (unifai, open-webui,
        openclaw-<persona>) on the metrics; never an authorisation input."""
        return str((self.raw_claims or {}).get("azp") or "")

    @property
    def persona(self) -> str:
        """ADR-0593: whose per-user budget and `user` label this call counts
        against, from validated claims only - never a header. In order: the
        `persona` claim, honoured only when `azp` is one of
        PERSONA_CLAIM_CLIENTS (the OpenClaw clients, whose tokens belong to a
        service account acting for one persona); else `preferred_username` of
        a person's token (unique and not user-editable in realm zuno); else
        `sub`. A `service-account-*` username is never a persona."""
        claims = self.raw_claims or {}
        claim = claims.get(PERSONA_CLAIM)
        if isinstance(claim, str) and claim.strip() and _client_matches(self.client, persona_claim_clients()):
            return claim.strip()
        username = claims.get("preferred_username")
        if isinstance(username, str) and username.strip() and not username.startswith(SERVICE_ACCOUNT_PREFIX):
            return username.strip()
        return self.sub

    @property
    def is_trusted_platform_client(self) -> bool:
        client = (self.raw_claims or {}).get("azp")
        return bool(client) and client in trusted_platform_clients()


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header; expected 'Bearer <token>'.",
        )
    return authorization.split(" ", 1)[1].strip()


def validate_token(authorization: Optional[str] = Header(default=None)) -> CallerIdentity:
    token = _extract_bearer_token(authorization)
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=JWT_AUDIENCE,
            issuer=KEYCLOAK_ISSUER,
            leeway=JWT_LEEWAY_SECONDS,
            options={"verify_aud": JWT_AUDIENCE is not None},
        )
    except jwt.PyJWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unable to validate JWT against Keycloak JWKS at %s: %s", KEYCLOAK_JWKS_URL, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider unreachable; cannot validate caller identity.",
        ) from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim.")

    patterns = allowed_clients()
    if patterns and not client_allowed(str(claims.get("azp") or ""), patterns):
        logger.warning("token of client %r refused (JWT_ALLOWED_CLIENTS)", claims.get("azp"))
        raise HTTPException(status_code=401, detail="Token issued to a client this gateway does not accept.")

    groups = claims.get("groups", []) or []
    return CallerIdentity(sub=sub, groups=[g.lstrip("/") for g in groups], raw_claims=claims, token=token)


def require_admin(authorization: Optional[str] = Header(default=None)) -> CallerIdentity:
    """Dependency for /admin/*: a valid token whose groups include one of
    ADMIN_GROUPS. ADMIN_AUTH_MODE=off restores the old network-only trust
    (ADR-0602 keeps it as an explicit, visible opt-out)."""
    if (os.getenv("ADMIN_AUTH_MODE", "enforce") or "enforce").strip().lower() == "off":
        return CallerIdentity(sub="admin-auth-off", groups=[], raw_claims={}, token="")
    identity = validate_token(authorization)
    if not set(identity.groups) & set(admin_groups()):
        logger.warning("admin call refused for sub=%s", identity.sub)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin group required.")
    return identity
