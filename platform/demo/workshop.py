"""Workshops by composition (ADR-0616 clause 10, WP-280).

A workshop page has an `## Agenda` table, `| Time | Block | Play | Transition to the next block |`. Its manifest
(`ansible/demos/<workshop>/demo.yml`) lists the same rows as an `agenda:`:

    - {at: "0:00", own: true}                                    the workshop's own row (opening, close)
    - {at: "0:03", scenario: "unifai-agents", version: "5"}      every step of a scenario version
    - {at: "0:33", scenario: "ai-gateway-sovereignty", version: "15", only: ["10:30", "12:30"]}   named steps
    - {at: "0:38", inline: "same-rules-one-dashboard"}           a section of the workshop page with a timed table

A scenario step is played from the scenario's own directory: no file is duplicated. Own and inline rows have their
step files under the workshop directory (`steps/agenda-H-MM.yml`, `steps/agenda-H-MM--MM-SS.yml`). The actions chain
the distinct scenarios' action files (status, check, install and start in agenda order, stop and uninstall in
reverse), then the workshop's own file; probes and browser checks queued by the scenarios run once, in the
workshop's own check or start file.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import catalogue
import guard
from runner import Unit, UnitResult

AGENDA_SECTION = "Agenda"
AGENDA_HEADER = ["Time", "Block", "Play", "Transition to the next block"]
VERSION_ANCHORS = {"5-minute-version": "5", "15-minute-version": "15"}
FORWARD = ("status", "check", "install", "start")
BACKWARD = ("stop", "uninstall")
DEFERRED_FLUSH = ("check", "start")


class AgendaError(ValueError):
    """The agenda of a manifest does not resolve against the pages."""


@dataclass
class AgendaRow:
    at: str
    block: str
    play: str
    transition: str
    line: int
    kind: str = "own"                  # own | scenario | inline
    scenario: str = ""
    version: str = ""
    only: List[str] = field(default_factory=list)
    inline: str = ""

    def entry(self) -> dict:
        """The manifest entry this row expects."""
        if self.kind == "scenario":
            data = {"at": self.at, "scenario": self.scenario, "version": self.version}
            if self.only:
                data["only"] = list(self.only)
            return data
        if self.kind == "inline":
            return {"at": self.at, "inline": self.inline}
        return {"at": self.at, "own": True}


@dataclass
class FlatStep:
    number: int
    name: str            # unique unit name: "0:00", "0:03/0:45"
    kind: str            # own | scenario | inline
    at: str
    block: str
    demo_id: str         # the directory that holds the step file
    file: str            # relative to that directory
    step: catalogue.Step
    position: int = 1    # within its block
    of: int = 1
    version: str = ""
    transition: str = ""  # on the last step of a scenario or inline block


def agenda_file(at: str, inner: Optional[catalogue.Step] = None) -> str:
    hours, minutes = at.split(":")
    name = f"agenda-{int(hours)}-{minutes}"
    if inner is not None:
        name += "--" + inner.file_name[:-len(".yml")]
    return f"steps/{name}.yml"


def inline_steps(page: catalogue.Page, slug: str) -> List[catalogue.Step]:
    """The timed rows of the workshop page's section with this slug ([] when it has none)."""
    for section in page.sections:
        if section.slug != slug:
            continue
        for table in catalogue.tables_of(section.lines, section.line + 1):
            if table.header != catalogue.STEP_HEADER:
                continue
            steps = []
            for line_no, cells in table.rows:
                if len(cells) == 4 and catalogue.TIME_RE.match(cells[0]):
                    steps.append(catalogue.Step(len(steps) + 1, cells[0], "w", cells[1], cells[2], cells[3], line_no))
            return steps
    return []


