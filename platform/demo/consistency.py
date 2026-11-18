"""The pages and the demo files agree (ADR-0616 clause 14, WP-271).

    python3 platform/demo/consistency.py [--only <id>]

problems() lists every disagreement; platform/demo/tests/test_demo_catalogue.py asserts there is none:
- every demo of the catalogue has its directory, its manifest and its six action files; a scenario has one step file
  per timed row and no other; the `steps:` keys of the manifest are quoted time stamps of the page;
- every file loads as a task list; a unit the manifest does not declare changing uses only the read-only `_lib`
  files, `kubernetes.core.k8s_info`, `stat`, `debug`, `set_fact`, `assert` and `fail`; every `cmd` passes
  readonly.py;
- every backticked `oc`, `make`, `curl` or `git` command of a Do cell is covered by a `cmd`, a `page_text` or a
  `not_run` entry of its step file;
- only the world-model directory names a MachineSet outside a read command, and nothing names `zuno-gpu-a` there;
- a ClusterServiceVersion is read by `name_prefix`, never by its versioned name;
- a workshop's `agenda:` matches the page's Agenda table row by row (scenario, version anchor, `only` times that
  exist, inline section with a timed table), its own and inline rows have their step files, and its check and start
  files run the queued probes;
- a page that has moved has `## Presenter lifecycle` with exactly `### Status` ... `### Uninstall`, none empty;
- every backticked `make demo <verb>` under docs/ is a verb of DEMO_VERBS (the Makefile);
- the page shape of ADR-0617 (WP-285), for every page that has `## Presenter lifecycle`: its `##` sections in the
  contract's order (a workshop: Introduction, Personas, Agenda, Presenter lifecycle first, References and Page status
  last), no ADR or WP reference and no link into docs/adr/ or docs/roadmap/ in the Introduction, Personas or Presenter
  lifecycle, and the `> **Status:**` banner under `## Page status` only;
- demo.yml `record: {kind, allow, cols, rows}` (ADR-0618): kind browser (a walkthrough), terminal, or assembled (made
  by hand from media that exist, with its cut list); each `allow`
  entry is a Do command of the 5-minute version, never a command the capture never types; `allow`, `cols` and `rows`
  only on a terminal take, the size within capture.window()'s bounds;
- a published GIF `docs/assets/img/demo/<id>.gif` belongs to a catalogue demo, is at most 8 MB, and is embedded as the
  last line of that demo's Introduction (and only there); a page embeds no other demo's GIF.
Warnings, never failures: an object a moved page's `### Status` or `### Check` names in backticks that its file does
not read (warnings()). ADRs and roadmap records
  are history and are not read; a demo page that has not moved yet is not read; a retired verb may be named on a
  line that says it is retired.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Dict, Iterable, List, Optional, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import catalogue  # noqa: E402
import gif  # noqa: E402
import guard  # noqa: E402
import probe_order  # noqa: E402
import readonly  # noqa: E402
import rehearse  # noqa: E402
import workshop  # noqa: E402
from runner import Unit  # noqa: E402

import yaml  # noqa: E402

READ_LIBS = {"nothing_to_run.yml", "run_reads.yml", "argo_apps.yml", "workloads.yml", "routes.yml", "cr_ready.yml",
             "trainjob_evidence.yml", "queue_probes.yml", "queue_browser.yml", "flush_checks.yml", "render.yml"}
READ_MODULES = {"kubernetes.core.k8s_info", "k8s_info", "ansible.builtin.stat", "stat", "ansible.builtin.debug",
                "debug", "ansible.builtin.set_fact", "set_fact", "ansible.builtin.assert", "assert",
                "ansible.builtin.fail", "fail"}
INCLUDES = {"ansible.builtin.include_tasks", "include_tasks"}
TASK_KEYWORDS = {"name", "vars", "when", "loop", "loop_control", "register", "changed_when", "failed_when", "tags",
                 "no_log", "ignore_errors", "until", "retries", "delay", "environment", "timeout", "args",
                 "check_mode", "become", "delegate_to", "run_once", "notify", "with_items", "block", "rescue",
                 "always"}
RETIRED_VERBS = {"reset", "all-check", "step-1", "step-2", "step-3", "step-4", "step-5", "step-N", "step-1..5"}
RETIRED_WORDS = re.compile(r"retired|removed|replaced|deleted", re.IGNORECASE)
DOC_VERB_RE = re.compile(r"`[^`]*?\bmake demo ([a-z0-9][a-z0-9.-]*)[^`]*`")


class _Loader(yaml.SafeLoader):
    """A safe loader that reads Ansible's `!unsafe` tag as the plain string it marks."""


