"""The guards in front of an action that changes the cluster (ADR-0616 clauses 7 and 8, WP-270).

Order: the freeze marker (refuses install, uninstall, rehearse, scout and record), the summary of the changes, the infrastructure
notice, then the confirmation: the presenter types the demo id, or, without a terminal, `DEMO_CONFIRM` holds that exact
id. There is no global yes. `ansible/playbooks/demo_run.yml` checks the confirmation again.
"""
from __future__ import annotations

import os
import sys
from typing import Callable, Dict, Iterable, Optional, TextIO

import session

FREEZE_REFUSED = ("install", "uninstall", "rehearse", "scout", "record")

DOUBLE_APPROVAL = (
    "INFRASTRUCTURE CHANGE: {unit} of {demo} changes the infrastructure layer (a GPU node, a MachineSet).\n"
    "It needs the platform owner's double approval, given for this run, before you confirm. It never scales down an\n"
    "existing GPU node (ADR-0616 clause 7)."
)


class Refused(Exception):
    """The guard refused; the command exits 2."""


def check_freeze(action: str, freeze: Optional[dict] = None) -> None:
    marker = freeze if freeze is not None else session.load_freeze()
    if marker and action in FREEZE_REFUSED:
        raise Refused(f"`{action}` is refused during a freeze (set by {marker.get('who', '?')} at "
                      f"{marker.get('when', '?')}). `make demo freeze off` ends it.")


def mutation_summary(value) -> str:
    if isinstance(value, dict):
        return str(value.get("summary") or value.get("changes") or "changes the cluster")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "changes the cluster"


def is_infra(value) -> bool:
    return isinstance(value, dict) and bool(value.get("infra"))


def changing_units(manifest: dict, units: Iterable[str]) -> Dict[str, object]:
    """unit name -> its `mutations:` entry, for the units the manifest declares changing."""
    declared = (manifest or {}).get("mutations") or {}
    return {u: declared[u] for u in units if u in declared}


def confirm(demo_id: str, changes: Dict[str, object], *, env: Optional[Dict[str, str]] = None,
            stdin: Optional[TextIO] = None, out: Optional[TextIO] = None,
            ask: Optional[Callable[[str], str]] = None, notices: Optional[Iterable[str]] = None) -> str:
    """Print what will change and return the confirmed demo id, or raise Refused.

    `changes`: unit -> mutations entry. `notices`: what a rehearsal runs on the live platform without changing it
    (its golden-path probes and browser checks: they spend persona budgets). One prompt covers both. Nothing to
    confirm when both are empty (returns "").
    """
    notices = [n for n in (notices or []) if n]
    if not changes and not notices:
        return ""
    env = os.environ if env is None else env
    stdin = stdin or sys.stdin
    out = out or sys.stdout
    if notices:
        out.write(f"This runs on the live platform ({demo_id}):\n")
        for notice in notices:
            out.write(f"  - {notice}\n")
    if changes:
        out.write(f"This changes the cluster ({demo_id}):\n")
    for unit, value in changes.items():
        out.write(f"  - {unit}: {mutation_summary(value)}\n")
    for unit, value in changes.items():
        if is_infra(value):
            out.write("\n" + DOUBLE_APPROVAL.format(unit=unit, demo=demo_id) + "\n")
    out.flush()
    given = env.get("DEMO_CONFIRM")
    if given is not None and given != "":
        if given == demo_id:
            out.write(f"Confirmed by DEMO_CONFIRM={demo_id}.\n")
            return demo_id
        raise Refused(f"DEMO_CONFIRM={given!r} does not confirm {demo_id!r}: it must hold this demo's exact id.")
    is_tty = False
    try:
        is_tty = stdin.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    if not is_tty:
        raise Refused(f"No terminal to confirm on: set DEMO_CONFIRM={demo_id} to confirm this demo, and only this one.")
    reader = ask or (lambda prompt: _ask_tty(prompt, stdin, out))
    typed = reader(f"Type the demo id ({demo_id}) to go on, anything else to stop: ").strip()
    if typed != demo_id:
        raise Refused("Not confirmed: nothing was changed.")
    return demo_id


def _ask_tty(prompt: str, stdin: TextIO, out: TextIO) -> str:
    out.write(prompt)
    out.flush()
    line = stdin.readline()
    return line if line else ""


def time_key(key) -> str:
    """A `steps:` key as M:SS. YAML 1.1 reads an unquoted 9:30 as the base-60 integer 570; quote the keys."""
    if isinstance(key, int) and not isinstance(key, bool):
        return f"{key // 60}:{key % 60:02d}"
    return str(key)


def step_metadata(manifest: dict) -> Dict[str, dict]:
    steps = (manifest or {}).get("steps") or {}
    return {time_key(t): m for t, m in steps.items() if isinstance(m, dict)}


def mutating_steps(manifest: dict) -> Dict[str, dict]:
    """step time -> metadata, for the steps the manifest declares changing (never run by `step`)."""
    return {t: m for t, m in step_metadata(manifest).items() if m.get("mutating")}


def step_meta(manifest: dict, time: str) -> dict:
    return step_metadata(manifest).get(time, {})


def forbidden_in_freeze(meta: dict) -> bool:
    return str(meta.get("freeze", "")).lower() == "forbidden"

