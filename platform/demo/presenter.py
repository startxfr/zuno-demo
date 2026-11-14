"""`make demo <verb>`: the presenter's command line (ADR-0616, WP-270).

    make demo                                   usage, the session in use, the freeze state
    make demo list                              the demos, their step counts, show-ready, last rehearsal
    make demo use <id> 5|15                     select a scenario and its version (a workshop takes no version)
    make demo status|check|install|start|stop|uninstall [<id>]
    make demo step next|<N>                     run step N's reads, then print its Do, Say and You should see
    make demo freeze on|off                     a freeze marker on this workstation
    make demo rehearse <id> 5|15                the whole sequence without pauses, with a report
    make demo golden-path|browser               the catalogue-wide checks (run by the Makefile, unchanged)

Each action and step runs its Ansible file (`ansible/demos/<id>/<action>.yml`, `steps/MM-SS.yml`) locally through
`ansible/playbooks/demo_run.yml`, prints its result, then the page section. Exit codes: 0 ok, 1 failed, 2 usage or
refused. Run from the repository root through make (ZUNO_REPO_ROOT); ZUNO_DEMO_ROOT points the catalogue elsewhere
(the test fixtures).
"""
from __future__ import annotations

import os
import pathlib
import sys
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import catalogue  # noqa: E402
import guard  # noqa: E402
import rehearse  # noqa: E402
import render  # noqa: E402
import session  # noqa: E402
from runner import Unit, UnitResult, run_units  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with Ansible
    yaml = None

VERBS = ("list", "use", "status", "check", "install", "start", "stop", "uninstall", "step", "freeze", "rehearse",
         "golden-path", "browser")
ACTIONS = catalogue.LIFECYCLE_ACTIONS
VERSIONS = ("5", "15")
QUIET_ACTIONS = ("status",)
WP280 = "Workshop agendas and their chained actions are composed by WP-280; until then play the scenarios one by one."

USAGE = """Zuno Demo - presenter lifecycle (ADR-0616)

Usage: make demo <verb> [arguments]

  list                       The demos, their step counts in each version, show-ready, last rehearsal
  use <id> 5|15              Select a scenario and its version for the commands below (a workshop takes no version)
  status [<id>]              Fast reads: is everything the demo needs installed and healthy
  check [<id>]               The demo's golden-path probes, its browser check and its own assertions
  install [<id>]             The demo's own add-on, if it has one; the shared platform is only verified
  start [<id>]               Prepare the session (warm-up, demo data)
  step next|<N>              Run the step's reads, then print its Do, Say and You should see
  stop [<id>]                Clean up what the session created
  uninstall [<id>]           Remove the demo's own add-on; never a shared component
  freeze on|off              Mark a freeze on this workstation: install, uninstall and rehearse refuse
  rehearse <id> 5|15         The whole sequence without pauses, with a report
  golden-path                One real call per demonstration moment (ADR-0605); ONLY=a,b limits the probes
  browser                    One browser check per experience (ADR-0606); ONLY=a,b limits the checks

A demo is played in the order status, check, install, start, step 1..N, stop, uninstall. An action that changes the
cluster shows what it will change and asks you to type the demo id (without a terminal: DEMO_CONFIRM=<id>).

Example: make demo use guardrails 15 && make demo status && make demo step next"""


class UsageError(Exception):
    pass


def out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def lines(items: List[str]) -> None:
    for item in items:
        out(item)


def load_manifest(demo_dir: pathlib.Path) -> dict:
    path = demo_dir / "demo.yml"
    if not path.is_file():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML is missing: install Ansible (it ships PyYAML) or `pip install pyyaml`")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} is not a mapping")
    return data


def resolve(demo_id: Optional[str]) -> catalogue.Entry:
    if demo_id is None:
        current = session.load_session()
        if not current:
            raise UsageError("No demo in use: run `make demo use <id> 5|15` first, or name the demo.")
        demo_id = current["demo"]
    try:
        return catalogue.find(demo_id)
    except KeyError:
        raise UsageError(f"Unknown demo id {demo_id!r}: `make demo list` shows the ids.")


def not_scaffolded(demo_id: str) -> str:
    return f"NOT SCAFFOLDED: ansible/demos/{demo_id}/ is missing (WP-271)"