_Loader.add_constructor("!unsafe", lambda loader, node: loader.construct_scalar(node))


def load_yaml(path: pathlib.Path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)


def demo_verbs(root: pathlib.Path) -> Set[str]:
    makefile = root / "Makefile"
    if not makefile.exists():
        makefile = catalogue.ENGINE_ROOT / "Makefile"
    m = re.search(r"^DEMO_VERBS\s*:?=\s*(.+)$", makefile.read_text(encoding="utf-8"), re.M)
    return set(m.group(1).split()) if m else set()


def _norm(command: str) -> str:
    return re.sub(r"\s+", " ", str(command)).strip()


def module_of(task: dict) -> Optional[str]:
    keys = [k for k in task if k not in TASK_KEYWORDS]
    return keys[0] if keys else None


def walk_tasks(tasks) -> Iterable[dict]:
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        yield task
        for key in ("block", "rescue", "always"):
            if isinstance(task.get(key), list):
                yield from walk_tasks(task[key])


def commands_of(tasks) -> Dict[str, List]:
    """{"cmd": [...], "page_text": [...], "not_run": [...], "env": {...}} gathered from run_reads includes."""
    found = {"cmd": [], "page_text": [], "not_run": [], "env": {}}
    for task in walk_tasks(tasks):
        variables = task.get("vars") or {}
        if not isinstance(variables, dict):
            continue
        found["env"].update(variables.get("demo_env") or {})
        for item in variables.get("run_reads") or []:
            if isinstance(item, dict):
                found["cmd"].append(item.get("cmd", ""))
                if item.get("page_text"):
                    found["page_text"].append(item["page_text"])
                found["env"].update(item.get("env") or {})
            else:
                found["cmd"].append(item)
        for item in variables.get("not_run") or []:
            if isinstance(item, dict) and item.get("page_text"):
                found["not_run"].append(item["page_text"])
    return found


def _strings_outside_commands(node, inside_commands: bool = False) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _strings_outside_commands(value, inside_commands or key in ("run_reads", "not_run"))
    elif isinstance(node, list):
        for value in node:
            yield from _strings_outside_commands(value, inside_commands)
    elif isinstance(node, str) and not inside_commands:
        yield node


def unit_problems(rel: str, tasks, changing: bool, variables: Dict[str, str], demo_id: str) -> List[str]:
    problems: List[str] = []
    if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
        return [f"{rel}: not a task list"]
    for task in walk_tasks(tasks):
        module = module_of(task)
        if module is None:
            continue
        if not changing:
            if module in INCLUDES:
                target = str(task[module] if not isinstance(task[module], dict) else task[module].get("file", ""))
                lib = target.rsplit("/", 1)[-1]
                if not target.startswith("{{ demo_lib }}/") or lib not in READ_LIBS:
                    problems.append(f"{rel}: includes {target}, not a read-only _lib file (declare the unit in "
                                    "demo.yml `mutations:` if it changes the cluster)")
            elif module not in READ_MODULES:
                problems.append(f"{rel}: module {module} in a unit not declared changing")
    found = commands_of(tasks)
    names = dict(variables)
    names.update({k: "x" for k in found["env"]})
    for cmd in found["cmd"]:
        ok, reason = readonly.check(cmd, names)
        if not ok:
            problems.append(f"{rel}: `{cmd}` is refused by readonly.py: {reason}")
    for task in walk_tasks(tasks):
        for entry in ((task.get("vars") or {}).get("cr_ready") or []) if isinstance(task.get("vars"), dict) else []:
            if isinstance(entry, dict) and entry.get("kind") == "ClusterServiceVersion" and "name" in entry:
                problems.append(f"{rel}: ClusterServiceVersion {entry['name']} is pinned by name: use `name_prefix` "
                                "(an OLM upgrade renames it)")
    strings = list(_strings_outside_commands(tasks))
    if demo_id != "world-model" and any("machineset" in s.lower() for s in strings):
        problems.append(f"{rel}: names a MachineSet outside a read command (only world-model may)")
    if any("zuno-gpu-a" in s for s in strings):
        problems.append(f"{rel}: names zuno-gpu-a outside a read command (nothing scales it)")
    return problems


