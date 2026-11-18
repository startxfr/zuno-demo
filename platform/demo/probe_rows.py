#!/usr/bin/env python3
"""One check row per probe, from the output of a golden-path or browser run (ADR-0616 clause 9).

`evaluations/golden_path_probe.py` and `evaluations/browser/run.mjs` print one result line per probe,
`STATUS name  12.3s  detail`, then `RESULT: ...`. `ansible/demos/_lib/flush_checks.yml` hands each run's exit code and
output to this file on stdin and records what it prints: one Day2Result row per probe, with the probe's own detail, so
a failed check names the probe that failed and why in the terminal RESULT, the log and the rehearsal report. A run that
fails without a failing result line (a crash, an unknown probe name, no exit code) gets one FAIL row for the whole run,
with its last error line. The lines that are not result lines are kept as the command's output.

Nothing here reads a credential, and the two scripts never print one; what looks like one (a bearer token, a JWT, an
OpenShift token, a `password=` value) is masked all the same before anything is recorded.

    echo '{"agent": "d", "layer": "check", "runs": [...]}' | python3 platform/demo/probe_rows.py
"""
from __future__ import annotations

import json
import re
import sys
from typing import Dict, List, Tuple

MASK = "***"
KEPT_LINES = 40
DETAIL_CHARS = 400
RESULT_LINE = re.compile(r"^(PASS|FAIL|MANUAL|ROADMAP|SKIPPED)\s+(\S+)\s+(\d+(?:\.\d+)?)s(?:\s(.*))?$")
SECRETS = [
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]+){0,2}"), MASK),
    (re.compile(r"\bsha256~[A-Za-z0-9_-]{8,}"), MASK),
    (re.compile(r"(?i)\b((?:[a-z0-9_-]*(?:password|passwd|secret|token|api[_-]?key)[a-z0-9_-]*)"
                r"[\"']?\s*[=:]\s*[\"']?)[^\s\"'&,;]+"), r"\1" + MASK),
    (re.compile(r"(://[^/\s:@]+:)[^@\s/]+@"), r"\1" + MASK + "@"),
]


def mask(text: str) -> str:
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


def parse(stdout: str) -> Tuple[List[dict], List[str]]:
    """(result lines as {status, name, seconds, detail}, the other non-empty lines) of a run's output."""
    found: List[dict] = []
    other: List[str] = []
    for line in (stdout or "").splitlines():
        match = RESULT_LINE.match(line.rstrip())
        if match:
            found.append({"status": match.group(1).lower(), "name": match.group(2),
                          "seconds": float(match.group(3)), "detail": (match.group(4) or "").strip()})
        elif line.strip() and not line.startswith("RESULT: "):
            other.append(line.rstrip())
    return found, other


def rows(run: dict, agent: str, layer: str) -> Tuple[List[dict], dict]:
    """(check rows, command record) of one run: {kind, names, cmd, rc, stdout, stderr, msg}."""
    kind = str(run.get("kind") or "golden-path")
    names = [str(n) for n in run.get("names") or []]
    rc = run.get("rc")
    rc = rc if isinstance(rc, int) and not isinstance(rc, bool) else -1
    found, other = parse(str(run.get("stdout") or ""))
    errors = [line.rstrip() for line in str(run.get("stderr") or "").splitlines() if line.strip()]
    message = " ".join(str(run.get("msg") or "").split())

    def row(name: str, passed: bool, detail: str, seconds: float = 0.0) -> dict:
        return {"agent": agent, "layer": layer, "id": f"{kind}/{name}", "category": kind, "passed": passed,
                "detail": mask(detail)[:DETAIL_CHARS], "duration_ms": int(seconds * 1000)}

    checks = []
    for item in found:
        failed = item["status"] == "fail"
        label = "" if item["status"] in ("pass", "fail") else item["status"] + ": "
        checks.append(row(item["name"], not failed, label + item["detail"], item["seconds"]))
    if rc != 0 and not any(item["status"] == "fail" for item in found):
        why = [f"exit {rc}" if rc >= 0 else "did not finish"]
        if message:
            why.append(message)
        if errors or other:
            why.append((errors or other)[-1].strip())
        checks.append(row(",".join(names) or "run", False, ": ".join(why)))
    elif not found:
        checks.append(row(",".join(names) or "run", True, "exit 0, no result line"))
    kept = (other + errors)[-KEPT_LINES:]
    command = {"cmd": str(run.get("cmd") or ""), "rc": rc, "output": mask("\n".join(kept)),
               "truncated": len(other) + len(errors) > KEPT_LINES}
    return checks, command


def record(data: dict) -> Dict[str, list]:
    checks: List[dict] = []
    commands: List[dict] = []
    for run in data.get("runs") or []:
        new_checks, command = rows(run, str(data.get("agent") or ""), str(data.get("layer") or ""))
        checks += new_checks
        commands.append(command)
    return {"checks": checks, "commands": commands}


def main() -> int:
    print(json.dumps(record(json.load(sys.stdin))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
