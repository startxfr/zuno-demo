"""ADR-0511 (WP-54 Part B) token-budget enforcement.

AI Gateway is the token-budget half of quota enforcement - only the
inference layer can meter tokens (request-per-window rates are Kuadrant/
Limitador's job, generated into the connectivity-link chart). Budgets,
precedence orders and fail modes come exclusively from
app/quota_budgets.yaml - a GENERATED slice of
policies/quotas/quota-policy.yaml (regenerate with
platform/okf/generate_quota_enforcement.py); this module never defines
an amount.

Semantics (ADR-0511 clause 2):
  - the GROUP budget is the outermost ceiling - always enforced;
  - with a verified project binding (the x-zuno-project-id header, only
    ever set platform-side from an ADR-0512 verification), consumption
    attributes to the PROJECT budget first, falling back to the USER
    budget once the project's is exhausted;
  - without a binding, consumption attributes to the USER budget;
  - denial is explicit (class, dimension, budget, window) - never
    silent degradation - and never bypasses or relaxes the ADR-0011/
    ADR-0036 authorization intersection, which runs regardless.

Counters are fixed windows held in-process. With QUOTA_LEDGER_STORE=redis
(WP-177) every increment is also written to the platform Redis (the one the
semantic cache uses) and reads take the larger of the local and the Redis
value, so a gateway restart or a second replica no longer resets the
budgets. Redis is best effort: a fault is logged and the local counter
alone applies, it never fails a request. The request-rate dimension stays
with Limitador.

Fail modes: if the budget config is missing or malformed, a class whose
fail_mode cannot be read is treated as `closed` (denied) - the ADR-0511
default; `standard`'s explicit `open` in the policy file is what keeps
plain chat available through a config fault.
"""
from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger("zuno.ai-gateway.quota")

