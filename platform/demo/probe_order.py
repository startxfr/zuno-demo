#!/usr/bin/env python3
"""The order of a queued golden-path run (ADR-0616 clause 9).

`evaluations/golden_path_probe.py --only a,b` runs the probes in the order it is given, and one probe reads what an
earlier one left: `trace` looks up the run id of `unifai-tekos`. A demo queues its probes in the order its page names
them, and a workshop merges its scenarios' queues, so the queue's order is not the script's. This file puts a queue in
the order of the script's own `PROBES` (read from the script's source, never copied here and never imported: the
script is not run), duplicates removed, before `ansible/demos/_lib/flush_checks.yml` runs it.

    python3 platform/demo/probe_order.py trace unifai-tekos      prints unifai-tekos,trace

`all` (the whole golden path, in the script's order) absorbs every other name. A name the script does not know is
kept, last: the script refuses it by name, which is the error the presenter needs.
"""
from __future__ import annotations

import ast
import pathlib
import sys
from typing import Dict, Iterable, List, Optional, Tuple

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "evaluations/golden_path_probe.py"
ALL = "all"
# What a probe reads from an earlier one (golden_path_probe.py Context.tekos_run_id: "set by unifai-tekos, read by
# trace"). The script's order already puts each need first; a queue that leaves the need out can never pass.
NEEDS: Dict[str, List[str]] = {"trace": ["unifai-tekos"]}


def known(script: Optional[pathlib.Path] = None) -> List[str]:
    """The keys of the script's `PROBES`, in its order."""
    tree = ast.parse((script or SCRIPT).read_text(encoding="utf-8"))
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        value = getattr(node, "value", None)
        if any(isinstance(t, ast.Name) and t.id == "PROBES" for t in targets) and isinstance(value, ast.Dict):
            return [key.value for key in value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]
    raise ValueError(f"{script or SCRIPT}: no PROBES mapping found")


def ordered(names: Iterable[str], order: Optional[List[str]] = None) -> List[str]:
    """The queue in the script's order, each name once; [`all`] when the queue holds it."""
    unique: List[str] = []
    for name in names:
        name = str(name).strip()
        if name and name not in unique:
            unique.append(name)
    if ALL in unique:
        return [ALL]
    order = known() if order is None else order
    return [n for n in order if n in unique] + [n for n in unique if n not in order]


def missing_needs(names: Iterable[str]) -> List[Tuple[str, str]]:
    """(probe, the probe it needs) for each need a queue leaves out; none when the queue holds `all`."""
    queue = [str(n) for n in names]
    if ALL in queue:
        return []
    return [(name, need) for name in queue for need in NEEDS.get(name, []) if need not in queue]


def main(argv: Optional[List[str]] = None) -> int:
    names = [part for arg in (sys.argv[1:] if argv is None else argv) for part in arg.split(",")]
    print(",".join(ordered(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
