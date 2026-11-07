"""ADR-0602 clause 9 (WP-225 lot A): an optional per-key token ceiling on the metered paths.

`/v1/messages` and `/v1/responses` (app/metered_paths.py) stay open: they are
metered, not blocked. This module adds the ceiling a deployment MAY set, per
key or per tenant. Without configuration there is no ceiling, which is today's
behaviour (the Claude Code developer key keeps working).

Configuration: KEY_CEILINGS, a JSON object rendered from the chart value
`meteredPaths.keyCeilings`, read once at start:

    {
      "window": "1h",                       # fixed window, as in app/quota.py (s, m, h, d)
      "default": 0,                         # tokens per window for a key with no entry; 0 = no ceiling
      "keys":    {"alice": 2000000},        # persona (CallerIdentity.persona) -> tokens
      "tenants": {"ocp-ai-dev": 20000000},  # Keycloak group -> tokens, shared by its members
      "exemptPersonas": ["claude-code-dev"],  # never capped
      "exemptClients":  ["zuno-dev"],         # Keycloak client ids (azp), never capped
      "maxConcurrentStreams": 0             # per key; 0 = no cap
    }

`exempt` (one list matched against both the persona and the client id) is still
read, for values written before the split.

A key is the caller's persona: the person (or the persona an OpenClaw client
acts for, ADR-0593), the same subject the token-budget ledger counts. A key
entry overrides `default`. A tenant ceiling is one counter for the whole group
and applies on top of the key's. An exemption wins over everything.

Parallel calls cannot run past a ceiling without bound: `admit` reserves an
estimate (the prompt estimate plus the requested output cap) against every
ceiling of the caller, a later call sees consumed + reserved, and `settle`
replaces the reservation with the real usage. The overrun is bounded by one
call. Reservations and the stream count are per replica; consumed tokens follow
QUOTA_LEDGER_STORE (with `redis`, shared through app/quota.py's store, best
effort).

A malformed KEY_CEILINGS is logged and means no ceiling: the paths are open by
decision, so a configuration fault must not close them.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from app import quota

logger = logging.getLogger("ai_gateway.key_ceilings")

_CLASS = "metered-paths"


@dataclass
class CeilingDenial:
    dimension: str  # "key", "tenant" or "streams"
    subject: str
    ceiling: int
    window: str
    retry_after: int

    def message(self) -> str:
        if self.dimension == "streams":
            return (f"too many concurrent streams for this key: at most {self.ceiling} on the metered "
                    f"paths; retry in {self.retry_after} s")
        return (f"token ceiling reached for this {self.dimension}: {self.ceiling} tokens per "
                f"{self.window} on the metered paths; retry in {self.retry_after} s")


@dataclass
class Reservation:
    """What `admit` held for one call; hand it back to `settle` (idempotent)."""
    persona: str
    limits: List[Tuple[str, str, int]] = field(default_factory=list)
    bucket: int = 0
    tokens: int = 0
    stream: bool = False
    settled: bool = False


class KeyCeilings:
    def __init__(self, raw: Optional[str] = None, store=None):
        raw = os.getenv("KEY_CEILINGS", "") if raw is None else raw
        self.window = "1h"
        self.window_secs = 3600
        self.default = 0
        self.keys: Dict[str, int] = {}
        self.tenants: Dict[str, int] = {}
        self.exempt_personas: set = set()
        self.exempt_clients: set = set()
        self.max_streams = 0
        self._counters: Dict[Tuple[str, str, int], int] = {}
        self._reserved: Dict[Tuple[str, str, int], int] = {}
        self._streams: Dict[str, int] = {}
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
            legacy = {str(e) for e in (doc.get("exempt") or [])}
            personas = {str(e) for e in (doc.get("exemptPersonas") or [])} | legacy
            clients = {str(e) for e in (doc.get("exemptClients") or [])} | legacy
            max_streams = int(doc.get("maxConcurrentStreams") or 0)
        except (ValueError, TypeError, AttributeError) as exc:
            logger.error("ignoring malformed KEY_CEILINGS (%s): no ceiling applies", exc)
            return
        self.window, self.window_secs, self.default = window, window_secs, default
        self.keys, self.tenants = keys, tenants
        self.exempt_personas, self.exempt_clients, self.max_streams = personas, clients, max_streams
        if self.configured:
            logger.info("metered-path ceilings: window=%s default=%s keys=%d tenants=%d streams=%s "
                        "exempt personas=%d clients=%d", window, default or "none", len(keys), len(tenants),
                        max_streams or "no cap", len(personas), len(clients))

    @property
    def configured(self) -> bool:
        return bool(self.default or self.keys or self.tenants or self.max_streams)

    def is_exempt(self, persona: str, client: str) -> bool:
        return persona in self.exempt_personas or (bool(client) and client in self.exempt_clients)

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

    def _retry_after(self, now: float) -> int:
        return max(1, int(self.window_secs - (now % self.window_secs)))

    def admit(self, persona: str, client: str, groups: Iterable[str], estimate: int = 0,
              stream: bool = False, now: Optional[float] = None) -> Tuple[Optional[CeilingDenial], Reservation]:
        """Refuse a caller whose ceiling (consumed + reserved by calls in flight) is
        used up, or who already holds maxConcurrentStreams streams; else reserve
        `estimate` tokens. There is no await between the check and the
        reservation, so two concurrent calls cannot both pass on the same room."""
        now = now or time.time()
        bucket = int(now // self.window_secs)
        done = Reservation(persona=persona, bucket=bucket, settled=True)
        if not self.configured or self.is_exempt(persona, client):
            return None, done
        if stream and self.max_streams and self._streams.get(persona, 0) >= self.max_streams:
            return CeilingDenial("streams", persona, self.max_streams, self.window, 5), done
        limits = self._limits(persona, groups)
        for dimension, subject, limit in limits:
            used = self._consumed(dimension, subject, bucket) + self._reserved.get((dimension, subject, bucket), 0)
            if used >= limit:
                return CeilingDenial(dimension, subject, limit, self.window, self._retry_after(now)), done
        tokens = max(0, int(estimate))
        for dimension, subject, _limit in limits:
            key = (dimension, subject, bucket)
            self._reserved[key] = self._reserved.get(key, 0) + tokens
        if stream:
            self._streams[persona] = self._streams.get(persona, 0) + 1
        return None, Reservation(persona=persona, limits=limits, bucket=bucket, tokens=tokens, stream=stream)

    def settle(self, reservation: Reservation, tokens: int) -> None:
        """Release the reservation and count the real usage. Idempotent."""
        if reservation.settled:
            return
        reservation.settled = True
        for dimension, subject, _limit in reservation.limits:
            key = (dimension, subject, reservation.bucket)
            left = self._reserved.get(key, 0) - reservation.tokens
            if left > 0:
                self._reserved[key] = left
            else:
                self._reserved.pop(key, None)
            if tokens > 0:
                self._counters[key] = self._counters.get(key, 0) + tokens
                if self._store is not None:
                    self._store.add((_CLASS, dimension, subject, reservation.bucket), tokens, self.window_secs)
        if reservation.stream:
            left = self._streams.get(reservation.persona, 0) - 1
            if left > 0:
                self._streams[reservation.persona] = left
            else:
                self._streams.pop(reservation.persona, None)
        if len(self._counters) > 10000:
            self._counters = {k: v for k, v in self._counters.items() if k[2] >= reservation.bucket - 1}

    def check(self, persona: str, client: str, groups: Iterable[str],
              now: Optional[float] = None) -> Optional[CeilingDenial]:
        """Check without reserving."""
        denial, reservation = self.admit(persona, client, groups, 0, now=now)
        self.settle(reservation, 0)
        return denial

    def consume(self, persona: str, client: str, groups: Iterable[str], tokens: int,
                now: Optional[float] = None) -> None:
        """Count usage without a reservation (also past the ceiling)."""
        if tokens <= 0 or not self.configured or self.is_exempt(persona, client):
            return
        now = now or time.time()
        self.settle(Reservation(persona=persona, limits=self._limits(persona, groups),
                                bucket=int(now // self.window_secs)), tokens)


ceilings = KeyCeilings()
