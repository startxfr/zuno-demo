"""JWT validation for the A2A gateway (ADR-0010, ADR-0012, ADR-0013).

Same contract as components/mcp-gateway/app/auth.py (this repo duplicates small, well-specified
auth code per service on purpose): RS256 signature against the Keycloak realm JWKS, issuer and
expiry, optional audience. The A2A gateway asks for the `zuno-admin-api` audience, which every
token of the `unifai` client carries, so a token minted for another client is refused.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import jwt
from jwt import PyJWKClient

logger = logging.getLogger("a2a_gateway.auth")

KEYCLOAK_ISSUER = os.getenv("KEYCLOAK_ISSUER", "https://keycloak-zuno.apps.mycluster.example.com/realms/zuno")
KEYCLOAK_JWKS_URL = os.getenv("KEYCLOAK_JWKS_URL", f"{KEYCLOAK_ISSUER}/protocol/openid-connect/certs")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE") or None
JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "30"))

_jwks_client: Optional[PyJWKClient] = None


class AuthError(Exception):
    """The caller could not be authenticated. ``status`` is the HTTP status to answer."""

    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


@dataclass
class CallerIdentity:
    sub: str
    groups: List[str]
    raw_claims: dict
    token: str


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(KEYCLOAK_JWKS_URL, cache_keys=True, lifespan=300)
    return _jwks_client


def bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing or malformed Authorization header; expected 'Bearer <token>'.")
    return authorization.split(" ", 1)[1].strip()


def validate_token(authorization: Optional[str]) -> CallerIdentity:
    token = bearer_token(authorization)
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
        raise AuthError("Invalid or expired token.") from exc
    except Exception as exc:  # JWKS endpoint unreachable, malformed token, ...
        logger.error("Unable to validate JWT against %s: %s", KEYCLOAK_JWKS_URL, exc)
        raise AuthError("Identity provider unreachable; cannot validate caller identity.", 503) from exc
    sub = claims.get("sub")
    if not sub:
        raise AuthError("Token missing 'sub' claim.")
    groups = [str(g).lstrip("/") for g in (claims.get("groups") or [])]
    return CallerIdentity(sub=sub, groups=groups, raw_claims=claims, token=token)
