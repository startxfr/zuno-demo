"""`make demo <verb>`: the presenter's command line (ADR-0616, WP-270).

    make demo                                   usage, the session in use, the freeze state
    make demo list                              the demos, their step counts, show-ready, last rehearsal
    make demo use <id> 5|15                     select a scenario and its version (a workshop takes no version)
    make demo status|check|install|start|stop|uninstall [<id>]
    make demo step next|<N>                     run step N's reads, then print its Do, Say and You should see
    make demo freeze on|off                     a freeze marker on this workstation
    make demo rehearse <id> 5|15                the whole sequence without pauses, with a report
    make demo scout <id>                        sign in and open the walkthrough's menus, no prompt (ADR-0618)
    make demo record <id>                       record the 5-minute version in a browser, then cut its GIF (ADR-0617);
                                                a terminal demo: capture the session and check it as text (ADR-0618)
    make demo record <id> render                a terminal demo: film the checked session, then cut its GIF
    make demo gif <id>                          cut the newest recording again, offline
    make demo golden-path|browser               the catalogue-wide checks (run by the Makefile, unchanged)

Each action and step runs its Ansible file (`ansible/demos/<id>/<action>.yml`, `steps/MM-SS.yml`) locally through
`ansible/playbooks/demo_run.yml`, prints its result, then the page section. Exit codes: 0 ok, 1 failed, 2 usage or
refused. `scout`, `record` and `gif` write under ~/.cache/zuno/demo/recordings/ only, never in the repository. Run
from the repository root through make (ZUNO_REPO_ROOT); ZUNO_DEMO_ROOT points the catalogue elsewhere (the test
fixtures).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import catalogue  # noqa: E402
import gif  # noqa: E402
import guard  # noqa: E402
import rehearse  # noqa: E402
import render  # noqa: E402
import session  # noqa: E402
import textgate  # noqa: E402
import workshop  # noqa: E402
from runner import Unit, UnitResult, run_units  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with Ansible
    yaml = None

VERBS = ("list", "use", "status", "check", "install", "start", "stop", "uninstall", "step", "freeze", "rehearse",
         "scout", "record", "gif", "golden-path", "browser")
ACTIONS = catalogue.LIFECYCLE_ACTIONS
VERSIONS = ("5", "15")
QUIET_ACTIONS = ("status",)
NO_AGENDA = "This workshop has no agenda in its demo.yml yet: play its scenarios one by one."

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
  freeze on|off              Mark a freeze on this workstation: install, uninstall, rehearse, scout and record refuse
  rehearse <id> 5|15         The whole sequence without pauses, with a report (asks for the id when it runs probes)
  scout <id>                 Sign in as the walkthrough's persona and open its menus: no prompt, nothing created
  record <id>                Record the 5-minute version in a browser, then cut its GIF (needs a scout of the
                             walkthrough and a check that passed today)
  record <id> [render]       A terminal demo: capture the session and check it as text; `render` films the checked
                             session and cuts its GIF, after the transcript is read
  gif <id>                   Cut the newest recording again, offline (the GIF is published only on the owner's go)
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


def workshop_steps(entry: catalogue.Entry, page: catalogue.Page):
    """(flattened steps, manifest) of a workshop; ([], {}) while its directory or agenda is missing."""
    demo_dir = catalogue.demo_dir(entry.id)
    if not demo_dir.is_dir():
        return [], {}
    manifest = load_manifest(demo_dir)
    try:
        return workshop.expand(page, manifest), manifest
    except workshop.AgendaError as exc:
        raise RuntimeError(str(exc))


def print_units(results: List[UnitResult]) -> None:
    for result in results:
        out(f"[{result.name}]")
        lines(render.result_block(result)[1:])


def workshop_action(entry: catalogue.Entry, page: catalogue.Page, action: str) -> int:
    demo_dir = catalogue.demo_dir(entry.id)
    if not demo_dir.is_dir():
        lines(["RESULT", f"  {not_scaffolded(entry.id)}", ""] + render.action_section(page, action))
        return 1
    manifest = load_manifest(demo_dir)
    manifests = workshop.load_manifests(entry.id, manifest, load_manifest)
    units = workshop.action_units(entry.id, manifest, action)
    missing = [u for u in units if not (pathlib.Path(u.dir or demo_dir) / u.file).is_file()]
    guard.check_freeze(action)
    confirmed = guard.confirm(entry.id, workshop.changing(units, manifests))
    refusal = next((r for r in (cluster_ready(m) for m in manifests.values()) if r), None)
    if refusal:
        raise guard.Refused(refusal)
    runnable = [u for u in units if u not in missing]
    run = run_units(entry.id, demo_dir, runnable, confirmed=confirmed, stream=action not in QUIET_ACTIONS,
                    label=action)
    results = [UnitResult(u.name, "missing", error=f"{u.demo}/{u.file} is missing (WP-271)") for u in missing]
    results += run.units
    out("RESULT")
    if run.error:
        out(f"  {run.error}")
    print_units(results)
    out()
    lines(render.action_section(page, action))
    if run.error or any(r.failed for r in results):
        if run.log_path:
            out(f"Log: {run.log_path}")
        out()
        lines(render.failure_rows(page))
        return 1
    return 0


def workshop_step(entry: catalogue.Entry, page: catalogue.Page, arg: str, current: dict) -> int:
    flat, manifest = workshop_steps(entry, page)
    if not flat:
        out(f"{entry.id} · workshop")
        out(NO_AGENDA)
        return 1
    if arg == "next":
        number = int(current.get("position") or 0) + 1
        if number > len(flat):
            out(f"{entry.id} · workshop: all {len(flat)} steps played.")
            out("Last step done: make demo stop   (make demo step <N> replays one)")
            return 0
    elif arg.isdigit() and 1 <= int(arg) <= len(flat):
        number = int(arg)
    else:
        raise UsageError(f"Usage: make demo step next|<N>, N from 1 to {len(flat)}")
    item = flat[number - 1]
    session.save_session(entry.id, None, number, len(flat))
    out(render.workshop_step_header(page, item, len(flat)))
    out()
    owner_dir = catalogue.demo_dir(item.demo_id)
    owner = load_manifest(owner_dir) if owner_dir.is_dir() else {}
    meta = guard.step_meta(owner, item.step.time) if item.kind == "scenario" else {}
    failed = False
    result: Optional[UnitResult] = None
    note = ""
    if not owner_dir.is_dir():
        note, failed = not_scaffolded(item.demo_id), True
    elif meta.get("mutating"):
        note = "NOT RUN: this step changes the cluster. Do it by hand, as the Do cell says"
        note += " (optional)." if meta.get("optional") else "."
        if guard.forbidden_in_freeze(meta) and session.load_freeze():
            note += " FORBIDDEN during a freeze: skip it."
    elif not (owner_dir / item.file).is_file():
        note, failed = f"MISSING: ansible/demos/{item.demo_id}/{item.file}", True
    else:
        refusal = cluster_ready(owner)
        if refusal:
            raise guard.Refused(refusal)
        run = run_units(entry.id, catalogue.demo_dir(entry.id), [workshop.step_unit(item)], label=item.name)
        result = run.unit(item.name) or UnitResult(item.name, "failed", error=run.error or "no result")
        if result.failed and run.log_path:
            result.messages.append(f"Log: {run.log_path}")
        failed = result.failed
    lines(render.result_block(result, note) if result else ["RESULT", f"  {note}"])
    out()
    lines(render.step_body(item.step))
    if item.transition:
        out("Transition to the next block:")
        lines(render._wrap(render.inline(item.transition), "  ", "  "))
    if failed and result is not None:
        out()
        lines(render.failure_rows(page, item.step.time))
    out()
    out(render.workshop_next_line(flat, item))
    return 1 if failed else 0


def workshop_rehearse(entry: catalogue.Entry, page: catalogue.Page) -> int:
    guard.check_freeze("rehearse")
    demo_dir = catalogue.demo_dir(entry.id)
    if not demo_dir.is_dir():
        out(not_scaffolded(entry.id))
        return 1
    manifest = load_manifest(demo_dir)
    manifests = workshop.load_manifests(entry.id, manifest, load_manifest)
    try:
        to_run, decided, order = workshop.rehearsal(page, manifest, manifests)
    except workshop.AgendaError as exc:
        raise RuntimeError(str(exc))
    changing = workshop.changing(to_run, manifests)
    confirmed = guard.confirm(entry.id, changing,
                              notices=rehearse.check_notices(*rehearse.queued_checks(to_run, demo_dir)))
    refusal = next((r for r in (cluster_ready(m) for m in manifests.values()) if r), None)
    if refusal and to_run:
        raise guard.Refused(refusal)
    out(f"Rehearsing {entry.id} · workshop: {len(to_run)} units to run, "
        f"{sum(1 for d in decided if d.status == 'skipped')} skipped, {sum(1 for d in decided if d.failed)} missing.")
    run = run_units(entry.id, demo_dir, to_run, confirmed=confirmed, label="rehearse-w") if to_run else None
    results = rehearse.merge(page, "w", run, decided, names=order)
    text, passed = rehearse.report(page, "w", results, run, changing=changing, confirmed=confirmed)
    path = rehearse.write_report(page, "w", text)
    out(text.rstrip("\n"))
    out(f"Report: {path}")
    return 0 if passed else 1


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
        steps_all = "-"
        if entry.kind == "workshop" and manifest.get("agenda") and k5 != "ERR":
            try:
                steps_all = str(len(workshop.expand(page, manifest)))
            except (workshop.AgendaError, catalogue.ParseError) as exc:
                failed = True
                steps_all = "ERR"
                sys.stderr.write(f"{exc}\n")
        ready = catalogue.show_ready(probes.get(entry.id, "")) if entry.kind == "scenario" else "-"
        addon = str(manifest.get("addon") or "-") if demo_dir.is_dir() else "-"
        last = []
        for version in (VERSIONS if entry.kind == "scenario" else ("w",)):
            found = rehearse.last_rehearsal(entry.id, version)
            if found:
                last.append(f"{version}: {found[1]} {found[0]}")
        rows.append([entry.id, entry.kind, entry.layer, k5, k15, steps_all, ready, addon,
                     "yes" if demo_dir.is_dir() else "missing", ", ".join(last) or "-"])
    header = ["ID", "KIND", "LAYER", "5", "15", "ALL", "SHOW-READY", "ADD-ON", "FILES", "LAST REHEARSAL"]
    widths = [max(len(r[i]) for r in rows + [header]) for i in range(len(header))]
    for row in [header] + rows:
        out("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    out()
    scenarios = sum(1 for r in rows if r[1] == "scenario")
    out(f"{len(rows)} demos: {scenarios} scenarios, {len(rows) - scenarios} workshops. "
        f"Steps: the 15-minute version includes the 5-minute steps; ALL is a workshop's whole agenda.")
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
        flat, _ = workshop_steps(entry, page)
        session.save_session(entry.id, None, 0, len(flat))
        out(f"Using {entry.id} · workshop · {len(flat)} steps.")
        if not flat:
            out(NO_AGENDA)
        out("Next: make demo status, make demo check, make demo install, make demo start, then make demo step next.")
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
        return workshop_action(entry, page, action)
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
    if action == "check":
        session.record_check(entry.id, not result.failed)
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
        return workshop_step(entry, page, args[0], current)
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
        out(f"Freeze ON ({marker['who']}, {marker['when']}): install, uninstall, rehearse, scout and record refuse on "
            "this workstation. It is local: other workstations and sessions are told by the freeze protocol.")
    else:
        out("Freeze off." if session.freeze_off() else "Freeze was already off.")
    return 0


def cmd_rehearse(args: List[str]) -> int:
    if not args or len(args) > 2:
        raise UsageError("Usage: make demo rehearse <id> 5|15   (a workshop takes no version)")
    entry = resolve(args[0])
    page = catalogue.load(entry)
    if entry.kind == "workshop":
        if len(args) != 1:
            raise UsageError(f"{entry.id} is a workshop: it takes no version (make demo rehearse {entry.id}).")
        return workshop_rehearse(entry, page)
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
    changing = guard.changing_units(manifest, [u.name for u in to_run])
    confirmed = guard.confirm(entry.id, changing,
                              notices=rehearse.check_notices(*rehearse.queued_checks(to_run, demo_dir)))
    refusal = cluster_ready(manifest)
    if refusal and to_run:
        raise guard.Refused(refusal)
    out(f"Rehearsing {entry.id} · {render.VERSION_LABEL[version]}: {len(to_run)} units to run, "
        f"{sum(1 for d in decided if d.status == 'skipped')} skipped, {sum(1 for d in decided if d.failed)} missing.")
    run = run_units(entry.id, demo_dir, to_run, confirmed=confirmed, label=f"rehearse-{version}") if to_run else None
    results = rehearse.merge(page, version, run, decided)
    checked = next((r for r in results if r.name == "check" and r.status in ("ok", "failed")), None)
    if checked is not None:
        session.record_check(entry.id, not checked.failed, source=f"rehearse {version}")
    text, passed = rehearse.report(page, version, results, run, changing=changing, confirmed=confirmed)
    path = rehearse.write_report(page, version, text)
    out(text.rstrip("\n"))
    out(f"Report: {path}")
    return 0 if passed else 1


RECORDER = pathlib.Path("evaluations") / "browser" / "record.sh"
CAPTURE = pathlib.Path("evaluations") / "browser" / "terminal" / "capture.py"
TAKE_RE = re.compile(r"^\d{8}-\d{6}$")
SKIPPED_RE = re.compile(r"^(\S+)\s+not typed: (.+)$")   # capture.py --plan's line for a row of demo.yml record.skip
WALKTHROUGHS = pathlib.Path("evaluations") / "browser" / "walkthroughs"
WALKTHROUGH_HELPERS = ("_helpers.mjs",)        # hashed before the walkthrough, in this order (WP-286 contract)
RECORD_TIMEOUT = 1200


def walkthrough_sha256(demo_id: str, root: pathlib.Path) -> str:
    """The hash a scout records for the walkthrough it scouted (the recorder computes the same): SHA-256 over, for the
    helper files then `walkthroughs/<id>.mjs`, the path `evaluations/browser/walkthroughs/<name>`, a 0 byte, the file's
    bytes, a 0 byte."""
    digest = hashlib.sha256()
    for name in WALKTHROUGH_HELPERS + (f"{demo_id}.mjs",):
        digest.update(f"evaluations/browser/walkthroughs/{name}".encode("utf-8") + b"\0")
        digest.update((root / WALKTHROUGHS / name).read_bytes() + b"\0")
    return digest.hexdigest()


def latest_scout(demo_id: str) -> Optional[dict]:
    """The newest `recordings/<id>-<stamp>-scout/scout.json`, or None."""
    base = gif.recordings_dir()
    found = sorted(p for p in base.glob(f"{demo_id}-*-scout") if (p / "scout.json").is_file()
                   and p.name[len(demo_id) + 1:][:8].isdigit()) if base.is_dir() else []
    if not found:
        return None
    try:
        data = json.loads((found[-1] / "scout.json").read_text(encoding="utf-8"))
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    data["_dir"] = str(found[-1])
    return data


def scout_gate(demo_id: str, root: pathlib.Path) -> str:
    """The `changes` line of the guard notice, or raise Refused: a take needs a finished scout of the current
    walkthrough (ADR-0618 clause 9). RECORD_NO_SCOUT=<this exact id> skips the gate for the owner, loudly."""
    override = os.environ.get("RECORD_NO_SCOUT", "")
    if override:
        if override != demo_id:
            raise guard.Refused(f"RECORD_NO_SCOUT={override!r} does not name {demo_id!r}: it must hold this demo's "
                                "exact id.")
        out(f"SCOUT GATE SKIPPED by RECORD_NO_SCOUT={demo_id}: this take has no finished scout of its walkthrough.")
        return "controls the take may switch: unknown (no scout)"
    current = walkthrough_sha256(demo_id, root)
    scout = latest_scout(demo_id)
    how = (f"run `make demo scout {demo_id}` first, with the owner's go (it signs in and opens the menus: no prompt, "
           "no model call, nothing created)")
    if scout is None:
        raise guard.Refused(f"no scout of {demo_id} under {gif.recordings_dir()}: {how}.")
    if scout.get("status") != "done":
        raise guard.Refused(f"the newest scout ({scout['_dir']}) did not finish (status {scout.get('status')!r}: "
                            f"{scout.get('detail') or 'no detail'}): {how}.")
    if scout.get("walkthrough_sha256") != current:
        raise guard.Refused(f"the newest scout ({scout['_dir']}) is of another version of the walkthrough (the "
                            f"walkthrough or its helpers changed since): {how}.")
    changes = [str(c) for c in scout.get("changes") or []]
    return f"controls the take may switch: {', '.join(changes) if changes else 'none'}"


def scenario_for_gif(args: List[str], verb: str) -> catalogue.Entry:
    if len(args) > 1:
        raise UsageError(f"Usage: make demo {verb} [<id>]")
    entry = resolve(args[0] if args else None)
    if entry.kind != "scenario":
        raise UsageError(f"{entry.id} is a workshop: `{verb}` takes a scenario (its 5-minute version).")
    if not gif.cut_list_path(entry.id).is_file():
        raise UsageError(f"{entry.id} has no cut list (ansible/demos/{entry.id}/gif.yml): no GIF is planned for it yet "
                         "(ADR-0617).")
    return entry


def print_built(built: "gif.Built", demo_id: str) -> None:
    lines(built.summary())
    out()
    out(f"Nothing was copied into the repository. Send the GIF to the owner; it is published in "
        f"docs/assets/img/demo/{demo_id}.gif only after their \"go {demo_id}\" (ADR-0617). "
        f"`make demo gif {demo_id}` cuts this take again after a change of the cut list.")


def cmd_gif(args: List[str]) -> int:
    """Cut the newest recording again: offline, no guard, no cluster call."""
    entry = scenario_for_gif(args, "gif")
    directory = gif.latest_recording(entry.id)
    if directory is None:
        out(f"No recording of {entry.id} under {gif.recordings_dir()}: make demo record {entry.id}")
        return 1
    out(f"{entry.id} · gif · {directory}")
    try:
        built = gif.build(entry.id, directory, gif.load_cut_list(gif.cut_list_path(entry.id)),
                          times=gif.page_times(entry.id), cut_path=gif.cut_list_path(entry.id))
    except gif.CutError as exc:
        lines([f"REFUSED: {r}" for r in exc.reasons])
        return 1
    print_built(built, entry.id)
    return 0


def require_recorder(entry: catalogue.Entry, root: pathlib.Path) -> pathlib.Path:
    """The recorder script, once it and the demo's walkthrough exist; else Refused."""
    recorder = root / RECORDER
    walkthrough = root / WALKTHROUGHS / f"{entry.id}.mjs"
    for path in (recorder, walkthrough):
        if not path.is_file():
            shown = path.relative_to(root) if root in path.parents else path
            raise guard.Refused(f"{shown} is missing: {entry.id} cannot be recorded yet (WP-284).")
    return recorder


