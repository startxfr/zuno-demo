"""The text gate of a terminal take: the captured session, checked as text before any pixel (ADR-0618 clauses 4 and 5,
WP-287).

    python3 platform/demo/textgate.py <take dir>

Reads `terminal.cast` (asciicast v2, written by evaluations/browser/terminal/capture.py), removes the escape codes,
and writes in the same directory:
    transcript.txt   the session as plain text, for the recording session to read before anything is rendered
    gate.json        {status: "pass"|"refused", hits: [{line, detector}], lines, cast_sha256, steps_status}
A hit names its transcript line and its detector, never the value. The cast is never edited: what is rendered is
what happened, so a hit refuses the take and the presenter records again after fixing the cause.

The real local values (the presenter's token, the kubeconfig path, the home directory, the login and host names)
are checked by the capture itself, which writes no cast when the session printed one. The detectors here are
patterns: bearer tokens, JWTs, `sha256~` tokens, URL userinfo, and a password, secret, token or API key value.
Exit codes: 0 pass, 1 refused, 2 no cast or an unreadable one.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple

CAST = "terminal.cast"
STEPS = "terminal-steps.json"
TRANSCRIPT = "transcript.txt"
GATE = "gate.json"
CLEAR_LINE = "---- clear ----"

CLEAR_RE = re.compile(r"\x1b\[H\x1b\[2?J|\x1b\[2J\x1b\[H")
OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ESC_RE = re.compile(r"\x1b[()][0-9A-Za-z]|\x1b[@-Z\\-_]|\x1b[=>78]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# A value these keys hold is a secret; these stand-ins are not.
NOT_A_VALUE = {"***", "<none>", "none", "null", "true", "false", "redacted", "<redacted>", "-", "''", '""', "{}", "[]"}
DETECTORS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("bearer token", re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I)),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("sha256~ token", re.compile(r"sha256~[A-Za-z0-9_-]{20,}")),
    ("URL userinfo", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"]+:[^/\s@'\"]+@", re.I)),
]
CREDENTIAL_RE = re.compile(
    r"""\b(password|passwd|secret|client[_-]?secret|token|access[_-]?token|api[_-]?key)\b["']?\s*[=:]\s*["']?"""
    r"""([^\s"',}]*)""", re.I)


class GateError(Exception):
    """No cast, or one that cannot be read."""


def read_cast(path: pathlib.Path) -> str:
    """The output stream of an asciicast v2 file: every "o" event, in order."""
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except FileNotFoundError:
        raise GateError(f"{path} is missing: the capture refused the session or did not run")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError(f"{path} cannot be read: {exc}")
    try:
        header = json.loads(lines[0])
    except (ValueError, IndexError):
        raise GateError(f"{path}: the first line is not an asciicast header")
    if not isinstance(header, dict) or header.get("version") != 2:
        raise GateError(f"{path}: not an asciicast v2 file")
    chunks = []
    for number, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            raise GateError(f"{path}:{number}: not a JSON event")
        if isinstance(event, list) and len(event) == 3 and event[1] == "o" and isinstance(event[2], str):
            chunks.append(event[2])
    return "".join(chunks)


def plain(stream: str) -> str:
    """The stream as a reader sees it: no escape codes, no carriage returns, a line where the screen was cleared."""
    text = CLEAR_RE.sub(f"\n{CLEAR_LINE}\n", stream)
    text = OSC_RE.sub("", text)
    text = CSI_RE.sub("", text)
    text = ESC_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "")
    text = CONTROL_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n") + "\n"


def hits(text: str) -> List[Dict[str, object]]:
    """[{line, detector}] for every line that holds something a public GIF must not show."""
    found = []
    for number, line in enumerate(text.split("\n"), 1):
        for name, pattern in DETECTORS:
            if pattern.search(line):
                found.append({"line": number, "detector": name})
        for match in CREDENTIAL_RE.finditer(line):
            value = match.group(2)
            if value and value.lower() not in NOT_A_VALUE and not value.startswith("$"):
                found.append({"line": number, "detector": f"a {match.group(1).lower()} value"})
                break
    return found


def gate(directory: pathlib.Path) -> dict:
    """Check the take in `directory`; write transcript.txt and gate.json; return the gate record. Raises GateError."""
    cast = directory / CAST
    text = plain(read_cast(cast))
    (directory / TRANSCRIPT).write_text(text, encoding="utf-8")
    found = hits(text)
    steps_status: Optional[str] = None
    try:
        steps_status = json.loads((directory / STEPS).read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError, AttributeError):
        steps_status = None
    record = {"status": "refused" if found else "pass", "hits": found, "lines": text.count("\n"),
              "cast_sha256": hashlib.sha256(cast.read_bytes()).hexdigest(), "steps_status": steps_status}
    (directory / GATE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def passed(directory: pathlib.Path) -> Tuple[bool, str]:
    """(True, "") when the take's gate passed on the cast as it is now and its capture finished; else (False, why)."""
    try:
        record = json.loads((directory / GATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "the text gate has not run on this take"
    if record.get("status") != "pass":
        return False, f"the text gate refused this take ({len(record.get('hits') or [])} hit(s))"
    try:
        current = hashlib.sha256((directory / CAST).read_bytes()).hexdigest()
    except OSError:
        return False, "terminal.cast is gone"
    if current != record.get("cast_sha256"):
        return False, "terminal.cast changed after the gate ran"
    if record.get("steps_status") != "done":
        return False, f"the capture did not finish (terminal-steps.json status {record.get('steps_status')!r})"
    return True, ""


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write("Usage: python3 platform/demo/textgate.py <take dir>\n")
        return 2
    directory = pathlib.Path(args[0])
    try:
        record = gate(directory)
    except GateError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    for hit in record["hits"]:
        print(f"HIT {TRANSCRIPT}:{hit['line']}: {hit['detector']}")
    print(f"GATE: {record['status']} ({len(record['hits'])} hit(s), {record['lines']} lines) {directory / TRANSCRIPT}")
    return 0 if record["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
