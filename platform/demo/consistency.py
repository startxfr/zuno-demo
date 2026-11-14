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
- a page that has moved has `## Presenter lifecycle` with exactly `### Status` ... `### Uninstall`, none empty;
- every backticked `make demo <verb>` under docs/ is a verb of DEMO_VERBS (the Makefile).
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
import guard  # noqa: E402
import readonly  # noqa: E402

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
        return problems
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
        except yaml.YAMLError:
            continue
        for name in dict.fromkeys(OBJECT_NAME_RE.findall(text)):
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
