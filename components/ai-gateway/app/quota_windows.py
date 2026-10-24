"""Retry-After for a MaaS quota 429 (WP-157, inventory V7 and V12).

MaaS answers a quota denial with HTTP 429, `text/plain`, and no
`Retry-After` header (V12). Limitador's token windows are not
epoch-aligned: a counter's window starts at its first hit and lasts the
policy window (V7). So the gateway computes the delay itself, from the
windows of app/quota_windows.yaml (GENERATED from the release's
policies/quotas/quota-policy.yaml by
platform/okf/generate_quota_enforcement.py) and the first MaaS call it saw
for each counter key in the current window.

The keys are the ones the gateway TokenRateLimitPolicy counts on, through
the attested headers (app/maas_adapter.py): the caller's `sub`, the sorted
groups key, and the project id when there is one. Which ceiling fired is not
in MaaS's 429, so the delay is the longest remaining window among the keys
this replica saw: retrying earlier than that could be denied again.

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

    def retry_after(
        self, quota_class: str, sub: Optional[str], groups_key: Optional[str], project_id: Optional[str],
    ) -> Optional[int]:
        """Seconds until the longest running window of these keys ends; the
        class's full window when none has a recorded start; None when the
        class has no window at all."""
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
