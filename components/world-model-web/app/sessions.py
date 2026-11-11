"""The GPU lease, session state and per-user limits (ADR-0604 §4.2, §4.3, §8.3).

One world holds the GPU at a time. The lease is taken before the (slow) image
generation so a second visitor is told "busy" at once instead of queuing behind
it. Everything is in memory: a restart of the pod drops the lease, and the
visitor gets an explicit "session lost" rather than a frozen frame.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Optional

from app import metrics
from app.config import Settings


class Busy(Exception):
    def __init__(self, holder: str):
        super().__init__("busy")
        self.holder = holder


class QuotaExceeded(Exception):
    def __init__(self, retry_after: int):
        super().__init__("quota")
        self.retry_after = retry_after


@dataclass
class Session:
    session_id: str
    owner_sub: str
    owner_name: str
    source: str  # "preset:<id>" or "prompt"
    seed: int
    state: str = "PREPARING_IMAGE"
    world_id: str = ""
    base_png_b64: str = ""  # the image the world started from, kept for reset
    scene_prompt: str = ""  # the text it came from, passed to the runtime to anchor the scene against drift
    prompt_requested: int = 0
    prompt_applied: int = 0
    streaming: bool = False
    runtime_ws: object = None  # the websockets connection while a stream is open
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    clock: Callable[[], float] = time.monotonic
    created: float = 0.0
    last_activity: float = 0.0

    def __post_init__(self) -> None:
        self.created = self.last_activity = self.clock()

    def touch(self) -> None:
        self.last_activity = self.clock()

    def public(self) -> dict:
        now = self.clock()
        return {
            "session_id": self.session_id, "world_id": self.world_id, "state": self.state, "source": self.source,
            "prompt_requested": self.prompt_requested, "prompt_applied": self.prompt_applied,
            "streaming": self.streaming, "age_seconds": int(now - self.created),
        }


class Lease:
    def __init__(self, settings: Settings, clock: Callable[[], float] = time.monotonic):
        self.settings = settings
        self.clock = clock
        self.current: Optional[Session] = None
        self._starts: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    def check_quota(self, sub: str) -> None:
        window = 3600.0
        now = self.clock()
        starts = self._starts[sub]
        while starts and now - starts[0] > window:
            starts.popleft()
        if len(starts) >= self.settings.worlds_per_hour:
            metrics.QUOTA_REJECTED.labels(limit="worlds_per_hour").inc()
            raise QuotaExceeded(int(window - (now - starts[0])) + 1)

    async def acquire(self, owner_sub: str, owner_name: str, source: str, seed: int) -> Session:
        async with self._lock:
            if self.current is not None:
                metrics.BUSY_REJECTED.inc()
                raise Busy(self.current.owner_name)
            self.check_quota(owner_sub)
            self._starts[owner_sub].append(self.clock())
            self.current = Session(uuid.uuid4().hex, owner_sub, owner_name, source, seed, clock=self.clock)
            metrics.SESSIONS_ACTIVE.set(1)
            return self.current

    def get(self, session_id: str) -> Optional[Session]:
        current = self.current
        return current if current is not None and current.session_id == session_id else None

    def release(self, session: Session, reason: str) -> bool:
        """Free the lease if `session` still holds it. Returns whether it did."""
        if self.current is not session:
            return False
        session.state = "CLOSED"
        session.stop.set()
        self.current = None
        metrics.SESSIONS_ACTIVE.set(0)
        metrics.SESSION_ENDED.labels(reason=reason).inc()
        return True

    def expired(self) -> Optional[str]:
        """Why the current session should be released now, if it should."""
        session = self.current
        if session is None:
            return None
        now = self.clock()
        if now - session.created > self.settings.max_session_seconds:
            return "max_duration"
        quiet = now - session.last_activity
        if not session.streaming and session.state != "PREPARING_IMAGE" and quiet > self.settings.detached_seconds:
            return "detached"
        if quiet > self.settings.idle_seconds:
            return "idle"
        return None
