#!/usr/bin/env python3
"""Capture a terminal demo as a real session: its bytes and its timing (ADR-0618 clauses 3, 4, 7 and 8, WP-287).

A real bash in a real pty, on the presenter's workstation, with the presenter's `oc` session. The driver types the
Do commands of the page's 5-minute rows, verbatim, at a human pace, presses Enter and waits for the prompt. What the
terminal printed is written as an asciicast v2 file (one JSON line per chunk of output, with its instant), and the
instant each step was typed and the instant its prompt came back are written beside it. Nothing is retyped from the
engine's results and the stream is never edited: `evaluations/browser/record.mjs` later replays these bytes in a
terminal emulator and films that.

    python3 evaluations/browser/terminal/capture.py <id> <out_dir>
    python3 evaluations/browser/terminal/capture.py <id> --plan     what would be typed, `<time>  $ <cmd>` per line, and
                                                                    the refusals; nothing runs

Writes in <out_dir>:
    terminal.cast         asciicast v2, 100x30 (only when the session printed none of the local values below)
    terminal-steps.json   {demo, cols, rows, started, steps: [{time, typed, done, commands: [{cmd, typed, done, rc}]}],
                          status "done"|"fail", detail}
Last line `CAPTURE: done` (exit 0) or `CAPTURE: failed <detail>` (exit 1); 2 is a usage or environment error.

What may be typed (clause 7). Before the shell starts, every Do command of every row must be acceptable, or the take
fails naming the command and nothing is typed at all:
- a command `platform/demo/readonly.py` accepts (the read-only allowlist of `make demo step`); a watch flag is removed
  as the engine removes it, so the read runs once;
- or a command the demo lists in `ansible/demos/<id>/demo.yml` under `record: {allow: [...]}`;
- never `oc whoami -t`, `oc config view`, `env`/`printenv`/`set`, or a read of a kubeconfig, whatever the list says.
  `$(oc whoami -t)` inside a command stays runnable: bash substitutes it and never echoes its value.
A row listed in demo.yml `record: {skip: {"<M:SS>": "<why>"}}` is not typed at all, so it is not in the take and
not in the GIF (a `make` row that prints the checkout's path, say); `--plan` prints it as `<time>  not typed: <why>`.

The shell (clause 8): `env -i` with only PATH, TERM, LC_ALL=C.UTF-8, KUBECONFIG (by path, never typed) and
PYTHONUSERBASE, the step variables of the demo (`env:` of demo.yml), HOME an empty temporary directory,
`bash --noprofile --norc`, a window of 100x30 unless demo.yml says `record: {cols, rows}` (80 to 140 columns, 20 to
40 rows: a demo whose tables are wider than 100 columns asks for more, its commands stay the page's), the prompt `$ `, no history (switched off, and HISTFILE=/dev/null), the repository root as the working directory.
The prompt also carries one invisible sequence (an OSC the terminal ignores) holding the exit code of the last command:
that is how the driver knows the prompt is back, and with which result.

The local values (clause 4, the part that cannot leave this process): the presenter's token (read here with
`oc whoami -t`, outside the pty, never written), the kubeconfig path, the home directory, the workstation host name,
the login name (as a whole word) and the values of the step variables whose name looks like a credential. When the
session printed one of them, the cast is NOT written and the take fails saying which kind. The pattern checks
(bearer tokens, JWTs...) and the transcript are the gate's, on the written cast (platform/demo, WP-287).
"""
from __future__ import annotations

