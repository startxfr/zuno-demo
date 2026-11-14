"""Run the read-only commands of a page's Do cell, without a shell (ADR-0616 clause 5, WP-270).

Allowed, as written on the page:
- `oc get|describe|logs|explain|whoami|api-resources|version`, `oc auth can-i`, `oc adm top`, `oc set env ... --list`;
- pipes into `grep awk sort uniq head tail wc cut jq`;
- `git log|show`;
- GET-only `curl`, with `$(oc whoami -t)` resolved in this process and masked in everything printed;
- `make help`, `make demo`, `make demo list`, `[ONLY=x] make demo golden-path`, `make dN check [component]` (run as
  its local playbook, never through AAP), `make d3 admit agents` without `UPDATE_LOCK`.

Refused: Secret reads other than `-o name`, watches and follows, redirects, `;`, `&&`, `||`, `&`, backticks, any other
`$(`, `xargs`, and everything not listed above.

    python3 platform/demo/readonly.py check '<command>'
    python3 platform/demo/readonly.py run [--json] '<command>'

Exit codes: 0 allowed / succeeded, 1 the command failed, 2 refused.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ENGINE_ROOT = pathlib.Path(__file__).resolve().parents[2]
TOKEN_EXPR = "$(oc whoami -t)"
TOKEN_PLACEHOLDER = "__ZUNO_OC_TOKEN__"
MASK = "***"
OUTPUT_LINES = 40
READ_TIMEOUT = 120
MAKE_TIMEOUT = 600

OC_VERBS = {"get", "describe", "logs", "explain", "whoami", "api-resources", "version"}
OC_GLOBAL_WITH_VALUE = {"-n", "--namespace", "--context", "--cluster", "--user", "--kubeconfig", "--request-timeout"}
PIPE_FILTERS = {"grep", "awk", "sort", "uniq", "head", "tail", "wc", "cut", "jq"}
SECRET_RESOURCES = {"secret", "secrets"}
CURL_DENIED = {
    "-d", "--data", "--data-ascii", "--data-binary", "--data-raw", "--data-urlencode", "-F", "--form",
    "--form-string", "-T", "--upload-file", "-o", "--output", "-O", "--remote-name", "--remote-name-all",
    "--json", "-K", "--config", "-c", "--cookie-jar", "-D", "--dump-header", "--output-dir", "--create-dirs",
    "--trace", "--trace-ascii", "--libcurl", "--stderr", "-P", "--ftp-port", "-Q", "--quote", "--proxy", "-x",
}
DAY_CHECK_RE = re.compile(r"^(?:d|day)([0-3])$")


class Denied(ValueError):
    """The command is outside the read-only allowlist."""


@dataclass
class Plan:
    display: str                          # the command as written (the token expression kept, never its value)
    pipeline: List[List[str]]             # argv per process; TOKEN_PLACEHOLDER where the token goes
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = READ_TIMEOUT
    needs_token: bool = False


@dataclass
class Result:
    cmd: str
    rc: int
    output: str
    truncated: bool = False
    log: str = ""
    refused: bool = False

    def to_dict(self) -> dict:
        return {"cmd": self.cmd, "rc": self.rc, "output": self.output, "truncated": self.truncated,
                "refused": self.refused}


def _tokens(segment_text: str) -> List[str]:
    lexer = shlex.shlex(segment_text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def tokenize(command: str) -> List[List[str]]:
    """Pipeline segments of a command; raise Denied on anything a shell would interpret beyond a plain pipe."""
    text = command.strip()
    if text.startswith("`") and text.endswith("`") and text.count("`") == 2:
        text = text[1:-1].strip()
    text = re.sub(r"\\\r?\n\s*", " ", text)
    if not text:
        raise Denied("empty command")
    if "`" in text:
        raise Denied("backticks are refused")
    text = text.replace(TOKEN_EXPR, TOKEN_PLACEHOLDER)
    if "$(" in text or "${" in text:
        raise Denied("command substitution is refused (only $(oc whoami -t) is resolved)")
    if re.search(r"<[A-Za-z][\w .-]*>", text):
        raise Denied("the command holds a placeholder (<...>) to fill in")
    try:
        tokens = _tokens(text)
    except ValueError as exc:
        raise Denied(f"cannot parse the command: {exc}")
    segments: List[List[str]] = [[]]
    for token in tokens:
        if token == "|":
            segments.append([])
            continue
        if token and set(token) <= set("();<>|&"):
            if token in (";",):
                raise Denied("`;` is refused")
            if token in ("&&", "||"):
                raise Denied(f"`{token}` is refused")
            if token == "&":
                raise Denied("background `&` is refused")
            if set(token) <= set("<>"):
                raise Denied("redirects are refused")
            raise Denied(f"`{token}` is refused")
        segments[-1].append(token)
    if any(not s for s in segments):
        raise Denied("an empty pipeline segment")
    return segments


def _flag_value(args: List[str], names: Tuple[str, ...]) -> Optional[str]:
    for i, arg in enumerate(args):
        for name in names:
            if arg == name and i + 1 < len(args):
                return args[i + 1]
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
            if len(name) == 2 and arg.startswith(name) and len(arg) > 2 and not arg.startswith("--"):
                return arg[2:]
    return None


def _has_flag(args: List[str], names: Tuple[str, ...]) -> bool:
    for arg in args:
        for name in names:
            if arg == name or arg.startswith(name + "="):
                return True
    return False


def _oc_verb(argv: List[str]) -> Tuple[str, List[str]]:
    """(verb, args) of an `oc` command, skipping the global flags that may precede the verb."""
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in OC_GLOBAL_WITH_VALUE:
            i += 2
            continue
        if arg.startswith("-"):
            i += 1
            continue
        return arg, argv[i + 1:]
    return "", []


def _names_secret(args: List[str]) -> bool:
    for arg in args:
        if arg.startswith("-"):
            continue
        for part in arg.split(","):
            kind = part.split("/", 1)[0].split(".", 1)[0].lower()
            if kind in SECRET_RESOURCES:
                return True
    return False


def check_oc(argv: List[str]) -> None:
    verb, args = _oc_verb(argv)
    every = argv[1:]
    if _has_flag(every, ("-w", "--watch", "--watch-only")):
        raise Denied("watches are refused")
    if verb == "auth":
        if not args or args[0] != "can-i":
            raise Denied("only `oc auth can-i` is allowed")
        return
    if verb == "adm":
        if not args or args[0] != "top":
            raise Denied("only `oc adm top` is allowed")
        return
    if verb == "set":
        if not args or args[0] != "env" or "--list" not in args:
            raise Denied("only `oc set env ... --list` is allowed")
        if _has_flag(args, ("--resolve",)):
            raise Denied("`--resolve` prints Secret values")
        return
    if verb not in OC_VERBS:
        raise Denied(f"`oc {verb or '?'}` is not a read the allowlist knows")
    if verb == "whoami" and _has_flag(args, ("-t", "--show-token")):
        raise Denied("`oc whoami -t` prints the token; it is only resolved inside a curl header")
    if verb == "logs" and _has_flag(args, ("-f", "--follow")):
        raise Denied("following logs is refused")
    if verb == "get" and _has_flag(args, ("-f", "--filename")):
        raise Denied("`-f` is refused")
    raw = _flag_value(args, ("--raw",))
    if raw is not None and "secret" in raw.lower():
        raise Denied("reading a Secret is refused (`--raw` on a secrets path)")
    if verb in ("get", "describe") and _names_secret(args):
        output = _flag_value(args, ("-o", "--output"))
        if verb == "describe" or output != "name":
            raise Denied("reading a Secret is refused (only `-o name`)")


def check_filter(argv: List[str]) -> None:
    name = argv[0]
    if name == "xargs":
        raise Denied("`xargs` is refused")
    if name not in PIPE_FILTERS:
        raise Denied(f"`{name}` is not an allowed filter ({' '.join(sorted(PIPE_FILTERS))})")
    args = argv[1:]
    if name == "tail" and _has_flag(args, ("-f", "-F", "--follow")):
        raise Denied("following is refused")
    if name == "sort" and _has_flag(args, ("-o", "--output")):
        raise Denied("`sort -o` writes a file")
    if name == "uniq" and len([a for a in args if not a.startswith("-")]) > 1:
        raise Denied("`uniq` with an output file is refused")
    if name == "awk":
        program = " ".join(args)
        if re.search(r"\bsystem\s*\(|\bgetline\b|\|\s*\"|>\s*\"|\bfflush\b", program):
            raise Denied("this awk program runs commands or writes files")
        if "ENVIRON" in program:
            raise Denied("this awk program prints the environment")
    if name == "jq":
        if _has_flag(args, ("--rawfile", "--slurpfile", "--from-file", "-f", "-L", "--args", "--jsonargs")):
            raise Denied("this jq option reads local files")
        if re.search(r"\$ENV\b|(?<![.\w$])env\b|\binput_filename\b|\$__loc__", " ".join(args)):
            raise Denied("this jq program prints the environment")


def check_git(argv: List[str]) -> None:
    if len(argv) < 2 or argv[1] not in ("log", "show"):
        raise Denied("only `git log` and `git show` are allowed")
    if _has_flag(argv[2:], ("--output", "--ext-diff", "--textconv", "--exec-path")):
        raise Denied("this git option writes files or runs a program")


def check_curl(argv: List[str]) -> None:
    args = argv[1:]
    method = _flag_value(args, ("-X", "--request"))
    if method is not None and method.upper() not in ("GET", "HEAD"):
        raise Denied(f"curl {method} is refused (GET only)")
    for arg in args:
        flag = arg.split("=", 1)[0] if arg.startswith("--") else arg
        if flag in CURL_DENIED or (not arg.startswith("--") and arg[:2] in CURL_DENIED and len(arg) > 2
                                   and arg[:2] in ("-d", "-F", "-T", "-o", "-O", "-K", "-c", "-D", "-x", "-Q")):
            raise Denied(f"curl `{flag}` sends data or writes a file (GET only)")
        if arg.startswith("@"):
            raise Denied("curl reading a local file is refused")
        scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", arg)
        if scheme and scheme.group(1).lower() not in ("http", "https"):
            raise Denied(f"curl {scheme.group(1)}:// is refused (http and https only)")


def plan_make(env_prefix: Dict[str, str], argv: List[str], display: str, root: pathlib.Path) -> Plan:
    args = argv[1:]
    words = [a for a in args if "=" not in a]
    make_vars = dict(a.split("=", 1) for a in args if "=" in a)
    if "UPDATE_LOCK" in env_prefix or "UPDATE_LOCK" in make_vars:
        raise Denied("UPDATE_LOCK changes the agents lock")
    if words == ["help"] and not env_prefix and not make_vars:
        return Plan(display, [["make", "-s", "help"]], timeout=MAKE_TIMEOUT)
    if words == ["demo", "golden-path"] and set(env_prefix) <= {"ONLY"} and not make_vars:
        return Plan(display, [["make", "demo", "golden-path"]], env=dict(env_prefix), timeout=MAKE_TIMEOUT)
    if words in (["demo"], ["demo", "list"]) and not env_prefix and not make_vars:
        return Plan(display, [["python3", str(root / "platform/demo/presenter.py")] + words[1:]], timeout=READ_TIMEOUT)
    if env_prefix:
        raise Denied("only ONLY=... may precede `make demo golden-path`")
    if len(words) >= 2 and DAY_CHECK_RE.match(words[0]) and words[1] == "check" and len(words) <= 3 and not make_vars:
        day = DAY_CHECK_RE.match(words[0]).group(1)
        component = words[2] if len(words) == 3 else "all"
        playbook = ["ansible-playbook", "-i", str(root / "ansible/inventories/demo/hosts.yml"),
                    str(root / f"ansible/playbooks/day{day}_check.yml"), "-e", f"target_component={component}"]
        if day == "3":
            playbook += ["-e", "report_format=text"]
        return Plan(display, [playbook], timeout=MAKE_TIMEOUT)
    if words[:3] == ["d3", "admit", "agents"] and len(words) == 3 and set(make_vars) <= {"RELEASE"}:
        cmd = ["python3", str(root / "platform/supply-chain/admit_okf_bundle.py"), "admit"]
        if make_vars.get("RELEASE"):
            cmd += ["--release", make_vars["RELEASE"]]
        return Plan(display, [cmd], timeout=MAKE_TIMEOUT)
    raise Denied(f"`make {' '.join(args)}` is not a read the allowlist knows")


def plan(command: str, root: Optional[pathlib.Path] = None) -> Plan:
    """Check a command against the allowlist and return how to run it, or raise Denied."""
    root = root or ENGINE_ROOT
    display = command.strip().strip("`").strip()
    segments = tokenize(command)
    head = segments[0]
    env_prefix: Dict[str, str] = {}
    while head and re.match(r"^[A-Z_][A-Z0-9_]*=", head[0]):
        key, value = head[0].split("=", 1)
        env_prefix[key] = value
        head = head[1:]
    if not head:
        raise Denied("no command")
    segments[0] = head
    program = head[0]
    if program == "make":
        if len(segments) > 1:
            raise Denied("a make verb is not piped")
        return plan_make(env_prefix, head, display, root)
    if env_prefix:
        raise Denied("environment assignments are refused")
    if program == "oc":
        check_oc(head)
    elif program == "git":
        check_git(head)
    elif program == "curl":
        check_curl(head)
    else:
        raise Denied(f"`{program}` is not an allowed command (oc, curl, git, make)")
    for segment in segments[1:]:
        check_filter(segment)
    needs_token = any(TOKEN_PLACEHOLDER in arg for seg in segments for arg in seg)
    if needs_token and program != "curl":
        raise Denied("$(oc whoami -t) is resolved only inside a curl command")
    return Plan(display, segments, needs_token=needs_token)


WATCH_FLAGS = {
    ("oc", "get"): ("-w", "--watch", "--watch-only"),
    ("oc", "describe"): ("-w", "--watch"),
    ("oc", "logs"): ("-f", "--follow"),
    ("tail", ""): ("-f", "-F", "--follow"),
}


def strip_watch_flags(command: str) -> Tuple[str, List[str]]:
    """(command without its watch/follow flags, the flags removed), for a Do command refused only for them.

    The step file then holds the result as `cmd` and the cell's command as `page_text`: it runs once, as a snapshot
    (reorg decision 2026-11-14). Raises Denied when the stripped command is still refused, or when nothing was
    stripped from a refused command.
    """
    text = command.strip()
    if text.startswith("`") and text.endswith("`") and text.count("`") == 2:
        text = text[1:-1].strip()
    removed: List[str] = []
    for segment in tokenize(text):
        program = segment[0]
        verb = _oc_verb(segment)[0] if program == "oc" else ""
        for flag in WATCH_FLAGS.get((program, verb), ()):
            if flag in segment:
                removed.append(flag)
    for flag in removed:
        text = re.sub(r"(?<!\S)" + re.escape(flag) + r"(?!\S)", "", text, count=1)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    plan(text)
    return text, removed


def check(command: str) -> Tuple[bool, str]:
    try:
        plan(command)
    except Denied as exc:
        return False, str(exc)
    return True, ""


def _resolve_token() -> str:
    done = subprocess.run(["oc", "whoami", "-t"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=30)
    token = done.stdout.strip()
    if done.returncode != 0 or not token:
        raise RuntimeError("`oc whoami -t` gave no token: log in with `oc login` first")
    return token


def _mask(text: str, secret: str) -> str:
    return text.replace(secret, MASK) if secret else text


def run_plan(p: Plan, cwd: Optional[pathlib.Path] = None, lines: int = OUTPUT_LINES) -> Result:
    """Run a pipeline without a shell; the result keeps `lines` lines of output, the token masked."""
    cwd = cwd or ENGINE_ROOT
    token = ""
    if p.needs_token:
        try:
            token = _resolve_token()
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            return Result(p.display, 1, str(exc))
    env = dict(os.environ)
    env.update(p.env)
    procs: List[subprocess.Popen] = []
    errs = []
    previous = None
    try:
        for i, argv in enumerate(p.pipeline):
            argv = [a.replace(TOKEN_PLACEHOLDER, token) if token else a for a in argv]
            err = tempfile.TemporaryFile()
            errs.append(err)
            last = i == len(p.pipeline) - 1
            proc = subprocess.Popen(argv, stdin=previous.stdout if previous else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=err, cwd=str(cwd), env=env)
            if previous is not None and previous.stdout is not None:
                previous.stdout.close()
            procs.append(proc)
            previous = proc
            if last:
                break
        try:
            out, _ = procs[-1].communicate(timeout=p.timeout)
        except subprocess.TimeoutExpired:
            for proc in procs:
                proc.kill()
            for proc in procs:
                proc.wait()
            for err in errs:
                err.close()
            return Result(p.display, 124, f"timed out after {p.timeout} s")
        for proc in procs[:-1]:
            proc.wait(timeout=10)
    except FileNotFoundError as exc:
        for proc in procs:
            proc.kill()
            proc.wait()
        for err in errs:
            err.close()
        return Result(p.display, 127, f"command not found: {exc.filename}")
    stderr_text = ""
    for err in errs:
        err.seek(0)
        stderr_text += err.read().decode("utf-8", "replace")
        err.close()
    rc = 0
    for proc in procs:
        code = proc.returncode
        if code in (-signal.SIGPIPE, 128 + signal.SIGPIPE) and proc is not procs[-1]:
            continue
        if code != 0:
            rc = code if code > 0 else 128 - code
            break
    text = out.decode("utf-8", "replace")
    if stderr_text.strip():
        text = (text.rstrip("\n") + "\n" if text.strip() else "") + stderr_text
    text = _mask(text, token)
    all_lines = text.rstrip("\n").split("\n") if text.strip() else []
    truncated = len(all_lines) > lines
    shown = "\n".join(all_lines[:lines])
    return Result(p.display, rc, shown, truncated, log=text)


def run(command: str, cwd: Optional[pathlib.Path] = None, lines: int = OUTPUT_LINES) -> Result:
    try:
        p = plan(command)
    except Denied as exc:
        return Result(command.strip().strip("`"), 2, f"REFUSED: {exc}", refused=True)
    return run_plan(p, cwd=cwd, lines=lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check or run a read-only demo command without a shell.")
    sub = parser.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("check")
    c.add_argument("command")
    r = sub.add_parser("run")
    r.add_argument("--json", action="store_true", help="print one JSON object (used by ansible/demos/_lib)")
    r.add_argument("--lines", type=int, default=OUTPUT_LINES)
    r.add_argument("command")
    args = parser.parse_args(argv)
    if args.mode == "check":
        ok, reason = check(args.command)
        print("allowed" if ok else f"REFUSED: {reason}")
        return 0 if ok else 2
    result = run(args.command, lines=args.lines)
    if args.json:
        print(json.dumps(result.to_dict()))
        return 0
    print(f"$ {result.cmd}")
    if result.output:
        print(result.output)
    if result.truncated:
        print(f"... (first {args.lines} lines)")
    return 2 if result.refused else (0 if result.rc == 0 else 1)


if __name__ == "__main__":
    sys.exit(main())
