"""ADR-0596: an experience client's declared model names select one of its tasks.

An experience client (Open WebUI, OpenClaw: the MARKER_FAIL_CLOSED_CLIENTS list,
ADR-0594) is shown `auto` ("Zuno") plus one model per entry of
MODEL_TASK_ALIASES, e.g. `zuno-code` ("Zuno Code"). Picking one sets the task of
the call in place of the `X-Zuno-Task` header. The name never selects a provider:
the routing policy entry of (client, task), generated from the agents release,
does, and the classification still decides what is eligible.

    MODEL_TASK_ALIASES  "<model id>=<task>[:<display name>]", comma-separated.
                        Default: "zuno-code=code:Zuno Code".

Every other caller, and every other model value, keeps the header's task.
"""
from __future__ import annotations

import os
from typing import Dict, List, Tuple

from app import tool_markers

_DEFAULT = "zuno-code=code:Zuno Code"


def aliases() -> Dict[str, Tuple[str, str]]:
    """model id -> (task, display name). Malformed entries are skipped."""
    out: Dict[str, Tuple[str, str]] = {}
    for item in os.getenv("MODEL_TASK_ALIASES", _DEFAULT).split(","):
        model, sep, rest = item.strip().partition("=")
        task, _, name = rest.partition(":")
        model, task, name = model.strip(), task.strip(), name.strip()
        if sep and model and task and model != "auto":
            out[model] = (task, name or model)
    return out


def task_for(client: str, model: str, header_task: str) -> str:
    """The task a call is routed under."""
    if not tool_markers.is_fail_closed_client(client or ""):
        return header_task
    entry = aliases().get((model or "").strip())
    return entry[0] if entry else header_task


def listed_models() -> List[Tuple[str, str]]:
    """(id, display name) of the alias models, after `auto`."""
    return [(model, name) for model, (_task, name) in aliases().items()]