def walkthrough_persona(demo_id: str, root: pathlib.Path) -> str:
    """The persona the walkthrough signs in as (`export const persona = "..."`), for the guard notice."""
    try:
        text = (root / WALKTHROUGHS / f"{demo_id}.mjs").read_text(encoding="utf-8")
    except OSError:
        text = ""
    found = re.search(r"""export\s+const\s+persona\s*=\s*["']([^"']+)["']""", text)
    if found:
        return found.group(1)
    # Several takes, one per persona (`export const takes = [{ name, persona }, ...]`): all of them, in order.
    takes = re.search(r"export\s+const\s+takes\s*=\s*\[(.*?)\];", text, re.S)
    personas = re.findall(r"""persona:\s*["']([^"']+)["']""", takes.group(1)) if takes else []
    return " then as ".join(personas) if personas else "the walkthrough's persona"


def cmd_scout(args: List[str]) -> int:
    """Sign in as the walkthrough's persona and open the menus it uses, with no prompt (ADR-0618 clause 9): what
    `record` needs first, for the current version of the walkthrough. Local, never AAP."""
    entry = scenario_for_gif(args, "scout")
    root = catalogue.repo_root()
    if take_kind(load_manifest(catalogue.demo_dir(entry.id))) != "browser":
        raise UsageError(f"{entry.id} is a terminal demo: its take guesses no selector and needs no scout "
                         f"(make demo record {entry.id}).")
    guard.check_freeze("scout")
    recorder = require_recorder(entry, root)
    persona = walkthrough_persona(entry.id, root)
    manifest = load_manifest(catalogue.demo_dir(entry.id))
    confirmed = guard.confirm(entry.id, {}, notices=[
        f"a sign-in as {persona}, then the menus the walkthrough uses: no prompt sent, no model call, nothing created"])
    refusal = cluster_ready(manifest)
    if refusal:
        raise guard.Refused(refusal)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = gif.recordings_dir() / f"{entry.id}-{stamp}-scout"
    directory.mkdir(parents=True, mode=0o700)
    log_path = session.logs_dir() / f"{entry.id}-scout-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out(f"{entry.id} · scout ({confirmed}) · {directory}")
    rc = run_recorder([str(recorder), entry.id, str(directory), "--scout"], root, log_path)
    try:
        report = json.loads((directory / "scout.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    report = report if isinstance(report, dict) else {}
    out("RESULT")
    for step in report.get("steps") or []:
        if not isinstance(step, dict):
            continue
        what = step.get("error") or step.get("selector") or step.get("png") or ""
        out(f"  {'ok    ' if step.get('ok') else 'FAILED'} {step.get('step')}  {str(what)[:100]}")
    status = report.get("status") or "no scout.json"
    out(f"  scout {status}: {report.get('detail') or '-'} (exit {rc}). Log: {log_path}")
    if rc == 0 and status == "done":
        changes = [str(c) for c in report.get("changes") or []]
        out(f"Controls the take may switch: {', '.join(changes) if changes else 'none'}. "
            f"Next: make demo record {entry.id}")
        return 0
    return 2 if rc == 2 else 1


def record_size(manifest: dict) -> str:
    """The terminal size of a terminal take, `<cols>x<rows>` (demo.yml record.cols/rows; the capture's default
    100x30)."""
    record = manifest.get("record") if isinstance(manifest.get("record"), dict) else {}
    return f"{record.get('cols') or 100}x{record.get('rows') or 30}"


def take_kind(manifest: dict) -> str:
    """demo.yml `record.kind`: browser (a walkthrough) or terminal (a captured session); browser when absent."""
    record = manifest.get("record") if isinstance(manifest.get("record"), dict) else {}
    return str(record.get("kind") or "browser")


def require_check_today(demo_id: str) -> None:
    if not session.check_passed_today(demo_id):
        last = session.last_check(demo_id)
        seen = (f"the last one {'passed' if last.get('passed') else 'FAILED'} on {last.get('date')} "
                f"({last.get('source')})") if last else "none is recorded on this workstation"
        raise guard.Refused(f"`record` needs a `make demo check {demo_id}` that passed today: {seen}. Then "
                            f"`make demo start {demo_id}` warms the model before the take.")


def latest_terminal_take(demo_id: str) -> Optional[pathlib.Path]:
    """The newest `recordings/<id>-<YYYYmmdd-HHMMSS>/` holding a terminal.cast, or None."""
    base = gif.recordings_dir()
    if not base.is_dir():
        return None
    found = [p for p in base.glob(f"{demo_id}-*") if p.is_dir() and TAKE_RE.match(p.name[len(demo_id) + 1:])
             and (p / textgate.CAST).is_file()]
    return sorted(found)[-1] if found else None


def capture_plan(demo_id: str, root: pathlib.Path) -> List[str]:
    """What the capture would type (`<time>  $ <cmd>` lines), or Refused with its reasons. Runs nothing."""
    done = subprocess.run([sys.executable, str(root / CAPTURE), demo_id, "--plan"], cwd=str(root),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
    lines_out = [line for line in done.stdout.split("\n") if line.strip()]
    if done.returncode == 2:
        raise guard.Refused(done.stderr.strip() or f"the capture cannot plan {demo_id}")
    if done.returncode != 0:
        failed = next((line for line in reversed(lines_out) if line.startswith("CAPTURE: failed")), "")
        raise guard.Refused(f"the take may not type every Do command of {demo_id}: "
                            f"{failed[len('CAPTURE: failed '):] or done.stderr.strip()}. A command outside the "
                            "read-only allowlist is typed only when demo.yml lists it under `record: {allow: [...]}`.")
    return [line for line in lines_out if not line.startswith("CAPTURE:")]


def record_terminal(entry: catalogue.Entry, root: pathlib.Path, manifest: dict) -> int:
    """A terminal take, first call: capture the real session, then the text gate. Nothing is rendered before the
    recording session has read the transcript (ADR-0618 clause 5): `make demo record <id> render` films it."""
    guard.check_freeze("record")
    for path in (root / CAPTURE, root / RECORDER):
        if not path.is_file():
            raise guard.Refused(f"{path.relative_to(root) if root in path.parents else path} is missing: "
                                f"{entry.id} cannot be recorded yet (WP-287).")
    require_check_today(entry.id)
    plan = capture_plan(entry.id, root)
    allow = [str(c) for c in (manifest.get("record") or {}).get("allow") or []]
    cut = gif.load_cut_list(gif.cut_list_path(entry.id))
    notices = [str(cut.get("record_notice") or "a real terminal session on the cluster with your `oc` login: the "
                   "5-minute rows typed as the page says"), "the session is checked as text before anything is filmed",
               f"a terminal of {record_size(manifest)}"]
    for line in plan:
        skipped = SKIPPED_RE.match(line)    # demo.yml record.skip: a row the take leaves out, and why
        notices.append(f"not typed, not filmed: {skipped.group(1)} ({skipped.group(2)})" if skipped
                       else f"typed: {line}")
    notices.append(f"typed beyond the read-only allowlist (demo.yml record.allow): "
                   f"{', '.join(allow) if allow else 'none'}")
    confirmed = guard.confirm(entry.id, {}, notices=notices)
    refusal = cluster_ready(manifest)
    if refusal:
        raise guard.Refused(refusal)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = gif.recordings_dir() / f"{entry.id}-{stamp}"
    directory.mkdir(parents=True, mode=0o700)
    log_path = session.logs_dir() / f"{entry.id}-capture-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out(f"{entry.id} · record, terminal capture ({confirmed}) · {directory}")
    rc = run_recorder([sys.executable, str(root / CAPTURE), entry.id, str(directory)], root, log_path)
    if rc == 2:
        out(f"RESULT: the capture could not start (exit 2). Log: {log_path}")
        return 2
    if not (directory / textgate.CAST).is_file():
        out("RESULT: REFUSED by the capture: the session printed a real local value (the token, the kubeconfig path, "
            f"the home directory, the login or host name), so no cast was written. Log: {log_path}")
        return 1
    try:
        record = textgate.gate(directory)
    except textgate.GateError as exc:
        out(f"RESULT: {exc}")
        return 1
    out("RESULT")
    for hit in record["hits"]:
        out(f"  HIT {textgate.TRANSCRIPT}:{hit['line']}: {hit['detector']}")
    if record["status"] != "pass":
        out(f"  REFUSED by the text gate: {len(record['hits'])} hit(s). The cast is never edited: fix the cause, then "
            f"record again. Transcript: {directory / textgate.TRANSCRIPT}")
        return 1
    if record.get("steps_status") != "done":
        out(f"  The capture did not finish (status {record.get('steps_status')!r}, exit {rc}): read "
            f"{directory / textgate.TRANSCRIPT} and {directory / textgate.STEPS}. Log: {log_path}")
        return 1
    out(f"  Text gate passed, {record['lines']} lines. Read the transcript before anything is filmed (ADR-0618 "
        f"clause 5): {directory / textgate.TRANSCRIPT}")
    out(f"  If it shows nothing private: make demo record {entry.id} render")
    return 0


def render_terminal(entry: catalogue.Entry, root: pathlib.Path) -> int:
    """A terminal take, second call: film the checked session (offline: the replay has no network), then cut."""
    directory = latest_terminal_take(entry.id)
    if directory is None:
        raise guard.Refused(f"no captured session of {entry.id}: run `make demo record {entry.id}` first.")
    ok, why = textgate.passed(directory)
    if not ok:
        raise guard.Refused(f"{directory}: {why}. Record again with `make demo record {entry.id}`.")
    if (directory / "recording.webm").exists():
        raise guard.Refused(f"{directory} is already filmed: `make demo gif {entry.id}` cuts it again.")
    recorder = root / RECORDER
    if not recorder.is_file():
        raise guard.Refused(f"{RECORDER} is missing (WP-287).")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = session.logs_dir() / f"{entry.id}-render-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out(f"{entry.id} · record render · {directory}")
    rc = run_recorder([str(recorder), entry.id, str(directory), "--terminal"], root, log_path)
    if rc != 0:
        out(f"RESULT: the replay failed (exit {rc}). Log: {log_path}")
        return 2 if rc == 2 else 1
    try:
        built = gif.build(entry.id, directory, gif.load_cut_list(gif.cut_list_path(entry.id)),
                          times=gif.page_times(entry.id), cut_path=gif.cut_list_path(entry.id))
    except gif.CutError as exc:
        lines([f"REFUSED: {r}" for r in exc.reasons])
        out(f"The take is kept in {directory}: fix the cut list, then make demo gif {entry.id}")
        return 1
    print_built(built, entry.id)
    return 0


def cmd_record(args: List[str]) -> int:
    """Record the 5-minute version through the demo's walkthrough, then cut the GIF; a terminal demo is captured and
    checked as text first, then filmed by `record <id> render`. Local, never AAP."""
    render_call = bool(args) and args[-1] == "render"
    if render_call:
        args = args[:-1]
    entry = scenario_for_gif(args, "record")
    root = catalogue.repo_root()
    manifest = load_manifest(catalogue.demo_dir(entry.id))
    kind = take_kind(manifest)
    if kind == "terminal":
        return render_terminal(entry, root) if render_call else record_terminal(entry, root, manifest)
    if render_call:
        raise UsageError(f"`render` is the second call of a terminal take; {entry.id} is recorded in a browser: "
                         f"make demo record {entry.id}")
    guard.check_freeze("record")
    recorder = require_recorder(entry, root)
    require_check_today(entry.id)
    changes = scout_gate(entry.id, root)
    demo_dir = catalogue.demo_dir(entry.id)
    manifest = load_manifest(demo_dir)
    cut = gif.load_cut_list(gif.cut_list_path(entry.id))
    notice = str(cut.get("record_notice") or "a recorded browser session that calls the models")
    confirmed = guard.confirm(entry.id, {}, notices=[notice, changes])
    refusal = cluster_ready(manifest)
    if refusal:
        raise guard.Refused(refusal)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = gif.recordings_dir() / f"{entry.id}-{stamp}"
    directory.mkdir(parents=True, mode=0o700)
    log_path = session.logs_dir() / f"{entry.id}-record-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    out(f"{entry.id} · record ({confirmed}) · {directory}")
    rc = run_recorder([str(recorder), entry.id, str(directory)], root, log_path)
    if rc != 0:
        out(f"RESULT: the recording failed (exit {rc}). Log: {log_path}")
        out(f"Files so far: {directory}")
        return 1 if rc != 2 else 2
    try:
        built = gif.build(entry.id, directory, cut, times=gif.page_times(entry.id),
                          cut_path=gif.cut_list_path(entry.id))
    except gif.CutError as exc:
        lines([f"REFUSED: {r}" for r in exc.reasons])
        out(f"The take is kept in {directory}: fix the cut list, then make demo gif {entry.id}")
        return 1
    print_built(built, entry.id)
    return 0


def run_recorder(argv: List[str], root: pathlib.Path, log_path: pathlib.Path) -> int:
    """Run record.sh, its output on the terminal and in the log."""
    with open(log_path, "w", encoding="utf-8") as log:
        log.write("$ " + " ".join(argv) + "\n")
        try:
            proc = subprocess.Popen(argv, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, bufsize=1)
        except OSError as exc:
            log.write(f"{exc}\n")
            out(f"Cannot run the recorder: {exc}")
            return 2
        assert proc.stdout is not None
        with proc.stdout:
            for line in proc.stdout:
                log.write(line)
                sys.stdout.write(line)
                sys.stdout.flush()
        try:
            return proc.wait(timeout=RECORD_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            out(f"The recorder ran over {RECORD_TIMEOUT} s and was stopped.")
            return 1


def complete(args: List[str]) -> int:
    """Words for bash completion: --complete <verb> [<word after the verb>]."""
    verb = args[0] if args else ""
    ids = [e.id for e in catalogue.discover()]
    if len(args) <= 1:
        if verb in ("use", "rehearse") + ACTIONS:
            out(" ".join(ids))
        elif verb in ("scout", "record", "gif"):
            with_cut = [e.id for e in catalogue.discover() if gif.cut_list_path(e.id).is_file()]
            if verb == "scout":         # a terminal take is not scouted: it guesses no selector
                with_cut = [i for i in with_cut if take_kind(load_manifest(catalogue.demo_dir(i))) == "browser"]
            out(" ".join(with_cut))
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
        if verb == "scout":
            return cmd_scout(args)
        if verb == "record":
            return cmd_record(args)
        if verb == "gif":
            return cmd_gif(args)
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