import argparse
import codecs
import datetime
import errno
import fcntl
import getpass
import json
import os
import pathlib
import pty
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[3]
COLS, ROWS = 100, 30                             # the default window
COLS_RANGE, ROWS_RANGE = (80, 140), (20, 40)     # what demo.yml `record: {cols, rows}` may ask for
KEY_DELAY = 0.045          # seconds between two keys: a person typing steadily
AFTER_TYPED = 0.6          # the typed line stays readable before Enter
BETWEEN_COMMANDS = 0.8
COMMAND_TIMEOUT = 600.0
RC_MARK = re.compile(r"\x1b\]1337;rc=(\d+)\x07\$ $")
PS1 = r"\[\e]1337;rc=$?\a\]$ "
TOKEN_EXPR = "$(oc whoami -t)"
SKIPPED = "not typed:"     # a `--plan` line of a row demo.yml `record.skip` leaves out: `<time>  not typed: <why>`
# Never typed, whatever a demo allows (clause 7). Checked on the command with `$(oc whoami -t)` taken out.
NEVER = [
    (re.compile(r"\boc\b[^|;&]*\bwhoami\b[^|;&]*(?:\s-t\b|--show-token)"), "`oc whoami -t` prints the presenter's token"),
    (re.compile(r"\b(?:oc|kubectl)\b[^|;&]*\bconfig\b[^|;&]*\b(?:view|get-users|get-clusters|get-contexts)\b"), "`oc config view` prints the kubeconfig"),
    (re.compile(r"(?:^|[|;&(]\s*)(?:env|printenv|set|export|declare|typeset|compgen)\b"), "`env` prints the shell's variables"),
    (re.compile(r"kubeconfig|\.kube/|\$\{?KUBECONFIG\b", re.I), "a read of a kubeconfig"),
    (re.compile(r"\$\{?(?:HOME|PATH|PYTHONUSERBASE)\b"), "a local path variable would be printed"),
]
CREDENTIAL_NAME = re.compile(r"KEY|TOKEN|PASSWORD|SECRET", re.I)


class NoDomain(RuntimeError):
    """The demo's variables need the cluster domain and it could not be read."""


class Refused(Exception):
    """A command may not be typed, or the session printed a local value."""


@dataclass
class Command:
    cmd: str
    typed: float = 0.0
    done: float = 0.0
    rc: Optional[int] = None


@dataclass
class Step:
    time: str
    commands: List[Command] = field(default_factory=list)


def never(command: str) -> str:
    """Why this command is never typed, or ""."""
    bare = command.replace(TOKEN_EXPR, "")
    for pattern, why in NEVER:
        if pattern.search(bare):
            return why
    return ""


def acceptable(command: str, allow: List[str], check: Callable[[str], Tuple[bool, str]]) -> Tuple[str, str]:
    """(the command to type, "") or ("", why it may not be typed)."""
    why = never(command)
    if why:
        return "", f"never typed: {why}"
    ok, reason = check(command)
    if ok:
        return command, ""
    if command in allow:
        return command, ""
    return "", f"refused by the read-only allowlist ({reason}) and not in demo.yml `record: {{allow: [...]}}`"


def clean_env(kubeconfig: str, variables: Dict[str, str], home: str) -> Dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "TERM": "xterm-256color", "LC_ALL": "C.UTF-8",
           "HOME": home, "PS1": PS1, "PS2": "> ", "INPUTRC": "/dev/null", "HISTFILE": "/dev/null"}
    if kubeconfig:
        env["KUBECONFIG"] = kubeconfig
    base = subprocess.run([sys.executable, "-c", "import site; print(site.getuserbase())"], stdout=subprocess.PIPE,
                          universal_newlines=True).stdout.strip()
    if base:
        env["PYTHONUSERBASE"] = base    # computed with the real HOME: `make` rows need the user-site Ansible
    for name, value in variables.items():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) and name not in env:
            env[name] = value
    return env


