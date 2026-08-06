"""JWT validation for the MCP Gateway (ADR-0010, ADR-0012, ADR-0013).

Every request into the gateway carries a Keycloak-issued Bearer JWT. We
validate its signature against the realm's JWKS endpoint and extract the
`groups` claim, which ADR-0011's policy intersection uses downstream in
policy.py. We deliberately do not accept unsigned/unverified tokens under
any configuration -- there is no "dev mode" bypass here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import jwt
from fastapi import Header, HTTPException, status
from jwt import PyJWKClient

logger = logging.getLogger("mcp_gateway.auth")

# The Keycloak route hostname is owned by the identity track (Keycloak
# Operator + realm import, see gitops/charts/keycloak). Override these two
# env vars per environment; the defaults only work for the example cluster
# domain used elsewhere in this repo (ansible/inventories/example).
KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER", "https://keycloak-zuno.apps.mycluster.example.com/realms/zuno"
)
KEYCLOAK_JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL", f"{KEYCLOAK_ISSUER}/protocol/openid-connect/certs"
)
# Most Keycloak client configs are audience-less by default for internal
# service calls; set JWT_AUDIENCE to enforce `aud` checking once the
# identity track assigns a client id to this gateway.
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


def validate_token(
    authorization: Optional[str] = Header(default=None),
) -> CallerIdentity:
    """FastAPI dependency: validates signature + issuer + expiry against
    Keycloak's JWKS, then extracts `sub` and `groups` for ADR-0011.
    """
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
    except Exception as exc:  # JWKS endpoint unreachable, malformed token, etc.
        logger.error(
            "Unable to validate JWT against Keycloak JWKS at %s: %s",
            KEYCLOAK_JWKS_URL,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider unreachable; cannot validate caller identity.",
        ) from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim.")

    groups = claims.get("groups", []) or []
    normalized_groups = [g.lstrip("/") for g in groups]

    return CallerIdentity(sub=sub, groups=normalized_groups, raw_claims=claims, token=token)
