"""ADR-0602 clause 9 (WP-225 lot A): an optional per-key token ceiling on the metered paths.

`/v1/messages` and `/v1/responses` (app/metered_paths.py) stay open: they are
metered, not blocked. This module adds the ceiling a deployment MAY set, per
key or per tenant. Without configuration there is no ceiling, which is today's
behaviour (the Claude Code developer key keeps working).

Configuration: KEY_CEILINGS, a JSON object rendered from the chart value
`meteredPaths.keyCeilings`, read once at start:

    {
      "window": "1h",          # fixed window, as in app/quota.py (s, m, h, d)
      "default": 0,            # tokens per window for a key with no entry; 0 = no ceiling
      "keys":    {"alice": 2000000},       # persona (CallerIdentity.persona) -> tokens
      "tenants": {"ocp-ai-dev": 20000000}, # Keycloak group -> tokens, shared by its members
      "exempt":  ["claude-code-dev"]       # persona or Keycloak client (azp): never capped
    }

A key is the caller's persona: the person (or the persona an OpenClaw client
acts for, ADR-0593), the same subject the token-budget ledger counts. A key
entry overrides `default`. A tenant ceiling is one counter for the whole group
and applies on top of the key's. `exempt` wins over everything, so an explicit
exemption keeps a named key or client uncapped whatever the default.

Counters are fixed windows in-process; with QUOTA_LEDGER_STORE=redis they are
also written to the platform Redis through app/quota.py's store (best effort).
A malformed KEY_CEILINGS is logged and means no ceiling: the paths are open by
decision, so a configuration fault must not close them.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from app import quota

logger = logging.getLogger("ai_gateway.key_ceilings")

_CLASS = "metered-paths"


@dataclass
class CeilingDenial:
    dimension: str  # "key" or "tenant"
    subject: str
    ceiling: int
    window: str
    retry_after: int

    def message(self) -> str:
        return (f"token ceiling reached for this {self.dimension}: {self.ceiling} tokens per "
                f"{self.window} on the metered paths; retry in {self.retry_after} s")


class KeyCeilings:
    def __init__(self, raw: Optional[str] = None, store=None):
        raw = os.getenv("KEY_CEILINGS", "") if raw is None else raw
        self.window = "1h"
        self.window_secs = 3600
        self.default = 0
        self.keys: Dict[str, int] = {}
        self.tenants: Dict[str, int] = {}
        self.exempt: set = set()
        self._counters: Dict[Tuple[str, str, int], int] = {}
        self._store = store if store is not None else quota._store_from_env()
        self._parse(raw)

    def _parse(self, raw: str) -> None:
        if not raw.strip():
            return
        try:
            doc = json.loads(raw)
            if not isinstance(doc, dict):
                raise ValueError("not a JSON object")
            window = str(doc.get("window") or "1h")
            window_secs = quota._window_seconds(window)
            default = int(doc.get("default") or 0)
            keys = {str(k): int(v) for k, v in (doc.get("keys") or {}).items()}
            tenants = {str(k).lstrip("/"): int(v) for k, v in (doc.get("tenants") or {}).items()}
            exempt = {str(e) for e in (doc.get("exempt") or [])}
        except (ValueError, TypeError, AttributeError) as exc:
            logger.error("ignoring malformed KEY_CEILINGS (%s): no ceiling applies", exc)
            return
        self.window, self.window_secs, self.default = window, window_secs, default
        self.keys, self.tenants, self.exempt = keys, tenants, exempt
        if self.configured:
            logger.info("metered-path ceilings: window=%s default=%s keys=%d tenants=%d exempt=%d",
                        window, default or "none", len(keys), len(tenants), len(exempt))

    @property
    def configured(self) -> bool:
        return bool(self.default or self.keys or self.tenants)

    def is_exempt(self, persona: str, client: str) -> bool:
        return persona in self.exempt or (bool(client) and client in self.exempt)

    def _limits(self, persona: str, groups: Iterable[str]) -> List[Tuple[str, str, int]]:
        limits: List[Tuple[str, str, int]] = []
        key_limit = self.keys.get(persona, self.default)
        if key_limit > 0:
            limits.append(("key", persona, key_limit))
        for group in sorted(set(groups or [])):
            if self.tenants.get(group, 0) > 0:
                limits.append(("tenant", group, self.tenants[group]))
        return limits

    def _consumed(self, dimension: str, subject: str, bucket: int) -> int:
        local = self._counters.get((dimension, subject, bucket), 0)
        if self._store is None:
            return local
        return max(local, self._store.get((_CLASS, dimension, subject, bucket)))

    def check(self, persona: str, client: str, groups: Iterable[str],
              now: Optional[float] = None) -> Optional[CeilingDenial]:
        """A denial when a ceiling of this caller is already used up, else None."""
        if not self.configured or self.is_exempt(persona, client):
            return None
        now = now or time.time()
        bucket = int(now // self.window_secs)
        for dimension, subject, limit in self._limits(persona, groups):
            if self._consumed(dimension, subject, bucket) >= limit:
                retry_after = max(1, int(self.window_secs - (now % self.window_secs)))
                return CeilingDenial(dimension, subject, limit, self.window, retry_after)
        return None

    def consume(self, persona: str, client: str, groups: Iterable[str], tokens: int,
                now: Optional[float] = None) -> None:
        if tokens <= 0 or not self.configured or self.is_exempt(persona, client):
            return
        now = now or time.time()
        bucket = int(now // self.window_secs)
        for dimension, subject, _limit in self._limits(persona, groups):
            key = (dimension, subject, bucket)
            self._counters[key] = self._counters.get(key, 0) + tokens
            if self._store is not None:
                self._store.add((_CLASS, dimension, subject, bucket), tokens, self.window_secs)
        if len(self._counters) > 10000:
            self._counters = {k: v for k, v in self._counters.items() if k[2] >= bucket - 1}


ceilings = KeyCeilings()
