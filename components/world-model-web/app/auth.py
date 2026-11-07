"""Identity of the caller (ADR-0604 D1, §8.1): the user's Keycloak token, validated here.

The oauth2-proxy front door authenticates the browser and forwards the user's
access token (X-Forwarded-Access-Token, or Authorization: Bearer). This module
validates it again (signature through the realm's JWKS, issuer, audience,
expiry) instead of trusting a header, then derives the groups from the token.
Identity, groups and persona come from validated claims only, never from a
request header; the one exception is the explicit dev mode of a local run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from app import metrics
from app.config import Settings

logger = logging.getLogger("world_model_web.auth")

LEEWAY_SECONDS = 30


@dataclass
class Caller:
    sub: str
    username: str
    groups: List[str]
    token: str = field(repr=False, default="")

    def in_any(self, wanted) -> bool:
        return any(group in self.groups for group in wanted)


def normalize_groups(claim) -> List[str]:
    """Keycloak group paths ("/ocp-ai-ops") to plain names; anything else is dropped."""
    if not isinstance(claim, list):
        return []
    return sorted({g.strip().lstrip("/") for g in claim if isinstance(g, str) and g.strip()})


class Authenticator:
    def __init__(self, settings: Settings, key_resolver: Optional[Callable[[str], object]] = None):
        self.settings = settings
        if key_resolver is not None:
            self._resolve = key_resolver
        else:
            client = PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=300)
            self._resolve = lambda token: client.get_signing_key_from_jwt(token).key

    def _token_from(self, request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer ") and auth[7:].strip():
            return auth[7:].strip()
        forwarded = request.headers.get("x-forwarded-access-token", "").strip()
        if forwarded:
            return forwarded
        raise _deny("missing_token", 401, "no access token")

    def authenticate(self, request) -> Caller:
        """The validated caller, or HTTPException (401 bad token, 403 not in an allowed group)."""
        if self.settings.auth_mode == "dev":
            return self._dev_caller(request)
        token = self._token_from(request)
        try:
            claims = jwt.decode(
                token,
                self._resolve(token),
                algorithms=["RS256", "ES256", "PS256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            logger.info("token refused: %s", type(exc).__name__)
            raise _deny("invalid_token", 401, "invalid access token") from exc
        except Exception as exc:  # noqa: BLE001 - JWKS unreachable: fail closed
            logger.warning("token check failed: %s", exc)
            raise _deny("jwks_unavailable", 503, "cannot verify the access token now") from exc
        caller = Caller(
            sub=str(claims["sub"]),
            username=str(claims.get("preferred_username") or claims["sub"]),
            groups=normalize_groups(claims.get("groups")),
            token=token,
        )
        if not caller.in_any(self.settings.allowed_groups):
            raise _deny("not_in_group", 403, "your account is not allowed to open the world-model demo")
        return caller

    def _dev_caller(self, request) -> Caller:
        # Local runs only. The chart never sets WORLD_MODEL_AUTH=dev, and a test pins that the default is oidc.
        user = request.headers.get("x-dev-user", "dev-presenter")
        groups = [g for g in request.headers.get("x-dev-groups", "zuno-world-model-users").split(",") if g]
        caller = Caller(sub=f"dev:{user}", username=user, groups=groups)
        if not caller.in_any(self.settings.allowed_groups):
            raise _deny("not_in_group", 403, "your account is not allowed to open the world-model demo")
        return caller


def _deny(reason: str, status: int, detail: str) -> HTTPException:
    metrics.AUTH_FAILURES.labels(reason=reason).inc()
    return HTTPException(status_code=status, detail=detail)
