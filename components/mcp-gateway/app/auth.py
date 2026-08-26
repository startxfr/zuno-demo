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


# --- ADR-0524: per-user identity for the /mcp front-door ---------------------
#
# OpenShift Lightspeed can forward the CONSOLE USER's own token to an MCP server
# (OLSConfig `headers[].valueFrom.type: client`). That token is an opaque
# OpenShift access token (`sha256~...`), not a JWT, so the JWKS path above can
# never validate it - no amount of Keycloak configuration changes that, because
# the token was never issued by Keycloak.
#
# The Kubernetes TokenReview API can: it is the same mechanism MaaS's own
# AuthPolicy uses (`kubernetesTokenReview`, verified live 2026-08-26). It returns
# the authenticated username and the user's GROUPS, which on this cluster carry
# the same names the tool policy already authorizes on - `consultant` and `sales`
# are both OpenShift groups AND tool-policy allowed_groups. So per-user
# authorization needs no synthetic mapping table: the groups pass straight
# through and a user with no relevant group is denied, exactly as a Keycloak
# caller with no relevant group would be.
#
# This is ADDITIVE. The Keycloak JWT path is unchanged and remains the primary
# one; this is tried only when the presented token cannot be a JWT.

KUBERNETES_HOST = os.getenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
KUBERNETES_PORT = os.getenv("KUBERNETES_SERVICE_PORT", "443")
SA_TOKEN_PATH = os.getenv(
    "SA_TOKEN_PATH", "/var/run/secrets/kubernetes.io/serviceaccount/token"
)
SA_CA_PATH = os.getenv(
    "SA_CA_PATH", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
)
# Groups every authenticated principal carries; never evidence of entitlement,
# so they are stripped before the policy sees them. Leaving them in would let
# any authenticated cluster user match a policy entry that happened to list one.
_UNINFORMATIVE_GROUPS = {
    "system:authenticated",
    "system:authenticated:oauth",
    "system:masters",
}


def _looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots. An OpenShift access
    token is `sha256~<base64>` and a legacy one is opaque - neither has two dots.
    Cheap and deterministic, so we never send a Keycloak token to TokenReview or
    vice versa."""
    return token.count(".") == 2 and not token.startswith("sha256~")


def _review_kubernetes_token(token: str) -> Optional[CallerIdentity]:
    """Resolve an OpenShift token through TokenReview. Returns None when the
    token is not valid for this cluster; raises only on infrastructure failure,
    so an unauthenticated caller and a broken API server are distinguishable."""
    import json as _json
    import urllib.request
    import ssl

    try:
        with open(SA_TOKEN_PATH, "r", encoding="utf-8") as fh:
            sa_token = fh.read().strip()
    except OSError as exc:
        logger.error("cannot read this pod's ServiceAccount token for TokenReview: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="token review unavailable: gateway has no ServiceAccount token",
        ) from exc

    body = _json.dumps(
        {
            "apiVersion": "authentication.k8s.io/v1",
            "kind": "TokenReview",
            "spec": {"token": token},
        }
    ).encode()
    url = f"https://{KUBERNETES_HOST}:{KUBERNETES_PORT}/apis/authentication.k8s.io/v1/tokenreviews"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {sa_token}", "Content-Type": "application/json"},
    )
    try:
        ctx = ssl.create_default_context(cafile=SA_CA_PATH)
    except OSError:
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            payload = _json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001 - network/API failure, not a denial
        logger.error("TokenReview call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="token review unavailable; cannot validate caller identity",
        ) from exc

    review_status = payload.get("status") or {}
    if not review_status.get("authenticated"):
        return None

    user = review_status.get("user") or {}
    username = user.get("username") or ""
    if not username:
        return None
    groups = [g for g in (user.get("groups") or []) if g not in _UNINFORMATIVE_GROUPS]
    return CallerIdentity(sub=username, groups=groups, raw_claims={"tokenReview": user}, token=token)


def validate_token_or_kubernetes(
    authorization: Optional[str] = Header(default=None),
) -> CallerIdentity:
    """FastAPI dependency for the /mcp front-door: accepts EITHER a Keycloak JWT
    (service-identity mode) or an OpenShift user token (per-user mode).

    Deliberately a separate dependency rather than a change to validate_token:
    the REST contract keeps accepting Keycloak tokens and nothing else, so this
    can never widen what `/v1/tools/{name}/invoke` admits.
    """
    token = _extract_bearer_token(authorization)
    if _looks_like_jwt(token):
        return validate_token(authorization)

    identity = _review_kubernetes_token(token)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token is neither a valid Keycloak JWT nor a valid OpenShift token",
        )
    logger.info(
        "per-user identity resolved via TokenReview: user=%s groups=%s", identity.sub, identity.groups
    )
    return identity