class Session:
    """A bash in a pty; everything it prints is kept with its instant."""

    def __init__(self, env: Dict[str, str], cwd: pathlib.Path, cols: int = COLS, rows: int = ROWS) -> None:
        self.events: List[Tuple[float, str]] = []
        self.text = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.pid, self.fd = pty.fork()
        if self.pid == 0:   # the shell
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                os.chdir(str(cwd))
                os.execve("/bin/bash", ["bash", "--noprofile", "--norc", "+o", "history", "-i"], env)
            finally:
                os._exit(127)
        self.t0 = time.monotonic()

    def now(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def pump(self, seconds: float) -> None:
        """Read what the terminal prints for this long."""
        end = time.monotonic() + seconds
        while True:
            left = end - time.monotonic()
            ready, _, _ = select.select([self.fd], [], [], max(left, 0))
            if ready:
                try:
                    data = os.read(self.fd, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        return
                    raise
                if not data:
                    return
                chunk = self._decoder.decode(data)
                if chunk:
                    self.events.append((self.now(), chunk))
                    self.text += chunk
            if left <= 0:
                return

    def wait_prompt(self, timeout: float) -> int:
        """Wait until the prompt is back; its invisible mark gives the exit code of the last command."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump(0.05)
            found = RC_MARK.search(self.text[-80:])
            if found:
                return int(found.group(1))
        raise TimeoutError

    def keys(self, text: str, delay: float = KEY_DELAY) -> None:
        for char in text:
            os.write(self.fd, char.encode("utf-8"))
            self.pump(delay)

    def close(self) -> None:
        try:
            os.kill(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass


def play(steps: List[Step], env: Dict[str, str], cwd: pathlib.Path, timeout: float = COMMAND_TIMEOUT,
         key_delay: float = KEY_DELAY, clear: bool = True, cols: int = COLS, rows: int = ROWS) -> Tuple[List[Tuple[float, str]], str]:
    """Type every command of every step in one session. Returns (events, why it stopped or "")."""
    session = Session(env, cwd, cols, rows)
    try:
        try:
            session.wait_prompt(20)
        except TimeoutError:
            return session.events, "the shell gave no prompt"
        session.pump(0.8)
        for number, step in enumerate(steps):
            if number and clear:
                os.write(session.fd, b"\x0c")   # Ctrl-L, as a presenter clears the screen between two rows
                session.pump(0.5)
            for command in step.commands:
                session.keys(command.cmd, key_delay)
                command.typed = session.now()
                session.pump(AFTER_TYPED)
                # The previous prompt's mark is before this point: only a prompt printed after Enter ends the wait.
                mark_from = len(session.text)
                os.write(session.fd, b"\r")
                end = time.monotonic() + timeout
                rc = None
                while time.monotonic() < end:
                    session.pump(0.05)
                    found = RC_MARK.search(session.text[max(mark_from, len(session.text) - 80):])
                    if found:
                        rc = int(found.group(1))
                        break
                if rc is None:
                    os.write(session.fd, b"\x03")
                    session.pump(0.5)
                    return session.events, f"`{command.cmd}` (row {step.time}) did not finish within {int(timeout)} s"
                command.done = session.now()
                command.rc = rc
                session.pump(BETWEEN_COMMANDS)
        session.pump(1.0)
        return session.events, ""
    finally:
        session.close()


def local_values(kubeconfig: str, variables: Dict[str, str], token: str) -> List[Tuple[str, str, bool]]:
    """(kind, value, whole word only) for every local value the session must not have printed."""
    values = [("the presenter's token", token, False), ("the kubeconfig path", kubeconfig, False),
              ("the home directory", os.path.expanduser("~"), False), ("the workstation's host name", socket.gethostname(), True),
              ("the login name", getpass.getuser(), True)]
    for name, value in variables.items():
        if CREDENTIAL_NAME.search(name):
            values.append((f"the value of ${name}", value, False))
    return [(kind, value, word) for kind, value, word in values if value and len(value) >= 2]


def printed(text: str, values: List[Tuple[str, str, bool]]) -> List[str]:
    """The kinds of local values found in what the session printed."""
    found = []
    for kind, value, word in values:
        pattern = (r"(?<![A-Za-z0-9_.-])" + re.escape(value) + r"(?![A-Za-z0-9_.-])") if word else re.escape(value)
        if re.search(pattern, text) and kind not in found:
            found.append(kind)
    return found


def write_cast(path: pathlib.Path, events: List[Tuple[float, str]], started: float, cols: int = COLS, rows: int = ROWS) -> None:
    header = {"version": 2, "width": cols, "height": rows, "timestamp": int(started),
              "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header) + "\n")
        for instant, chunk in events:
            handle.write(json.dumps([instant, "o", chunk]) + "\n")


def capture(demo_id: str, steps: List[Step], out: pathlib.Path, env: Dict[str, str], values: List[Tuple[str, str, bool]],
            cwd: pathlib.Path = ROOT, **options) -> Tuple[bool, str]:
    """Play the steps, check the local values, write the files. Returns (passed, detail)."""
    started = time.time()
    cols, rows = options.get("cols", COLS), options.get("rows", ROWS)
    events, stopped = play(steps, env, cwd, **options)
    leaked = printed("".join(chunk for _, chunk in events), values)
    failures = [stopped] if stopped else []
    failures += [f"`{c.cmd}` (row {s.time}) ended with exit code {c.rc}" for s in steps for c in s.commands if c.rc]
    if leaked:
        failures.insert(0, "the session printed " + ", ".join(leaked) + ": the cast is not written")
    else:
        write_cast(out / "terminal.cast", events, started, cols, rows)
    record = {
        "demo": demo_id, "cols": cols, "rows": rows,
        "started": datetime.datetime.utcfromtimestamp(started).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "steps": [{"time": s.time, "typed": s.commands[0].typed, "done": s.commands[-1].done,
                   "commands": [{"cmd": c.cmd, "typed": c.typed, "done": c.done, "rc": c.rc} for c in s.commands]}
                  for s in steps if s.commands],
        "status": "fail" if failures else "done",
        "detail": "; ".join(failures) if failures else f"{sum(len(s.commands) for s in steps)} commands in {events[-1][0]:.1f} s",
    }
    (out / "terminal-steps.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return not failures, record["detail"]


def window(record: dict) -> Tuple[int, int, List[str]]:
    """(cols, rows, problems) of demo.yml `record: {cols, rows}`: the terminal's window, 100x30 when absent. A wide
    table needs more columns than 100; the commands stay the page's own, so the window is what adapts."""
    problems = []
    size = []
    for key, default, (low, high) in (("cols", COLS, COLS_RANGE), ("rows", ROWS, ROWS_RANGE)):
        value = (record or {}).get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            problems.append(f"demo.yml `record: {{{key}: {value!r}}}` must be a whole number from {low} to {high}")
            value = default
        size.append(value)
    return size[0], size[1], problems


def skips(record: dict, rows: List[Tuple[str, bool]]) -> Tuple[Dict[str, str], List[str]]:
    """({time: why}, problems) of demo.yml `record: {skip: {"<M:SS>": "<why>"}}`: 5-minute rows the take does not
    type, each with the reason in one phrase (the guard summary prints it). `rows` are the 5-minute rows as
    (time, has a Do command). A skipped time must be such a row with a command; an unquoted 3:00 is read by YAML as
    the base-60 integer 180, so integers are read back as M:SS."""
    value = (record or {}).get("skip")
    if value is None:
        return {}, []
    if not isinstance(value, dict) or not value:
        return {}, ['demo.yml `record.skip` must be a mapping of 5-minute row times to a reason, such as '
                    '{"3:00": "prints the checkout path"}']
    commands = dict(rows)
    found, problems = {}, []
    for key, why in value.items():
        time_ = f"{key // 60}:{key % 60:02d}" if isinstance(key, int) and not isinstance(key, bool) else str(key)
        if time_ not in commands:
            problems.append(f"demo.yml `record.skip` names {time_}, which is not a time of the 5-minute version "
                            f"({', '.join(t for t, _ in rows)})")
        elif not commands[time_]:
            problems.append(f"demo.yml `record.skip` names {time_}, a row with no Do command: nothing is typed there")
        elif not isinstance(why, str) or not why.strip() or "\n" in why.strip():
            problems.append(f"demo.yml `record.skip` {time_}: the reason must be one phrase")
        else:
            found[time_] = why.strip()
    return found, problems


def demo_manifest(demo_id: str, root: pathlib.Path = ROOT) -> dict:
    sys.path.insert(0, str(root / "platform/demo"))
    import catalogue
    import yaml

    return yaml.safe_load((catalogue.demo_dir(demo_id, root) / "demo.yml").read_text(encoding="utf-8")) or {}


def demo_skips(demo_id: str, root: pathlib.Path = ROOT) -> Tuple[Dict[str, str], List[str]]:
    """The skipped 5-minute rows of a demo, {time: why}, and the problems of its `record.skip`."""
    sys.path.insert(0, str(root / "platform/demo"))
    import catalogue

    page = catalogue.load(catalogue.find(demo_id, root))
    rows = [(row.time, bool(catalogue.do_commands(row.do))) for row in page.steps("5")]
    return skips(demo_manifest(demo_id, root).get("record") or {}, rows)


def demo_window(demo_id: str, root: pathlib.Path = ROOT) -> Tuple[int, int, List[str]]:
    sys.path.insert(0, str(root / "platform/demo"))
    import catalogue
    import yaml

    manifest = yaml.safe_load((catalogue.demo_dir(demo_id, root) / "demo.yml").read_text(encoding="utf-8")) or {}
    return window(manifest.get("record") or {})


def demo_steps(demo_id: str, root: pathlib.Path = ROOT) -> Tuple[List[Step], Dict[str, str], List[str]]:
    """(the 5-minute rows with their Do commands, the demo's variables, why some may not be typed)."""
    sys.path.insert(0, str(root / "platform/demo"))
    import catalogue
    import readonly
    import yaml

    page = catalogue.load(catalogue.find(demo_id, root))
    manifest = yaml.safe_load((catalogue.demo_dir(demo_id, root) / "demo.yml").read_text(encoding="utf-8")) or {}
    variables = {str(k): str(v) for k, v in (manifest.get("env") or {}).items()}
    if any("cluster_base_domain" in v for v in variables.values()):
        domain = subprocess.run(["oc", "get", "ingresses.config.openshift.io", "cluster", "-o", "jsonpath={.spec.domain}"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True).stdout.strip()
        if not domain:
            raise NoDomain("the demo's variables use the cluster domain and `oc` gave none: is oc logged in?")
        variables = {k: re.sub(r"\{\{\s*cluster_base_domain\s*\}\}", domain, v) for k, v in variables.items()}
    allow = [str(c) for c in ((manifest.get("record") or {}).get("allow") or [])]
    skipped, problems = skips(manifest.get("record") or {},
                              [(row.time, bool(catalogue.do_commands(row.do))) for row in page.steps("5")])
    steps = []
    for row in page.steps("5"):
        if row.time in skipped:
            continue        # not typed, so not checked either: the take does not show this row
        step = Step(row.time)
        for command in catalogue.do_commands(row.do):
            once = readonly.strip_watch_flags(command)[0]
            typed, why = acceptable(once, allow, lambda c: readonly.check(c, variables))
            if why:
                problems.append(f"row {row.time}: `{command}` is {why}")
            else:
                step.commands.append(Command(typed))
        if step.commands:
            steps.append(step)
    return steps, variables, problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a terminal demo as a real session (ADR-0618).")
    parser.add_argument("demo")
    parser.add_argument("out_dir", nargs="?", default="")
    parser.add_argument("--plan", action="store_true", help="only print what would be typed; nothing runs, no out_dir needed")
    args = parser.parse_args(argv)
    if not args.plan and not args.out_dir:
        parser.error("out_dir is required unless --plan")
    try:
        steps, variables, problems = demo_steps(args.demo)
        cols, rows, size_problems = demo_window(args.demo)
        problems += size_problems
        skipped = demo_skips(args.demo)[0]
    except (KeyError, OSError, NoDomain) as exc:   # also for --plan: a plan with an empty host would show wrong URLs
        print(f"{args.demo}: {exc}", file=sys.stderr)
        return 2
    if args.plan or problems:
        for step in steps:
            for command in step.commands:
                print(f"{step.time}  $ {command.cmd}")
        for time_, why in skipped.items():
            print(f"{time_}  {SKIPPED} {why}")
    if problems:
        print("CAPTURE: failed " + "; ".join(problems))
        return 1
    if args.plan:
        return 0
    if not steps:
        print(f"CAPTURE: failed {args.demo} has no Do command to type in its 5-minute rows")
        return 1
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kubeconfig = os.environ.get("KUBECONFIG") or os.path.expanduser("~/.kube/config")
    whoami = subprocess.run(["oc", "whoami", "-t"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
    token = whoami.stdout.strip()
    if whoami.returncode != 0 or not token:
        print("oc is not logged in: the presenter's session is what the terminal runs with", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="zuno-terminal-home-") as home:
        env = clean_env(kubeconfig, variables, home)
        passed, detail = capture(args.demo, steps, out, env, local_values(kubeconfig, variables, token)
                                 + [("the temporary home", home, False)], cols=cols, rows=rows)
    print("CAPTURE: done" if passed else f"CAPTURE: failed {detail}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
