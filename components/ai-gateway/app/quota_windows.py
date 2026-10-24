"""Retry-After for a MaaS quota 429 (WP-157, inventory V7 and V12).

MaaS answers a quota denial with HTTP 429, `text/plain`, and no
`Retry-After` header (V12). Limitador's token windows are not
epoch-aligned: a counter's window starts at its first hit and lasts the
policy window (V7). So the gateway computes the delay itself, from the
windows of app/quota_windows.yaml (GENERATED from the release's
policies/quotas/quota-policy.yaml by
platform/okf/generate_quota_enforcement.py) and the first MaaS call it saw
for each counter key in the current window.

Two kinds of limit can answer that 429, and MaaS does not say which: the
model's own MaaSSubscription budget for the ai-gateway ServiceAccount
(window `maas_quota_window` of the provider-routing.yaml entry, 1 h today,
counted per model from the gateway's first call), and the gateway-level
TokenRateLimitPolicy ceilings (the policy windows, 24 h for `standard`,
counted per caller key: `sub`, groups key, project id). The subscription
budget is by far the smaller one and the one seen tripping live (WP-157
drill of 2026-10-24: a 24 h delay was sent for a 1 h limit), so when the
provider has a subscription window the delay is what remains of it. Only a
provider without one falls back to the longest remaining policy window of
the caller's keys. A client retrying after a subscription delay while a
24 h ceiling is the one exhausted gets a new 429 with a new delay: an
under-estimate costs one more refusal, an over-estimate a day's wait.

Bounded by what one replica knows. A key first seen by another replica, or
before a restart, has no recorded start; when no key of the request has
one, the delay is the class's full window, the safe upper bound. Used only
on the MAAS_QUOTA_429_PASSTHROUGH path.
"""
from __future__ import annotations

import logging
import pathlib
import re
import threading
import time
from typing import Callable, Dict, Iterable, Optional, Tuple

import yaml

logger = logging.getLogger("zuno.ai-gateway.quota_windows")

QUOTA_WINDOWS_PATH = pathlib.Path(__file__).resolve().parent / "quota_windows.yaml"

_WINDOW_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def window_seconds(window: str) -> int:
    match = _WINDOW_RE.match(str(window))
    if not match:
        raise ValueError(f"unparseable window {window!r}")
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


def _load(path: pathlib.Path) -> Dict[str, Dict[str, int]]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {
            cls: {dim: window_seconds(w) for dim, w in (dims or {}).items()}
            for cls, dims in (doc.get("classes") or {}).items()
        }
    except Exception as exc:  # noqa: BLE001 - no windows = no computed delay
        logger.error("quota windows unreadable (%s) - a MaaS 429 carries no Retry-After", exc)
        return {}


class WindowClock:
    def __init__(
        self,
        windows: Optional[Dict[str, Dict[str, int]]] = None,
        path: pathlib.Path = QUOTA_WINDOWS_PATH,
        clock: Callable[[], float] = time.time,
    ):
        self.windows = windows if windows is not None else _load(path)
        self._clock = clock
        self._starts: Dict[Tuple[str, str, str], float] = {}
        self._model_starts: Dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _keys(sub: Optional[str], groups_key: Optional[str], project_id: Optional[str]) -> Iterable[Tuple[str, str]]:
        for dim, key in (("user", sub), ("group", groups_key), ("project", project_id)):
            if key:
                yield dim, key

    def hit(self, quota_class: str, sub: Optional[str], groups_key: Optional[str], project_id: Optional[str]) -> None:
        """A call through MaaS under these keys: starts each key's window
        unless one is already running."""
        dims = self.windows.get(quota_class) or {}
        now = self._clock()
        with self._lock:
            for dim, key in self._keys(sub, groups_key, project_id):
                window = dims.get(dim)
                if not window:
                    continue
                slot = (quota_class, dim, key)
                start = self._starts.get(slot)
                if start is None or now - start >= window:
                    self._starts[slot] = now

    def hit_model(self, provider: str, window: Optional[str]) -> None:
        """A call through MaaS to this provider's model: starts its
        subscription window unless one is already running."""
        if not window:
            return
        seconds = window_seconds(window)
        now = self._clock()
        with self._lock:
            start = self._model_starts.get(provider)
            if start is None or now - start >= seconds:
                self._model_starts[provider] = now

    def retry_after(
        self, quota_class: str, sub: Optional[str], groups_key: Optional[str], project_id: Optional[str],
        provider: Optional[str] = None, model_window: Optional[str] = None,
    ) -> Optional[int]:
        """With a subscription window for the provider: seconds until it
        ends (the whole window when this replica saw no start). Otherwise:
        seconds until the longest running policy window of these keys ends;
        the class's full window when none has a recorded start; None when
        the class has no window at all."""
        if provider and model_window:
            seconds = window_seconds(model_window)
            now = self._clock()
            with self._lock:
                start = self._model_starts.get(provider)
            if start is None or now - start >= seconds:
                return seconds
            return max(1, int(start + seconds - now + 0.999))
        dims = self.windows.get(quota_class) or {}
        if not dims:
            return None
        now = self._clock()
        remaining = []
        with self._lock:
            for dim, key in self._keys(sub, groups_key, project_id):
                window = dims.get(dim)
                start = self._starts.get((quota_class, dim, key))
                if window and start is not None and now - start < window:
                    remaining.append(start + window - now)
        if not remaining:
            return max(dims.values())
        return max(1, int(max(remaining) + 0.999))


clock = WindowClock()
