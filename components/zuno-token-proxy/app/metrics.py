"""Minimal Prometheus counters, exposed on /metrics as text (no client library needed)."""

from __future__ import annotations

import threading
from typing import Dict, Tuple

_lock = threading.Lock()
_counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}


def inc(name: str, **labels: str) -> None:
    key = (name, tuple(sorted(labels.items())))
    with _lock:
        _counters[key] = _counters.get(key, 0.0) + 1


def value(name: str, **labels: str) -> float:
    return _counters.get((name, tuple(sorted(labels.items()))), 0.0)


def reset() -> None:
    with _lock:
        _counters.clear()


def render() -> str:
    lines = []
    with _lock:
        names = sorted({name for name, _ in _counters})
        for name in names:
            lines.append(f"# TYPE {name} counter")
            for (n, labels), count in sorted(_counters.items()):
                if n != name:
                    continue
                rendered = ",".join(f'{k}="{v}"' for k, v in labels)
                lines.append(f"{name}{{{rendered}}} {count:g}")
    return "\n".join(lines) + "\n"