def lifecycle_problems(page: catalogue.Page, rel: str) -> List[str]:
    section = page.section(catalogue.LIFECYCLE_SECTION)
    if section is None:
        return []
    subs = page.subsections(section)
    titles = [s.title for s in subs]
    expected = [a.capitalize() for a in catalogue.LIFECYCLE_ACTIONS]
    problems = []
    if titles != expected:
        problems.append(f"{rel}: `## Presenter lifecycle` holds {titles}, expected {expected}")
    for sub in subs:
        if not sub.text.strip():
            problems.append(f"{rel}: `### {sub.title}` is empty (write \"Nothing to do.\")")
    return problems


TAKE_KINDS = ("browser", "terminal", "assembled")   # assembled: made by hand from media that exist (gif.py)
TERMINAL_SIZE = ("cols", "rows")       # the capture's window; capture.window() holds the one rule (bounds, defaults)


def _capture():
    """evaluations/browser/terminal/capture.py as a module: its `never(command)` (the commands no `record.allow` can
    open, ADR-0618 clause 7) and `window(record)` (the terminal's size rule). None when it is absent from this tree."""
    if "zuno_capture" in sys.modules:
        return sys.modules["zuno_capture"]
    path = catalogue.ENGINE_ROOT / "evaluations" / "browser" / "terminal" / "capture.py"
    if not path.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("zuno_capture", str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules["zuno_capture"] = module                 # its dataclasses look their module up while it loads
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def record_problems(entry: catalogue.Entry, page: catalogue.Page, manifest: dict, root: pathlib.Path) -> List[str]:
    """demo.yml `record: {kind, allow, cols, rows, skip}` (ADR-0618 clause 7, WP-287, WP-289): the kind of take, the
    commands a terminal take may type beyond the read-only allowlist (each a Do command of the 5-minute version, never
    an always-refused one), the terminal's size when a table needs more than 100x30, and the 5-minute rows a terminal
    take does not type (each a row with a Do command, with its reason)."""
    rel = f"ansible/demos/{entry.id}/demo.yml"
    record = manifest.get("record")
    if record is None:
        return []
    if not isinstance(record, dict):
        return [f"{rel}: `record` must be a mapping {{kind, allow, cols, rows}}"]
    found = []
    unknown = sorted(set(record) - {"kind", "allow", "skip"} - set(TERMINAL_SIZE))
    if unknown:
        found.append(f"{rel}: `record` has unknown key(s) {', '.join(unknown)}")
    kind = record.get("kind", "browser")
    allow = record.get("allow") or []
    if kind not in TAKE_KINDS:
        found.append(f"{rel}: `record.kind` is {kind!r}, one of {', '.join(TAKE_KINDS)}")
    elif kind == "browser":
        walkthrough = root / "evaluations" / "browser" / "walkthroughs" / f"{entry.id}.mjs"
        if gif.cut_list_path(entry.id, root).is_file() and not walkthrough.is_file():
            found.append(f"{rel}: a browser take needs evaluations/browser/walkthroughs/{entry.id}.mjs")
        if allow:
            found.append(f"{rel}: `record.allow` is for a terminal take; a browser take types nothing")
        for key in TERMINAL_SIZE:
            if key in record:
                found.append(f"{rel}: `record.{key}` is for a terminal take; a browser take has its walkthrough's "
                             "viewport")
        if "skip" in record:
            found.append(f"{rel}: `record.skip` is for a terminal take; a browser take plays its walkthrough")
    elif kind == "assembled":
        for key in ("allow", "skip") + TERMINAL_SIZE:
            if key in record:
                found.append(f"{rel}: `record.{key}` is for a terminal take; an assembled take is cut from media "
                             "that already exist")
        if not gif.cut_list_path(entry.id, root).is_file():
            found.append(f"{rel}: an assembled take needs its cut list, ansible/demos/{entry.id}/gif.yml")
    capture = _capture() if kind == "terminal" else None
    if capture is not None:
        found += [f"{rel}: {problem}" for problem in capture.window(record)[2]]
        rows = [(step.time, bool(catalogue.do_commands(step.do))) for step in page.steps("5")]
        found += [f"{rel}: {problem}" for problem in capture.skips(record, rows)[1]]
    if not isinstance(allow, list) or not all(isinstance(a, str) for a in allow):
        return found + [f"{rel}: `record.allow` must be a list of commands"]
    commands = {readonly.strip_watch_flags(c)[0] for step in page.steps("5") for c in catalogue.do_commands(step.do)}
    never = capture.never if capture is not None and allow else None
    for command in allow:
        if command not in commands:
            found.append(f"{rel}: `record.allow` names `{command}`, which is not a Do command of the 5-minute version")
        why = never(command) if never else ""
        if why:
            found.append(f"{rel}: `record.allow` names `{command}`, which is never typed ({why})")
    return found


def demo_problems(entry: catalogue.Entry, root: pathlib.Path) -> List[str]:
    page = catalogue.load(entry)
    rel_page = entry.path.relative_to(root).as_posix()
    problems = lifecycle_problems(page, rel_page)
    base = catalogue.demo_dir(entry.id, root)
    rel_dir = f"ansible/demos/{entry.id}"
    if not base.is_dir():
        return problems + [f"{rel_dir}/: missing (python3 platform/demo/scaffold.py --write --only {entry.id})"]
    manifest_path = base / "demo.yml"
    manifest: dict = {}
    if not manifest_path.is_file():
        problems.append(f"{rel_dir}/demo.yml: missing")
    else:
        try:
            manifest = load_yaml(manifest_path) or {}
        except yaml.YAMLError as exc:
            return problems + [f"{rel_dir}/demo.yml: {exc}"]
        if not isinstance(manifest, dict):
            return problems + [f"{rel_dir}/demo.yml: not a mapping"]
        if manifest.get("kind") != entry.kind:
            problems.append(f"{rel_dir}/demo.yml: kind {manifest.get('kind')!r}, the page is a {entry.kind}")
        if manifest.get("page") != rel_page:
            problems.append(f"{rel_dir}/demo.yml: page {manifest.get('page')!r}, expected {rel_page!r}")
        for action in (manifest.get("mutations") or {}):
            if action not in catalogue.LIFECYCLE_ACTIONS:
                problems.append(f"{rel_dir}/demo.yml: mutations names {action!r}, not an action")
        problems += record_problems(entry, page, manifest, root)
    times = {s.time: s for s in page.steps("15")}
    for key in (manifest.get("steps") or {}):
        if not isinstance(key, str):
            problems.append(f"{rel_dir}/demo.yml: steps key {key!r} is not a string: quote the time stamp "
                            f"(\"{guard.time_key(key)}\")")
        elif key not in times:
            problems.append(f"{rel_dir}/demo.yml: steps key {key!r} is not a timed row of the page")
    variables = {name: "x" for name in (manifest.get("env") or {})}
    changing_actions = set(manifest.get("mutations") or {})
    mutating_steps = set(guard.mutating_steps(manifest))
    for action in catalogue.LIFECYCLE_ACTIONS:
        path = base / f"{action}.yml"
        if not path.is_file():
            problems.append(f"{rel_dir}/{action}.yml: missing")
            continue
        try:
            tasks = load_yaml(path)
        except yaml.YAMLError as exc:
            problems.append(f"{rel_dir}/{action}.yml: {exc}")
            continue
        problems += unit_problems(f"{rel_dir}/{action}.yml", tasks, action in changing_actions, variables, entry.id)
    if entry.kind == "workshop":
        return problems + workshop_problems(entry, page, manifest, base, rel_dir, root)
    expected_files = {s.file_name: s for s in times.values()}
    steps_dir = base / "steps"
    present = {p.name for p in steps_dir.glob("*.yml")} if steps_dir.is_dir() else set()
    for name in sorted(set(expected_files) - present):
        problems.append(f"{rel_dir}/steps/{name}: missing (row {expected_files[name].time} of the page)")
    for name in sorted(present - set(expected_files)):
        problems.append(f"{rel_dir}/steps/{name}: no timed row of the page has this time")
    for name in sorted(present & set(expected_files)):
        step = expected_files[name]
        rel = f"{rel_dir}/steps/{name}"
        try:
            tasks = load_yaml(steps_dir / name)
        except yaml.YAMLError as exc:
            problems.append(f"{rel}: {exc}")
            continue
        problems += unit_problems(rel, tasks, step.time in mutating_steps, variables, entry.id)
        found = commands_of(tasks) if isinstance(tasks, list) else {"cmd": [], "page_text": [], "not_run": []}
        covered = {_norm(c) for c in found["cmd"] + found["page_text"] + found["not_run"]}
        for command in catalogue.do_commands(step.do):
            if _norm(command) not in covered:
                problems.append(f"{rel}: the Do command `{command}` is not covered (cmd, page_text or not_run)")
    return problems + probe_problems(rel_dir, base)


def probe_problems(rel_dir: str, base: pathlib.Path) -> List[str]:
    """The golden-path probes a check or start file queues: each one known to the script, and none without the
    probe it reads from (`trace` needs `unifai-tekos` in the same run, platform/demo/probe_order.py)."""
    problems = []
    known = probe_order.known()
    for action in ("check", "start"):
        queued, _ = rehearse.queued_checks([Unit(action, f"{action}.yml")], base)
        for name in queued:
            if name != probe_order.ALL and name not in known:
                problems.append(f"{rel_dir}/{action}.yml: queues the golden-path probe `{name}`, which "
                                "evaluations/golden_path_probe.py does not have")
        for name, need in probe_order.missing_needs(queued):
            problems.append(f"{rel_dir}/{action}.yml: queues the golden-path probe `{name}` without `{need}`, "
                            f"whose run it reads: queue `{need}` in the same file")
    return problems


def _normal_entry(entry) -> dict:
    if not isinstance(entry, dict):
        return {"invalid": repr(entry)}
    data = dict(entry)
    if "at" in data:
        data["at"] = guard.time_key(data["at"])
    if "version" in data:
        data["version"] = str(data["version"])
    if "only" in data:
        data["only"] = [guard.time_key(t) for t in data["only"] or []]
    return data


def workshop_problems(entry: catalogue.Entry, page: catalogue.Page, manifest: dict, base: pathlib.Path,
                      rel_dir: str, root: pathlib.Path) -> List[str]:
    """The agenda of the manifest against the page's Agenda table (ADR-0616 clause 10), and the workshop's own
    step files against its own and inline rows."""
    problems: List[str] = []
    rows = workshop.agenda_rows(page)
    entries = [_normal_entry(e) for e in manifest.get("agenda") or []]
    for raw in manifest.get("agenda") or []:
        if isinstance(raw, dict) and not isinstance(raw.get("at"), str):
            problems.append(f"{rel_dir}/demo.yml: agenda `at` {raw.get('at')!r} is not a string: quote the time stamp")
    expected = [row.entry() for row in rows]
    by_time = {e.get("at"): e for e in entries}
    for row in rows:
        have = by_time.get(row.at)
        if have is None:
            problems.append(f"{rel_dir}/demo.yml: the Agenda row {row.at} ({row.block}) has no agenda entry")
        elif have != row.entry():
            problems.append(f"{rel_dir}/demo.yml: agenda entry {row.at} is {have}, the page's row says {row.entry()}")
    for extra in [e for e in entries if e.get("at") not in {r.at for r in rows}]:
        problems.append(f"{rel_dir}/demo.yml: agenda entry {extra.get('at')} is not a row of the page's Agenda table")
    if [e.get("at") for e in entries] != [e["at"] for e in expected] and not problems:
        problems.append(f"{rel_dir}/demo.yml: the agenda entries are not in the page's order")
    for name in workshop.scenarios(manifest):
        if not catalogue.demo_dir(name, root).is_dir():
            problems.append(f"{rel_dir}/demo.yml: scenario {name} has no directory under ansible/demos/")
    try:
        workshop.expand(page, manifest, root)
    except (workshop.AgendaError, catalogue.ParseError) as exc:
        problems.append(f"{rel_dir}/demo.yml: {exc}")
    if workshop.scenarios(manifest):
        for action in workshop.DEFERRED_FLUSH:
            path = base / f"{action}.yml"
            if path.is_file() and "flush_checks.yml" not in path.read_text(encoding="utf-8"):
                problems.append(f"{rel_dir}/{action}.yml: a workshop's {action} must include _lib/flush_checks.yml "
                                "(its scenarios only queue their probes)")
    wanted = workshop.own_step_files(page)
    steps_dir = base / "steps"
    present = {f"steps/{p.name}" for p in steps_dir.glob("*.yml")} if steps_dir.is_dir() else set()
    for rel in sorted(set(wanted) - present):
        problems.append(f"{rel_dir}/{rel}: missing (agenda row {wanted[rel][0]} of the page)")
    for rel in sorted(present - set(wanted)):
        problems.append(f"{rel_dir}/{rel}: no own or inline agenda row of the page has this time")
    for rel in sorted(present & set(wanted)):
        step = wanted[rel][1]
        try:
            tasks = load_yaml(base / rel)
        except yaml.YAMLError as exc:
            problems.append(f"{rel_dir}/{rel}: {exc}")
            continue
        problems += unit_problems(f"{rel_dir}/{rel}", tasks, False, {}, entry.id)
        found = commands_of(tasks) if isinstance(tasks, list) else {"cmd": [], "page_text": [], "not_run": []}
        covered = {_norm(c) for c in found["cmd"] + found["page_text"] + found["not_run"]}
        for command in catalogue.do_commands(step.do):
            if _norm(command) not in covered:
                problems.append(f"{rel_dir}/{rel}: the Do command `{command}` is not covered (cmd, page_text or "
                                "not_run)")
    return problems


def docs_problems(root: pathlib.Path, verbs: Set[str], unmoved: Set[pathlib.Path]) -> List[str]:
    problems = []
    docs = root / "docs"
    for path in sorted(docs.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("docs/adr/", "docs/roadmap/")) or path.resolve() in unmoved:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for verb in DOC_VERB_RE.findall(line):
                if verb in verbs:
                    continue
                if verb in RETIRED_VERBS and RETIRED_WORDS.search(line):
                    continue
                problems.append(f"{rel}:{number}: `make demo {verb}` is not a verb of DEMO_VERBS")
    return problems


OBJECT_NAME_RE = re.compile(r"`([a-z0-9][a-z0-9.]*-[a-z0-9.-]*[a-z0-9])`")
# A page names a route by its full host; the file reads it portably, as `<name>.{{ cluster_base_domain }}`.
APPS_HOST_RE = re.compile(r"^([a-z0-9-]+)\.apps\.[a-z0-9.-]+$")


def _data_strings(node) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _data_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _data_strings(value)
    elif node is not None:
        yield str(node)


# --- the page shape of ADR-0617 (WP-285) --------------------------------------------------------------------------

# True since WP-285 moved every page (2026-11-15): every page needs the shape. False was the rollout mode, where a page
# without `## Page status` got one warning instead of its problems.
SHAPE_ENFORCED = True
PAGE_STATUS = "Page status"
REFERENCES = "References"
SCENARIO_ORDER = ["Introduction", "Personas", catalogue.LIFECYCLE_SECTION, "5-minute version", "15-minute version",
                  catalogue.IF_WRONG_SECTION, "Limits", "Appendix A - HLD", "Appendix B - LLD", REFERENCES, PAGE_STATUS]
WORKSHOP_HEAD = ["Introduction", "Personas", "Agenda", catalogue.LIFECYCLE_SECTION]
WORKSHOP_TAIL = [REFERENCES, PAGE_STATUS]
PRESENTER_SECTIONS = ("Introduction", "Personas", catalogue.LIFECYCLE_SECTION)
REFERENCE_RES = (
    (re.compile(r"\bADR-\d{4}\b"), "an ADR reference"),
    (re.compile(r"\bWP-\d{2,3}\b"), "a work-package reference"),
    (re.compile(r"\]\((?:[^)\s]*/)?(?:adr|roadmap)/[^)]*\)"), "a link into docs/adr/ or docs/roadmap/"),
)
BANNER_RE = re.compile(r"^>\s*\*\*Status:\*\*")
EMBED_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
GIF_RE = re.compile(r"(?:^|/)assets/img/demo/([a-z0-9-]+)\.gif$")


def gif_dir(root: pathlib.Path) -> pathlib.Path:
    return root / "docs" / "assets" / "img" / "demo"


def _fenced(lines: List[str]) -> List[bool]:
    """Per line: inside a fenced code block (the fence lines included)."""
    flags, inside = [], False
    for line in lines:
        fence = line.lstrip().startswith(("```", "~~~"))
        flags.append(inside or fence)
        if fence:
            inside = not inside
    return flags


def has_page_status(page: catalogue.Page) -> bool:
    return page.section(PAGE_STATUS) is not None


def shape_findings(entry: catalogue.Entry, page: catalogue.Page, root: pathlib.Path) -> List[str]:
    """What keeps a page from the ADR-0617 shape, one line each (`<page>:<line>: ...`). A page that has not moved to
    `## Presenter lifecycle` yet (ADR-0616) is not read."""
    if page.section(catalogue.LIFECYCLE_SECTION) is None:
        return []
    rel = entry.path.resolve().relative_to(root.resolve()) if root.resolve() in entry.path.resolve().parents \
        else entry.path
    found: List[str] = []
    titles = [s.title for s in page.sections if s.level == 2]
    if entry.kind == "scenario":
        if titles != SCENARIO_ORDER:
            found.append(f"{rel}:1: the `##` sections are {', '.join(titles)}; the contract is "
                         f"{', '.join(SCENARIO_ORDER)}")
    elif titles[:len(WORKSHOP_HEAD)] != WORKSHOP_HEAD or titles[-len(WORKSHOP_TAIL):] != WORKSHOP_TAIL:
        found.append(f"{rel}:1: a workshop's `##` sections start with {', '.join(WORKSHOP_HEAD)} and end with "
                     f"{', '.join(WORKSHOP_TAIL)}; they are {', '.join(titles)}")
    for title in PRESENTER_SECTIONS:
        section = page.section(title)
        if section is None:
            continue
        for k, (line, fenced) in enumerate(zip(section.lines, _fenced(section.lines))):
            if fenced:
                continue
            hits = [(what, pattern.search(line)) for pattern, what in REFERENCE_RES]
            hits = [(what, hit) for what, hit in hits if hit]
            if hits:
                kinds = " and ".join(what for what, _ in hits)
                found.append(f"{rel}:{section.line + 1 + k}: `## {title}` holds {kinds} ({hits[0][1].group(0)[:50]}): "
                             "it belongs in `## References`")
    lines = page.text.split("\n")
    status = page.section(PAGE_STATUS)
    inside = range(status.line, status.line + 1 + len(status.lines)) if status else range(0)
    for number, (line, fenced) in enumerate(zip(lines, _fenced(lines)), 1):
        if not fenced and BANNER_RE.match(line) and number not in inside:
            found.append(f"{rel}:{number}: the `> **Status:**` banner belongs under `## {PAGE_STATUS}`, the last "
                         "section")
    return found


def gif_problems(entries: List[catalogue.Entry], root: pathlib.Path, everything: bool) -> List[str]:
    """The published GIFs and their embeds (ADR-0617): pairing, owner, size. `everything`: also the orphan files."""
    found: List[str] = []
    directory = gif_dir(root)
    for entry in entries:
        page = catalogue.load(entry)
        rel = entry.path.resolve().relative_to(root.resolve()) if root.resolve() in entry.path.resolve().parents \
            else entry.path
        published = directory / f"{entry.id}.gif"
        lines = page.text.split("\n")
        own: List[int] = []
        for number, (line, fenced) in enumerate(zip(lines, _fenced(lines)), 1):
            if fenced:
                continue
            for target in EMBED_RE.findall(line):
                m = GIF_RE.search(target)
                if not m:
                    continue
                if m.group(1) != entry.id:
                    found.append(f"{rel}:{number}: embeds the GIF of another demo ({m.group(1)})")
                else:
                    own.append(number)
        intro = page.section("Introduction")
        body = [(intro.line + 1 + k, line) for k, line in enumerate(intro.lines)] if intro else []
        body = [(n, line) for n, line in body if line.strip()]
        last = body[-1] if body else None
        last_embeds = bool(last and any(GIF_RE.search(t) and GIF_RE.search(t).group(1) == entry.id
                                        for t in EMBED_RE.findall(last[1])))
        if published.is_file():
            if not last_embeds:
                found.append(f"{rel}: docs/assets/img/demo/{entry.id}.gif is published: embed it as the last line of "
                             "`## Introduction`")
            if published.stat().st_size > gif.MAX_BYTES:
                found.append(f"docs/assets/img/demo/{entry.id}.gif: {published.stat().st_size / 1048576:.1f} MB, over "
                             f"the {gif.MAX_BYTES // 1048576} MB limit")
            for number in own:
                if not (last_embeds and number == last[0]):
                    found.append(f"{rel}:{number}: the GIF is embedded once, as the last line of `## Introduction`")
        else:
            for number in own:
                found.append(f"{rel}:{number}: embeds docs/assets/img/demo/{entry.id}.gif, which is not published "
                             "(the owner's go comes first)")
    if everything and directory.is_dir():
        ids = {e.id for e in catalogue.discover(root)}
        for path in sorted(directory.iterdir()):
            if path.suffix != ".gif" or path.stem not in ids:
                found.append(f"docs/assets/img/demo/{path.name}: no catalogue demo has this GIF")
            elif path.stat().st_size > gif.MAX_BYTES and path.stem not in {e.id for e in entries}:
                found.append(f"docs/assets/img/demo/{path.name}: {path.stat().st_size / 1048576:.1f} MB, over the "
                             f"{gif.MAX_BYTES // 1048576} MB limit")
    return found


def shape_problems(entries: List[catalogue.Entry], root: pathlib.Path) -> List[str]:
    found: List[str] = []
    for entry in entries:
        page = catalogue.load(entry)
        if SHAPE_ENFORCED or has_page_status(page):
            found += shape_findings(entry, page, root)
    return found


def shape_warnings(entries: List[catalogue.Entry], root: pathlib.Path, detailed: bool) -> List[str]:
    """A page not moved to the ADR-0617 shape yet: one line, or all its findings when the run names it (--only). A
    published GIF whose demo has no cut list (no provenance)."""
    found: List[str] = []
    for entry in entries:
        page = catalogue.load(entry)
        if not SHAPE_ENFORCED and not has_page_status(page):
            findings = shape_findings(entry, page, root)
            if findings and detailed:
                found += [f"not moved yet: {f}" for f in findings]
            elif findings:
                rel = entry.path.resolve().relative_to(root.resolve()) \
                    if root.resolve() in entry.path.resolve().parents else entry.path
                found.append(f"{rel}: not in the ADR-0617 page shape yet ({len(findings)} finding(s); "
                             f"`python3 platform/demo/consistency.py --only {entry.id}` lists them)")
        if (gif_dir(root) / f"{entry.id}.gif").is_file() and not gif.cut_list_path(entry.id, root).is_file():
            found.append(f"docs/assets/img/demo/{entry.id}.gif: no ansible/demos/{entry.id}/gif.yml says how it was "
                         "cut")
    return found


def section_warnings(entry: catalogue.Entry, root: pathlib.Path) -> List[str]:
    """The backticked object names (Kubernetes-style, with a hyphen) of a moved page's `### Status` and `### Check`
    that appear in no value of its status.yml or check.yml: the page says the file reads them, the file does not."""
    page = catalogue.load(entry)
    if page.section(catalogue.LIFECYCLE_SECTION) is None:
        return []
    found = []
    for action in ("status", "check"):
        text, _ = page.lifecycle_text(action)
        path = catalogue.demo_dir(entry.id, root) / f"{action}.yml"
        if not text or not path.is_file():
            continue
        try:
            data = " ".join(_data_strings(load_yaml(path)))
            if entry.kind == "workshop":
                # A workshop's action chains its scenarios' files: what they read and probe counts as read.
                manifest = load_yaml(catalogue.demo_dir(entry.id, root) / "demo.yml") or {}
                for name in workshop.scenarios(manifest):
                    base = catalogue.demo_dir(name, root)
                    for part in (base / f"{action}.yml", base / "demo.yml"):
                        if part.is_file():
                            data += " " + " ".join(_data_strings(load_yaml(part)))
        except (yaml.YAMLError, OSError):
            continue
        for name in dict.fromkeys(OBJECT_NAME_RE.findall(text)):
            host = APPS_HOST_RE.match(name)
            if host and f"{host.group(1)}.{{{{ cluster_base_domain }}}}" in data:
                continue
            if name not in data:
                found.append(f"ansible/demos/{entry.id}/{action}.yml: the page's `### {action.capitalize()}` names "
                             f"`{name}`, which the file does not read")
    return found


def warnings(root: Optional[pathlib.Path] = None, only: Optional[List[str]] = None) -> List[str]:
    """Not failures: what a reviewer should look at (WP-275 to WP-279 review each demo against its page)."""
    root = root or catalogue.repo_root()
    found: List[str] = []
    for entry in catalogue.discover(root):
        if only and entry.id not in only:
            continue
        try:
            found += section_warnings(entry, root)
        except catalogue.ParseError:
            continue
    entries = [e for e in catalogue.discover(root) if not only or e.id in only]
    try:
        found += shape_warnings(entries, root, detailed=bool(only))
    except catalogue.ParseError:
        pass
    return found


def problems(root: Optional[pathlib.Path] = None, only: Optional[List[str]] = None, docs: bool = True) -> List[str]:
    root = root or catalogue.repo_root()
    entries = [e for e in catalogue.discover(root) if not only or e.id in only]
    found: List[str] = []
    unmoved: Set[pathlib.Path] = set()
    for entry in entries:
        try:
            found += demo_problems(entry, root)
        except catalogue.ParseError as exc:
            found.append(str(exc))
            continue
    for entry in catalogue.discover(root):
        if catalogue.load(entry).section(catalogue.LIFECYCLE_SECTION) is None:
            unmoved.add(entry.path.resolve())
    try:
        found += shape_problems(entries, root)
        found += gif_problems(entries, root, everything=not only)
    except catalogue.ParseError as exc:
        found.append(str(exc))
    if not only:
        ids = {e.id for e in catalogue.discover(root)}
        demos = root / "ansible" / "demos"
        for directory in sorted(demos.iterdir()) if demos.is_dir() else []:
            if directory.is_dir() and directory.name != "_lib" and directory.name not in ids:
                found.append(f"ansible/demos/{directory.name}/: no catalogue page has this id")
    if docs:
        found += docs_problems(root, demo_verbs(root), unmoved)
    return found


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check that the demo pages and ansible/demos/ agree (ADR-0616).")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args(argv)
    found = problems(only=args.only or None)
    for line in found:
        print(line)
    warned = warnings(only=args.only or None)
    for line in warned:
        print(f"warning: {line}")
    print(f"{len(found)} problem(s), {len(warned)} warning(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
