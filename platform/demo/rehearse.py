"""`make demo rehearse <id> 5|15`: the whole sequence without pauses, with a report (ADR-0616 clause 11, WP-270).

status, check, install, start, every step, stop, uninstall, in one runner playbook run. A step the manifest declares
changing is never run: it is recorded `SKIPPED (mutating)`, optional or not. The report goes to
`~/.cache/zuno/demo/rehearsals/<id>-<version>-<date>.md` and ends with `RESULT: PASS` or `RESULT: FAIL`. The session is
never touched.
"""
from __future__ import annotations

import datetime
import pathlib
from typing import Dict, List, Optional, Tuple

import guard
import session
from catalogue import Page
from runner import RunResult, Unit, UnitResult

VERSION_LABEL = {"5": "5-minute", "15": "15-minute"}


def plan_units(page: Page, version: str, demo_dir: pathlib.Path, manifest: dict) -> Tuple[List[Unit], List[UnitResult]]:
    """(units to run, results decided without running: skipped and missing files), in sequence order."""
    to_run: List[Unit] = []
    decided: List[UnitResult] = []
    order = ["status", "check", "install", "start"]
    for action in order:
        _add(action, f"{action}.yml", "action", demo_dir, to_run, decided)
    mutating = guard.mutating_steps(manifest)
    for step in page.steps(version):
        if step.time in mutating:
            decided.append(UnitResult(step.time, "skipped"))
            continue
        _add(step.time, f"steps/{step.file_name}", "step", demo_dir, to_run, decided)
    for action in ("stop", "uninstall"):
        _add(action, f"{action}.yml", "action", demo_dir, to_run, decided)
    return to_run, decided


def _add(name: str, rel: str, kind: str, demo_dir: pathlib.Path, to_run: List[Unit], decided: List[UnitResult]) -> None:
    if (demo_dir / rel).is_file():
        to_run.append(Unit(name, rel, kind))
    else:
        decided.append(UnitResult(name, "missing", error=f"{rel} is missing (WP-271)"))


def sequence(page: Page, version: str) -> List[str]:
    return ["status", "check", "install", "start"] + [s.time for s in page.steps(version)] + ["stop", "uninstall"]


def merge(page: Page, version: str, run: Optional[RunResult], decided: List[UnitResult]) -> List[UnitResult]:
    by_name = {u.name: u for u in decided}
    for u in (run.units if run else []):
        by_name[u.name] = u
    return [by_name.get(name, UnitResult(name, "failed", error="no result")) for name in sequence(page, version)]


def report(page: Page, version: str, results: List[UnitResult], run: Optional[RunResult],
           changing: Optional[Dict[str, object]] = None, confirmed: str = "") -> Tuple[str, bool]:
    """The rehearsal report. `changing`: the units the manifest declares changing that this rehearsal ran, with what
    they change; `confirmed`: the demo id that confirmed them (typed or DEMO_CONFIRM)."""
    passed = not any(r.failed for r in results) and not (run and run.error)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    skipped = [r.name for r in results if r.status == "skipped"]
    if changing:
        units = "; ".join(f"{unit} ({guard.mutation_summary(value)})" for unit, value in changing.items())
        changes = f"- Changing units, confirmed by `{confirmed or '?'}`: {units}"
    else:
        changes = "- Changing units: none (every action is a read or has nothing to run)"
    lines = [
        f"# Rehearsal: {page.id}, {VERSION_LABEL[version]} version",
        "",
        f"- Date: {stamp}",
        f"- Page: `{page.path.name}`",
        changes,
        f"- Steps not run (declared mutating): {', '.join(skipped)}" if skipped else "- Steps not run: none",
        f"- Log: `{run.log_path}`" if run and run.log_path else "- Log: none (nothing ran)",
        "",
        "| Unit | Result | Seconds | Detail |",
        "|---|---|---|---|",
    ]
    for r in results:
        detail = "; ".join(filter(None, [r.error] + r.messages + [
            f"{c.get('cmd')} -> exit {c.get('rc')}" for c in r.commands if c.get("rc") not in (0, None)] + [
            f"{c.get('id')} FAIL" for c in r.checks if c.get("passed") not in (True, "True", "true")]))
        status = {"ok": "PASS", "nothing": "PASS (nothing to run)", "skipped": "SKIPPED (mutating)",
                  "missing": "FAIL (missing)", "failed": "FAIL"}.get(r.status, r.status)
        cell = detail.replace("|", "\\|")
        lines.append(f"| {r.name} | {status} | {r.seconds:.1f} | {cell} |")
    if run and run.error:
        lines += ["", f"Runner error: {run.error}"]
    lines += ["", f"RESULT: {'PASS' if passed else 'FAIL'}", ""]
    return "\n".join(lines), passed


def write_report(page: Page, version: str, text: str) -> pathlib.Path:
    directory = session.rehearsals_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = directory / f"{page.id}-{version}-{stamp}.md"
    path.write_text(text, encoding="utf-8")
    return path


def last_rehearsal(demo_id: str, version: str) -> Optional[Tuple[str, str]]:
    """(date, PASS|FAIL) of the newest report, or None."""
    directory = session.rehearsals_dir()
    if not directory.is_dir():
        return None
    reports = sorted(directory.glob(f"{demo_id}-{version}-*.md"))
    reports = [p for p in reports if p.name[len(demo_id) + len(version) + 2:][:4].isdigit()]
    if not reports:
        return None
    newest = reports[-1]
    result = "?"
    for line in newest.read_text(encoding="utf-8").split("\n"):
        if line.startswith("RESULT: "):
            result = line.split(": ", 1)[1].strip()
    date = newest.stem[len(demo_id) + len(version) + 2:][:10]
    return date, result