def cluster_ready(manifest: dict) -> Optional[str]:
    """A refusal message when the demo needs the cluster and no kubeconfig exists, else None."""
    if manifest.get("cluster", True) is False:
        return None
    kubeconfig = os.environ.get("KUBECONFIG") or str(pathlib.Path.home() / ".kube" / "config")
    if any(pathlib.Path(p).is_file() for p in kubeconfig.split(os.pathsep) if p):
        return None
    return f"No kubeconfig found at {kubeconfig} - run 'oc login <cluster-api-url>' first (see 'make help')."


def session_line() -> str:
    current = session.load_session()
    freeze = session.load_freeze()
    if current:
        version = f" · {render.VERSION_LABEL.get(current.get('version'), 'workshop')}" if current.get("version") else ""
        text = f"Session: {current['demo']}{version} · step {current.get('position', 0)}/{current.get('total', 0)}"
    else:
        text = "Session: none (make demo use <id> 5|15)"
    text += f" · freeze {'ON since ' + str(freeze.get('when')) + ' (' + str(freeze.get('who')) + ')' if freeze else 'off'}"
    return text


# --- verbs -------------------------------------------------------------------------------------------------------

def cmd_usage() -> int:
    out(USAGE)
    out()
    out(session_line())
    return 0


def cmd_list(args: List[str]) -> int:
    if args:
        raise UsageError("Usage: make demo list")
    probes = catalogue.readme_probes()
    rows = []
    failed = False
    missing = 0
    for entry in catalogue.discover():
        try:
            page = catalogue.load(entry)
            k5 = str(len(page.steps("5"))) if entry.kind == "scenario" else "-"
            k15 = str(len(page.steps("15"))) if entry.kind == "scenario" else "-"
        except catalogue.ParseError as exc:
            failed = True
            k5 = k15 = "ERR"
            sys.stderr.write(f"{exc}\n")
        demo_dir = catalogue.demo_dir(entry.id)
        manifest = {}
        if demo_dir.is_dir():
            try:
                manifest = load_manifest(demo_dir)
            except (RuntimeError, yaml.YAMLError if yaml else RuntimeError) as exc:
                failed = True
                sys.stderr.write(f"{demo_dir}/demo.yml: {exc}\n")
        else:
            missing += 1
        ready = catalogue.show_ready(probes.get(entry.id, "")) if entry.kind == "scenario" else "-"
        addon = str(manifest.get("addon") or "-") if demo_dir.is_dir() else "-"
        last = []
        for version in (VERSIONS if entry.kind == "scenario" else ("w",)):
            found = rehearse.last_rehearsal(entry.id, version)
            if found:
                last.append(f"{version}: {found[1]} {found[0]}")
        rows.append([entry.id, entry.kind, entry.layer, k5, k15, ready, addon,
                     "yes" if demo_dir.is_dir() else "missing", ", ".join(last) or "-"])
    header = ["ID", "KIND", "LAYER", "5", "15", "SHOW-READY", "ADD-ON", "FILES", "LAST REHEARSAL"]
    widths = [max(len(r[i]) for r in rows + [header]) for i in range(len(header))]
    for row in [header] + rows:
        out("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    out()
    scenarios = sum(1 for r in rows if r[1] == "scenario")
    out(f"{len(rows)} demos: {scenarios} scenarios, {len(rows) - scenarios} workshops. "
        f"Steps: the 15-minute version includes the 5-minute steps.")
    if missing:
        out(f"{missing} without their directory under ansible/demos/ yet (WP-271).")
    return 1 if failed else 0


def cmd_use(args: List[str]) -> int:
    if not args or len(args) > 2:
        raise UsageError("Usage: make demo use <id> 5|15   (a workshop takes no version)")
    entry = resolve(args[0])
    page = catalogue.load(entry)
    if entry.kind == "workshop":
        if len(args) == 2:
            raise UsageError(f"{entry.id} is a workshop: it takes no version (make demo use {entry.id}).")
        session.save_session(entry.id, None, 0, 0)
        out(f"Using {entry.id} (workshop).")
        out(WP280)
        return 0
    if len(args) != 2 or args[1] not in VERSIONS:
        raise UsageError(f"Usage: make demo use {entry.id} 5|15")
    version = args[1]
    total = len(page.steps(version))
    session.save_session(entry.id, version, 0, total)
    out(f"Using {entry.id} · {render.VERSION_LABEL[version]} · {total} steps.")
    if not catalogue.demo_dir(entry.id).is_dir():
        out(not_scaffolded(entry.id))
    out("Next: make demo status, make demo check, make demo install, make demo start, then make demo step next.")
    return 0


def run_one(entry: catalogue.Entry, demo_dir: pathlib.Path, manifest: dict, unit: Unit, *,
            confirmed: str, stream: bool) -> UnitResult:
    refusal = cluster_ready(manifest)
    if refusal:
        raise guard.Refused(refusal)
    result = run_units(entry.id, demo_dir, [unit], confirmed=confirmed, stream=stream, label=unit.name)
    if result.error:
        return UnitResult(unit.name, "failed", error=result.error)
    found = result.unit(unit.name)
    if found is None:
        return UnitResult(unit.name, "failed", error=f"no result (see {result.log_path})")
    if found.failed and result.log_path:
        found.messages.append(f"Log: {result.log_path}")
    return found


def cmd_action(action: str, args: List[str]) -> int:
    if len(args) > 1:
        raise UsageError(f"Usage: make demo {action} [<id>]")
    entry = resolve(args[0] if args else None)
    page = catalogue.load(entry)
    out(f"{entry.id} · {action}")
    if action == "status":
        out(session_line())
    out()
    demo_dir = catalogue.demo_dir(entry.id)
    if entry.kind == "workshop":
        lines(["RESULT", f"  {WP280}", ""] + render.action_section(page, action))
        return 1
    if not demo_dir.is_dir():
        lines(["RESULT", f"  {not_scaffolded(entry.id)}", ""] + render.action_section(page, action))
        return 1
    manifest = load_manifest(demo_dir)
    guard.check_freeze(action)
    confirmed = guard.confirm(entry.id, guard.changing_units(manifest, [action]))
    rel = f"{action}.yml"
    if not (demo_dir / rel).is_file():
        lines(["RESULT", f"  MISSING: ansible/demos/{entry.id}/{rel} (WP-271)", ""] + render.action_section(page, action))
        return 1
    result = run_one(entry, demo_dir, manifest, Unit(action, rel), confirmed=confirmed,
                     stream=action not in QUIET_ACTIONS)
    lines(render.result_block(result))
    out()
    lines(render.action_section(page, action))
    if result.failed:
        out()
        lines(render.failure_rows(page))
        return 1
    return 0


def cmd_step(args: List[str]) -> int:
    if len(args) != 1:
        raise UsageError("Usage: make demo step next|<N>")
    current = session.load_session()
    if not current:
        raise UsageError("No demo in use: run `make demo use <id> 5|15` first.")
    entry = resolve(current["demo"])
    page = catalogue.load(entry)
    if entry.kind == "workshop":
        out(f"{entry.id} · workshop")
        out(WP280)
        return 1
    version = current.get("version")
    if version not in VERSIONS:
        raise UsageError(f"The session has no version: run `make demo use {entry.id} 5|15`.")
    steps = page.steps(version)
    if args[0] == "next":
        number = int(current.get("position") or 0) + 1
        if number > len(steps):
            out(f"{entry.id} · {render.VERSION_LABEL[version]}: all {len(steps)} steps played.")
            out("Last step done: make demo stop   (make demo step <N> replays one)")
            return 0
    elif args[0].isdigit() and 1 <= int(args[0]) <= len(steps):
        number = int(args[0])
    else:
        raise UsageError(f"Usage: make demo step next|<N>, N from 1 to {len(steps)}")
    step = steps[number - 1]
    session.save_session(entry.id, version, number, len(steps))
    out(render.step_header(page, version, step, len(steps)))
    out()
    demo_dir = catalogue.demo_dir(entry.id)
    failed = False
    result: Optional[UnitResult] = None
    note = ""
    if not demo_dir.is_dir():
        note, failed = not_scaffolded(entry.id), True
    else:
        manifest = load_manifest(demo_dir)
        meta = guard.step_meta(manifest, step.time)
        rel = f"steps/{step.file_name}"
        if meta.get("mutating"):
            note = "NOT RUN: this step changes the cluster. Do it by hand, as the Do cell says"
            note += " (optional)." if meta.get("optional") else "."
            if guard.forbidden_in_freeze(meta) and session.load_freeze():
                note += " FORBIDDEN during a freeze: skip it."
        elif not (demo_dir / rel).is_file():
            note, failed = f"MISSING: ansible/demos/{entry.id}/{rel} (WP-271)", True
        else:
            result = run_one(entry, demo_dir, manifest, Unit(step.time, rel, "step"), confirmed="", stream=False)
            failed = result.failed
    lines(render.result_block(result, note) if result else ["RESULT", f"  {note}"])
    out()
    lines(render.step_body(step))
    if failed and result is not None:
        out()
        lines(render.failure_rows(page, step.time))
    out()
    out(render.next_line(steps, step))
    return 1 if failed else 0


def cmd_freeze(args: List[str]) -> int:
    if not args:
        marker = session.load_freeze()
        out(f"Freeze: ON since {marker.get('when')} ({marker.get('who')})" if marker else "Freeze: off")
        return 0
    if len(args) != 1 or args[0] not in ("on", "off"):
        raise UsageError("Usage: make demo freeze on|off")
    if args[0] == "on":
        marker = session.freeze_on()
        out(f"Freeze ON ({marker['who']}, {marker['when']}): install, uninstall and rehearse refuse on this "
            "workstation. It is local: other workstations and sessions are told by the freeze protocol.")
    else:
        out("Freeze off." if session.freeze_off() else "Freeze was already off.")
    return 0


def cmd_rehearse(args: List[str]) -> int:
    if not args or len(args) > 2:
        raise UsageError("Usage: make demo rehearse <id> 5|15")
    entry = resolve(args[0])
    page = catalogue.load(entry)
    if entry.kind == "workshop":
        out(WP280)
        return 1
    if len(args) != 2 or args[1] not in VERSIONS:
        raise UsageError(f"Usage: make demo rehearse {entry.id} 5|15")
    version = args[1]
    guard.check_freeze("rehearse")
    demo_dir = catalogue.demo_dir(entry.id)
    if not demo_dir.is_dir():
        out(not_scaffolded(entry.id))
        return 1
    manifest = load_manifest(demo_dir)
    to_run, decided = rehearse.plan_units(page, version, demo_dir, manifest)
    confirmed = guard.confirm(entry.id, guard.changing_units(manifest, [u.name for u in to_run]))
    refusal = cluster_ready(manifest)
    if refusal and to_run:
        raise guard.Refused(refusal)
    out(f"Rehearsing {entry.id} · {render.VERSION_LABEL[version]}: {len(to_run)} units to run, "
        f"{sum(1 for d in decided if d.status == 'skipped')} skipped, {sum(1 for d in decided if d.failed)} missing.")
    run = run_units(entry.id, demo_dir, to_run, confirmed=confirmed, label=f"rehearse-{version}") if to_run else None
    results = rehearse.merge(page, version, run, decided)
    text, passed = rehearse.report(page, version, results, run)
    path = rehearse.write_report(page, version, text)
    out(text.rstrip("\n"))
    out(f"Report: {path}")
    return 0 if passed else 1


def complete(args: List[str]) -> int:
    """Words for bash completion: --complete <verb> [<word after the verb>]."""
    verb = args[0] if args else ""
    ids = [e.id for e in catalogue.discover()]
    if len(args) <= 1:
        if verb in ("use", "rehearse") + ACTIONS:
            out(" ".join(ids))
        elif verb == "step":
            current = session.load_session()
            total = int(current.get("total") or 0) if current else 0
            out(" ".join(["next"] + [str(n) for n in range(1, total + 1)]))
        elif verb == "freeze":
            out("on off")
        return 0
    if verb in ("use", "rehearse") and args[1] in ids:
        entry = catalogue.find(args[1])
        out("5 15" if entry.kind == "scenario" else "")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--ids"]:
        out("\n".join(e.id for e in catalogue.discover()))
        return 0
    if argv[:1] == ["--complete"]:
        return complete(argv[1:])
    if not argv:
        return cmd_usage()
    verb, args = argv[0], argv[1:]
    try:
        if verb == "list":
            return cmd_list(args)
        if verb == "use":
            return cmd_use(args)
        if verb in ACTIONS:
            return cmd_action(verb, args)
        if verb == "step":
            return cmd_step(args)
        if verb == "freeze":
            return cmd_freeze(args)
        if verb == "rehearse":
            return cmd_rehearse(args)
        if verb in ("golden-path", "browser"):
            raise UsageError(f"`{verb}` is run by the Makefile: make demo {verb}")
        raise UsageError(f"Unsupported demo verb: '{verb}' (expected one of: {' '.join(VERBS)})")
    except UsageError as exc:
        sys.stdout.flush()
        sys.stderr.write(f"{exc}\n")
        return 2
    except guard.Refused as exc:
        sys.stdout.flush()
        sys.stderr.write(f"REFUSED: {exc}\n")
        return 2
    except catalogue.ParseError as exc:
        sys.stdout.flush()
        sys.stderr.write(f"The page does not follow the ADR-0616 contract: {exc}\n")
        return 1
    except RuntimeError as exc:
        sys.stdout.flush()
        sys.stderr.write(f"{exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
