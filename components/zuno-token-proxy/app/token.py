"""Client-credentials token source (ADR-0601 decision 2).

The token is fetched from the Keycloak Route, cached, and refreshed once `refresh_ratio` of its
lifetime has passed. A failed refresh keeps serving the current token while it is still valid;
with no valid token left, `get()` raises TokenUnavailable and the proxy answers 503.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

import httpx

from app import metrics
from app.config import Settings

logger = logging.getLogger("zuno_token_proxy.token")

# Never trust a lifetime so short that every request would refresh, nor one longer than an hour.
_MIN_LIFETIME_S = 10
_MAX_LIFETIME_S = 3600
# A token is not handed out in its last seconds: the upstream would see it expire in flight.
_EXPIRY_MARGIN_S = 5


class TokenUnavailable(Exception):
    """No valid token can be served."""


class TokenSource:
    def __init__(self, settings: Settings, client: httpx.AsyncClient, clock: Callable[[], float] = time.monotonic):
        self._settings = settings
        self._client = client
        self._clock = clock
        self._lock = asyncio.Lock()
        self._token: Optional[str] = None
        self._expires_at = 0.0
        self._refresh_at = 0.0

    def _valid(self, now: float) -> bool:
        return self._token is not None and now < self._expires_at - _EXPIRY_MARGIN_S

    @property
    def ready(self) -> bool:
        return self._valid(self._clock())

    async def get(self) -> str:
        now = self._clock()
        if self._valid(now) and now < self._refresh_at:
            return self._token  # type: ignore[return-value]
        async with self._lock:
            now = self._clock()
            if self._valid(now) and now < self._refresh_at:
                return self._token  # type: ignore[return-value]
            try:
                await self._fetch(now)
                metrics.inc("zuno_token_proxy_refresh_total", result="success")
            except Exception as exc:  # noqa: BLE001 - every failure has the same outcome
                metrics.inc("zuno_token_proxy_refresh_total", result="error")
                logger.warning("token refresh failed: %s", exc)
                if not self._valid(self._clock()):
                    raise TokenUnavailable("no valid token from Keycloak") from exc
            return self._token  # type: ignore[return-value]

    async def _fetch(self, now: float) -> None:
        data = {"grant_type": "client_credentials"}
        if self._settings.scope:
            data["scope"] = self._settings.scope
        response = await self._client.post(
            self._settings.token_url,
            data=data,
            auth=(self._settings.client_id, self._settings.client_secret),
            timeout=self._settings.token_timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("token response has no access_token")
        lifetime = body.get("expires_in", 60)
        if not isinstance(lifetime, (int, float)):
            raise ValueError("token response has a non-numeric expires_in")
        lifetime = min(max(float(lifetime), _MIN_LIFETIME_S), _MAX_LIFETIME_S)
        self._token = token
        self._expires_at = now + lifetime
        self._refresh_at = now + lifetime * self._settings.refresh_ratio
