"""Per-provider circuit breaker (ADR-0591 decision 3).

The safety net behind model readiness: a provider that just failed by timeout,
connection error or 5xx is skipped for `CIRCUIT_OPEN_SECONDS`, then one call is
let through (half-open); its success closes the breaker, its failure opens it
again. A trial that never reports back (a cancelled request) expires after the
same window, so a provider is never skipped for good. A 429 (MaaS quota,
ADR-0570), any other 4xx and a guardrails refusal are answers, not outages:
they never open it, and they close it - the provider is reachable.

In memory, per replica: no shared state to keep consistent, and a replica that
has not seen the failure simply pays it once.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Dict, Optional


def _open_seconds() -> float:
    return float(os.getenv("CIRCUIT_OPEN_SECONDS", "60"))


def _enabled() -> bool:
    return os.getenv("CIRCUIT_BREAKER_ENABLED", "false").strip().lower() == "true"


def is_outage(exc: BaseException) -> bool:
    """Timeout, connection error or 5xx - the failures a breaker is for."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status >= 500
    name = type(exc).__name__
    if "Timeout" in name or "Connect" in name:
        return True
    try:
        import httpx

        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)):
            return True
    except ImportError:  # pragma: no cover
        pass
    return isinstance(exc, (TimeoutError, ConnectionError))


class CircuitBreaker:
    def __init__(self) -> None:
        self._opened_at: Dict[str, float] = {}
        self._trial_at: Dict[str, float] = {}
        self._lock = threading.Lock()

    def is_open(self, provider: str, now: Optional[float] = None) -> bool:
        """True while the provider must be skipped. Past the open window, the
        first caller gets False (the half-open trial) and later callers keep
        getting True until that trial reports back."""
        if not _enabled():
            return False
        now = time.monotonic() if now is None else now
        with self._lock:
            opened = self._opened_at.get(provider)
            if opened is None:
                return False
            if now - opened < _open_seconds():
                return True
            trial = self._trial_at.get(provider)
            if trial is not None and now - trial < _open_seconds():
                return True
            self._trial_at[provider] = now
            return False

    def peek_open(self, provider: str, now: Optional[float] = None) -> bool:
        """Like is_open, without claiming the half-open trial."""
        if not _enabled():
            return False
        now = time.monotonic() if now is None else now
        with self._lock:
            opened = self._opened_at.get(provider)
            if opened is None or now - opened >= _open_seconds():
                trial = self._trial_at.get(provider)
                return opened is not None and trial is not None and now - trial < _open_seconds()
            return True

    def record_success(self, provider: str) -> None:
        with self._lock:
            self._opened_at.pop(provider, None)
            self._trial_at.pop(provider, None)

    def record_failure(self, provider: str, exc: BaseException, now: Optional[float] = None) -> bool:
        """Open the breaker if `exc` is an outage; returns whether it did."""
        if not is_outage(exc):
            self.record_success(provider)
            return False
        with self._lock:
            self._opened_at[provider] = time.monotonic() if now is None else now
            self._trial_at.pop(provider, None)
        return True

    def reset(self) -> None:
        with self._lock:
            self._opened_at.clear()
            self._trial_at.clear()


breaker = CircuitBreaker()
