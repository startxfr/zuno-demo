"""JWT validation for the AI Inference Gateway (ADR-0009, ADR-0012, ADR-0013).

Structurally identical to components/mcp-gateway/app/auth.py and
components/agent-runtime/app/auth.py — three independently deployable
services, so the ~60 lines are duplicated rather than factored into a
shared package the repo doesn't otherwise have (see agent-runtime's copy
for the fuller rationale). This gateway only needs authenticated-caller
verification (`sub`) — unlike mcp-gateway, it has no per-caller
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
    "KEYCLOAK_ISSUER", "https://keycloak-zuno.apps.example.com/realms/zuno"
)
KEYCLOAK_JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL", f"{KEYCLOAK_ISSUER}/protocol/openid-connect/certs"
)
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE") or None
JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "30"))

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

    groups = claims.get("groups", []) or []
    return CallerIdentity(sub=sub, groups=[g.lstrip("/") for g in groups], raw_claims=claims, token=token)
