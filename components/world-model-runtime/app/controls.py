"""Browser controls to world_engine CtrlInput, with last-value coalescing (ADR-0604 D4, §6.1).

The browser sends `KeyboardEvent.code` names and relative mouse movement; this
module maps them server-side to world_engine button IDs. Never trust a browser
key code: anything outside KEY_MAP is dropped.

Button IDs follow Owl-Control's keycode table, which matches Windows
virtual-key codes in world_engine's own sample (A=65, D=68, S=83, Space=32,
left mouse=1); W=87 and Shift=16 follow the same table. To confirm against the
model during the GPU smoke test (WP-232).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, Optional, Set, Tuple

KEY_MAP: Dict[str, int] = {
    "KeyW": 87,
    "KeyA": 65,
    "KeyS": 83,
    "KeyD": 68,
    "Space": 32,
    "ShiftLeft": 16,
    "ShiftRight": 16,
    "ControlLeft": 17,
    "KeyE": 69,
    "KeyQ": 81,
    "KeyR": 82,
    "KeyF": 70,
    "Mouse0": 1,  # left button
    "Mouse2": 2,  # right button
    # Arrow keys move like WASD for presenters without a mouse grab.
    "ArrowUp": 87,
    "ArrowDown": 83,
}
# Arrow left/right turn the view: a constant horizontal mouse velocity.
TURN_KEYS: Dict[str, float] = {"ArrowLeft": -0.35, "ArrowRight": 0.35}
MAX_KEYS = 8
MOUSE_LIMIT = 1.0


@dataclass(frozen=True)
class Ctrl:
    """One generation step's input (the shape of world_engine.CtrlInput)."""

    button: FrozenSet[int] = frozenset()
    mouse: Tuple[float, float] = (0.0, 0.0)
    scroll_wheel: int = 0


def _clamp(value: float) -> float:
    return max(-MOUSE_LIMIT, min(MOUSE_LIMIT, value))


@dataclass
class ControlState:
    """Latest key state plus accumulated mouse motion since the last step.

    Keys are a state (last message wins); mouse deltas accumulate until a
    generation step takes them, so 60 Hz input never queues behind a 15 Hz
    model step and no motion is lost either.
    """

    _keys: Set[int] = field(default_factory=set)
    _turn: float = 0.0
    _dx: float = 0.0
    _dy: float = 0.0
    _scroll: int = 0
    _last_seq: int = -1
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, seq: int, keys: Iterable[str], mouse: Optional[Dict[str, float]] = None,
               scroll: int = 0) -> bool:
        """Apply one control message. Returns False when it is stale or malformed."""
        if not isinstance(seq, int) or seq <= self._last_seq:
            return False
        key_list = [k for k in keys if isinstance(k, str)][:MAX_KEYS]
        buttons = {KEY_MAP[k] for k in key_list if k in KEY_MAP}
        turn = sum(TURN_KEYS[k] for k in key_list if k in TURN_KEYS)
        dx = dy = 0.0
        if mouse:
            try:
                dx, dy = float(mouse.get("dx", 0.0)), float(mouse.get("dy", 0.0))
            except (TypeError, ValueError):
                return False
            if dx != dx or dy != dy:  # NaN
                return False
        with self._lock:
            self._last_seq = seq
            self._keys = buttons
            self._turn = turn
            self._dx = _clamp(self._dx + dx)
            self._dy = _clamp(self._dy + dy)
            self._scroll = max(-1, min(1, int(scroll or 0)))
        return True

    def take(self) -> Ctrl:
        """The input for the next step; consumes the accumulated mouse motion."""
        with self._lock:
            ctrl = Ctrl(
                button=frozenset(self._keys),
                mouse=(_clamp(self._dx + self._turn), _clamp(self._dy)),
                scroll_wheel=self._scroll,
            )
            self._dx = self._dy = 0.0
            self._scroll = 0
        return ctrl

    def clear(self) -> None:
        with self._lock:
            self._keys = set()
            self._turn = self._dx = self._dy = 0.0
            self._scroll = 0