def agenda_rows(page: catalogue.Page) -> List[AgendaRow]:
    """The rows of the page's `## Agenda` table, each classified from its Play cell."""
    section = page.section(AGENDA_SECTION)
    if section is None:
        return []
    rows: List[AgendaRow] = []
    for table in catalogue.tables_of(section.lines, section.line + 1):
        if table.header != AGENDA_HEADER:
            continue
        for line_no, cells in table.rows:
            if len(cells) != 4 or not catalogue.TIME_RE.match(cells[0]):
                continue
            row = AgendaRow(cells[0], cells[1], cells[2], cells[3], line_no)
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", row.play):
                path, _, anchor = target.partition("#")
                if path.endswith(".md") and anchor in VERSION_ANCHORS:
                    row.kind, row.scenario = "scenario", pathlib.PurePosixPath(path).stem
                    row.version = VERSION_ANCHORS[anchor]
                    if re.search(r"\bonly\b", row.play):
                        row.only = re.findall(r"\((\d{1,2}:\d{2})\)", row.play)
                    break
                if not path and anchor and inline_steps(page, anchor):
                    row.kind, row.inline = "inline", anchor
                    break
            rows.append(row)
    return rows


def scenarios(manifest: dict) -> List[str]:
    """The distinct scenarios of an agenda, in agenda order."""
    found: List[str] = []
    for entry in (manifest or {}).get("agenda") or []:
        name = entry.get("scenario") if isinstance(entry, dict) else None
        if name and name not in found:
            found.append(name)
    return found


def expand(page: catalogue.Page, manifest: dict, root: Optional[pathlib.Path] = None) -> List[FlatStep]:
    """The workshop's steps in agenda order. Raises AgendaError when an entry does not resolve."""
    root = root or catalogue.repo_root()
    rows = {row.at: row for row in agenda_rows(page)}
    flat: List[FlatStep] = []
    for entry in (manifest or {}).get("agenda") or []:
        if not isinstance(entry, dict) or "at" not in entry:
            raise AgendaError(f"{page.id}: an agenda entry needs `at`: {entry!r}")
        at = guard.time_key(entry["at"])
        row = rows.get(at)
        if row is None:
            raise AgendaError(f"{page.id}: agenda entry {at} is not a row of the page's Agenda table")
        if entry.get("scenario"):
            try:
                scenario = catalogue.load(catalogue.find(entry["scenario"], root))
            except KeyError:
                raise AgendaError(f"{page.id}: agenda entry {at} names an unknown scenario {entry['scenario']!r}")
            version = str(entry.get("version", ""))
            if scenario.kind != "scenario" or version not in catalogue.VERSION_SECTIONS:
                raise AgendaError(f"{page.id}: agenda entry {at} needs a scenario and a version 5 or 15")
            steps = scenario.steps(version)
            only = [guard.time_key(t) for t in entry.get("only") or []]
            missing = [t for t in only if t not in {s.time for s in steps}]
            if missing:
                raise AgendaError(f"{page.id}: agenda entry {at}: {scenario.id} {version} has no step "
                                  f"{', '.join(missing)}")
            chosen = [s for s in steps if not only or s.time in only]
            for i, step in enumerate(chosen, 1):
                flat.append(FlatStep(0, f"{at}/{step.time}", "scenario", at, row.block, scenario.id,
                                     f"steps/{step.file_name}", step, i, len(chosen), version,
                                     row.transition if i == len(chosen) else ""))
        elif entry.get("inline"):
            steps = inline_steps(page, entry["inline"])
            if not steps:
                raise AgendaError(f"{page.id}: agenda entry {at}: section #{entry['inline']} holds no timed table")
            for i, step in enumerate(steps, 1):
                flat.append(FlatStep(0, f"{at}/{step.time}", "inline", at, row.block, page.id,
                                     agenda_file(at, step), step, i, len(steps), "",
                                     row.transition if i == len(steps) else ""))
        else:
            step = catalogue.Step(1, at, "w", row.play, row.transition, "", row.line)
            flat.append(FlatStep(0, at, "own", at, row.block, page.id, agenda_file(at), step))
    for number, item in enumerate(flat, 1):
        item.number = number
    return flat


