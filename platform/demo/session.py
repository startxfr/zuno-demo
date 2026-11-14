"""The presenter's session and freeze marker, on the workstation (ADR-0616 clauses 1 and 8, WP-270).

- `~/.config/zuno/demo-session.json`: the demo in use, its version, the last step played and the step count.
- `~/.config/zuno/demo-freeze.json`: present while a freeze is on (who set it, when). Local by the owner's decision.
- `~/.cache/zuno/demo/`: the Ansible logs and the rehearsal reports.

No credential is ever written here.
"""
from __future__ import annotations

import datetime
import getpass
import json
import os
import pathlib
import socket
import tempfile
from typing import Optional


def config_dir() -> pathlib.Path:
    return pathlib.Path.home() / ".config" / "zuno"


def cache_dir() -> pathlib.Path:
    return pathlib.Path.home() / ".cache" / "zuno" / "demo"


def session_path() -> pathlib.Path:
    return config_dir() / "demo-session.json"


def freeze_path() -> pathlib.Path:
    return config_dir() / "demo-freeze.json"


def logs_dir() -> pathlib.Path:
    return cache_dir() / "logs"


def rehearsals_dir() -> pathlib.Path:
    return cache_dir() / "rehearsals"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def _read_json(path: pathlib.Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_session() -> Optional[dict]:
    """{demo, version, position, total, updated}, or None when no demo is in use."""
    data = _read_json(session_path())
    if not data or not data.get("demo"):
        return None
    data.setdefault("version", None)
    data.setdefault("position", 0)
    data.setdefault("total", 0)
    return data


def save_session(demo: str, version: Optional[str], position: int, total: int) -> dict:
    data = {"demo": demo, "version": version, "position": int(position), "total": int(total), "updated": now_iso()}
    _write_json(session_path(), data)
    return data


def set_position(session: dict, position: int) -> dict:
    return save_session(session["demo"], session.get("version"), position, session.get("total", 0))


def load_freeze() -> Optional[dict]:
    return _read_json(freeze_path())


def freeze_on(reason: str = "") -> dict:
    data = {"who": f"{getpass.getuser()}@{socket.gethostname()}", "when": now_iso()}
    if reason:
        data["reason"] = reason
    _write_json(freeze_path(), data)
    return data


def freeze_off() -> bool:
    try:
        freeze_path().unlink()
        return True
    except FileNotFoundError:
        return False