BUDGETS_PATH = pathlib.Path(__file__).resolve().parent / "quota_budgets.yaml"
_WINDOW_RE = re.compile(r"^([0-9]+)(s|m|h|d)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _window_seconds(window: str) -> int:
    match = _WINDOW_RE.match(str(window))
    if not match:
        raise ValueError(f"unparseable window {window!r}")
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


class RedisCounterStore:
    """Best-effort shared counters (WP-177): INCRBY with an expiry, GET."""

    def __init__(self, client=None, prefix: str = "zuno:quota"):
        self._client = client
        self._prefix = prefix
        self._unavailable_logged = False
        self._down_until = 0.0  # after a fault, skip Redis briefly so a dead store adds no latency

    def _redis(self):
        if self._client is None:
            addr = os.getenv("REDIS_ADDR", "")
            if not addr:
                raise RuntimeError("REDIS_ADDR is not configured")
            import redis  # imported lazily: the memory store needs no Redis package
            from redis.backoff import NoBackoff
            from redis.retry import Retry

            host, _, port = addr.partition(":")
            # redis-py retries a failed connection 3 times with a growing wait by default; on the request
            # path that turned one dead Redis into a multi-second stall (drill, 2026-10-25). No retries.
            self._client = redis.Redis(
                host=host, port=int(port or 6379), password=os.getenv("REDIS_PASSWORD") or None,
                socket_timeout=0.1, socket_connect_timeout=0.1, decode_responses=True,
                retry=Retry(NoBackoff(), 0),
            )
        return self._client

    def _key(self, counter_key: Tuple[str, str, str, int]) -> str:
        quota_class, dimension, key, bucket = counter_key
        if len(key) > 200:
            key = "sha1:" + hashlib.sha1(key.encode("utf-8")).hexdigest()
        return f"{self._prefix}:{quota_class}:{dimension}:{key}:{bucket}"

    def _fault(self, action: str, exc: Exception) -> None:
        self._down_until = time.monotonic() + 5.0
        if not self._unavailable_logged:
            logger.warning("quota ledger redis %s failed (%s) - local counters only until it answers", action, exc)
            self._unavailable_logged = True

    def get(self, counter_key: Tuple[str, str, str, int]) -> int:
        if time.monotonic() < self._down_until:
            return 0
        try:
            raw = self._redis().get(self._key(counter_key))
            self._unavailable_logged = False
            return int(raw) if raw is not None else 0
        except Exception as exc:  # noqa: BLE001 - never fail a request on the shared store
            self._fault("read", exc)
            return 0

    def add(self, counter_key: Tuple[str, str, str, int], tokens: int, window_secs: int) -> None:
        if time.monotonic() < self._down_until:
            return
        try:
            client = self._redis()
            key = self._key(counter_key)
            client.incrby(key, tokens)
            client.expire(key, window_secs * 2)
            self._unavailable_logged = False
        except Exception as exc:  # noqa: BLE001
            self._fault("write", exc)


def _store_from_env() -> Optional[RedisCounterStore]:
    if os.getenv("QUOTA_LEDGER_STORE", "memory").strip().lower() == "redis":
        return RedisCounterStore()
    return None


@dataclass
class QuotaDenial:
    quota_class: str
    dimension: str
    budget: int
    window: str
    # Seconds until the fixed window rolls over and the budget refills; sent
    # as the Retry-After header so clients can tell the user when to retry.
    retry_after: Optional[int] = None

    def detail(self) -> Dict[str, object]:
        return {
            "error": "quota_exceeded",
            "quota_class": self.quota_class,
            "dimension": self.dimension,
            "budget_tokens": self.budget,
            "window": self.window,
        }


class TokenBudgetLedger:
    """In-process fixed-window token ledger over the generated config."""

    def __init__(self, config: Optional[Dict] = None, store: Optional[RedisCounterStore] = None):
        self._store = store if store is not None else _store_from_env()
        self._config_error: Optional[str] = None
        if config is None:
            try:
                config = yaml.safe_load(BUDGETS_PATH.read_text(encoding="utf-8")) or {}
            except Exception as exc:  # noqa: BLE001 - any load fault = fail per class fail_mode
                logger.error("quota budget config unreadable (%s) - fail modes apply", exc)
                self._config_error = str(exc)
                config = {}
        self._classes: Dict[str, Dict] = config.get("classes") or {}
        # (class, dimension, key, window_bucket) -> tokens consumed
        self._counters: Dict[Tuple[str, str, str, int], int] = {}

    # -- internals -------------------------------------------------------

    def _budget(self, quota_class: str, dimension: str) -> Optional[Tuple[int, str, int]]:
        entry = ((self._classes.get(quota_class) or {}).get("tokens") or {}).get(dimension)
        if not entry:
            return None
        return int(entry["budget"]), str(entry["window"]), _window_seconds(entry["window"])

    def _consumed(self, quota_class: str, dimension: str, key: str, window_secs: int, now: float) -> int:
        bucket = int(now // window_secs)
        counter_key = (quota_class, dimension, key, bucket)
        local = self._counters.get(counter_key, 0)
        if self._store is None:
            return local
        return max(local, self._store.get(counter_key))

    def _add(self, quota_class: str, dimension: str, key: str, window_secs: int, tokens: int, now: float) -> None:
        bucket = int(now // window_secs)
        counter_key = (quota_class, dimension, key, bucket)
        self._counters[counter_key] = self._counters.get(counter_key, 0) + tokens
        if self._store is not None:
            self._store.add(counter_key, tokens, window_secs)
        if len(self._counters) > 10000:  # opportunistic prune of expired buckets
            self._counters = {
                (c, d, k, b): v for (c, d, k, b), v in self._counters.items()
                if b >= int(now // _window_seconds("24h")) - 2
            }

    def _exhausted(self, quota_class: str, dimension: str, key: str, now: float) -> Optional[QuotaDenial]:
        budget = self._budget(quota_class, dimension)
        if budget is None:
            return None
        amount, window, window_secs = budget
        if self._consumed(quota_class, dimension, key, window_secs, now) >= amount:
            # Fixed window: the budget refills when the current bucket ends.
            retry_after = max(1, int(window_secs - (now % window_secs)))
            return QuotaDenial(quota_class, dimension, amount, window, retry_after)
        return None

    @staticmethod
    def _group_key(groups: Optional[List[str]]) -> str:
        return "|".join(sorted(groups or [])) or "(none)"

    # -- public API ------------------------------------------------------

    def check(self, quota_class: str, sub: str, groups: Optional[List[str]],
              project_id: Optional[str], now: Optional[float] = None) -> Optional[QuotaDenial]:
        """Return a QuotaDenial if this request must be refused, else None."""
        now = now or time.time()
        cls = self._classes.get(quota_class)
        if cls is None:
            fail_mode = "closed" if self._config_error or not self._classes else "closed"
            logger.warning("unknown quota class %r (config_error=%s) - fail %s",
                           quota_class, self._config_error, fail_mode)
            return QuotaDenial(quota_class, "class", 0, "-")
        # Group budget is the outermost ceiling - always enforced.
        denial = self._exhausted(quota_class, "group", self._group_key(groups), now)
        if denial:
            return denial
        if project_id:
            # Project first; user is the fallback once the project's is gone.
            if not self._exhausted(quota_class, "project", project_id, now):
                return None
            return self._exhausted(quota_class, "user", sub, now)
        return self._exhausted(quota_class, "user", sub, now)

    def consume(self, quota_class: str, sub: str, groups: Optional[List[str]],
                project_id: Optional[str], tokens: int, now: Optional[float] = None) -> None:
        """Attribute consumed tokens per the precedence order."""
        if tokens <= 0 or quota_class not in self._classes:
            return
        now = now or time.time()
        group_budget = self._budget(quota_class, "group")
        if group_budget:
            self._add(quota_class, "group", self._group_key(groups), group_budget[2], tokens, now)
        if project_id:
            project_budget = self._budget(quota_class, "project")
            if project_budget and not self._exhausted(quota_class, "project", project_id, now):
                self._add(quota_class, "project", project_id, project_budget[2], tokens, now)
                return
        user_budget = self._budget(quota_class, "user")
        if user_budget:
            self._add(quota_class, "user", sub, user_budget[2], tokens, now)

    def fail_open(self, quota_class: str) -> bool:
        """Whether a class rides through an enforcement fault (ADR-0511:
        default closed; `open` only when the policy file says so)."""
        return (self._classes.get(quota_class) or {}).get("fail_mode") == "open"


ledger = TokenBudgetLedger()