def own_step_files(page: catalogue.Page) -> Dict[str, Tuple[str, catalogue.Step]]:
    """relative file -> (agenda time, step) for the own and inline rows of the page: the workshop's own step files."""
    files: Dict[str, Tuple[str, catalogue.Step]] = {}
    for row in agenda_rows(page):
        if row.kind == "own":
            files[agenda_file(row.at)] = (row.at, catalogue.Step(1, row.at, "w", row.play, row.transition, "", row.line))
        elif row.kind == "inline":
            for step in inline_steps(page, row.inline):
                files[agenda_file(row.at, step)] = (row.at, step)
    return files


def action_units(workshop_id: str, manifest: dict, action: str, root: Optional[pathlib.Path] = None) -> List[Unit]:
    """The chain of one action: each distinct scenario's file, then the workshop's own."""
    names = scenarios(manifest)
    if action in BACKWARD:
        names = list(reversed(names))
    units = [Unit(f"{action}:{name}", f"{action}.yml", "action", dir=str(catalogue.demo_dir(name, root)), demo=name,
                  action=action, defer_flush=action in DEFERRED_FLUSH) for name in names]
    units.append(Unit(action, f"{action}.yml", "action", demo=workshop_id, action=action))
    return units


def step_unit(item: FlatStep, root: Optional[pathlib.Path] = None) -> Unit:
    return Unit(item.name, item.file, "step", dir=str(catalogue.demo_dir(item.demo_id, root)), demo=item.demo_id,
                time=item.step.time)


def changing(units: List[Unit], manifests: Dict[str, dict]) -> Dict[str, object]:
    """unit name -> what it changes, for the action units their own manifest declares changing."""
    found: Dict[str, object] = {}
    for unit in units:
        declared = (manifests.get(unit.demo) or {}).get("mutations") or {}
        if unit.kind == "action" and unit.action in declared:
            found[unit.name] = declared[unit.action]
    return found


def rehearsal(page: catalogue.Page, manifest: dict, manifests: Dict[str, dict],
              root: Optional[pathlib.Path] = None) -> Tuple[List[Unit], List[UnitResult], List[str]]:
    """(units to run, results decided without running, every unit name in sequence order)."""
    to_run: List[Unit] = []
    decided: List[UnitResult] = []
    order: List[str] = []

    def add(unit: Unit) -> None:
        order.append(unit.name)
        skip = ((manifests.get(unit.demo) or {}).get("not_rehearsed") or {}) if unit.kind == "action" else {}
        if unit.action in skip:
            decided.append(UnitResult(unit.name, "skipped", messages=[f"not rehearsed: {skip[unit.action]}"]))
        elif not (pathlib.Path(unit.dir or catalogue.demo_dir(page.id, root)) / unit.file).is_file():
            decided.append(UnitResult(unit.name, "missing", error=f"{unit.demo}/{unit.file} is missing"))
        else:
            to_run.append(unit)

    for action in FORWARD:
        for unit in action_units(page.id, manifest, action, root):
            add(unit)
    for item in expand(page, manifest, root):
        unit = step_unit(item, root)
        if guard.step_meta(manifests.get(item.demo_id) or {}, item.step.time).get("mutating"):
            order.append(unit.name)
            decided.append(UnitResult(unit.name, "skipped"))
        else:
            add(unit)
    for action in BACKWARD:
        for unit in action_units(page.id, manifest, action, root):
            add(unit)
    return to_run, decided, order


def load_manifests(workshop_id: str, manifest: dict, loader: Callable[[pathlib.Path], dict],
                   root: Optional[pathlib.Path] = None) -> Dict[str, dict]:
    """demo id -> manifest, for the workshop and each of its scenarios ({} when a directory is missing)."""
    result = {workshop_id: manifest}
    for name in scenarios(manifest):
        directory = catalogue.demo_dir(name, root)
        result[name] = loader(directory) if directory.is_dir() else {}
    return result
