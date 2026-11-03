#!/usr/bin/env python3
"""Read-only check of a live agent delegation through the a2a-gateway (WP-174, ADR-0401/0403/0406).

After a delegating run (Arkos -> Tekos, started by a person in UnifAI or by arkos scenario 21), the evidence is in
the logs of the gateways, which this script reads (`oc logs`, nothing is changed):

  mcp-gateway   the audit line of every tool call carries `caller` (the user's `sub`), `agent`/`task` (the target),
                `delegated_by`, `depth` and `allowed`. A delegated call that runs as the user shows
                `delegated_by=<delegator>:<task>` and `depth=1`; a refused chain shows `allowed=False`.
  a2a-gateway   one access line per call: `POST /agents/<target>/ 200`.

    python3 platform/testing/a2a_delegation_check.py --delegator arkos --target tekos --since 30m
    python3 platform/testing/a2a_delegation_check.py --since 30m --expect-denied-sub <sub of the unentitled persona>

Exit code 0 when at least one delegated call ran as a user with the expected chain and none of the delegated calls
broke the chain rules; 1 otherwise (the findings are printed). No token is read or printed: only the `sub`.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

_FIELD = re.compile(r"(\w+)=(\[[^\]]*\]|\S*)")
_A2A_ACCESS = re.compile(r'"POST /agents/([a-z][a-z0-9-]*)/? HTTP/1\.\d" (\d{3})')


@dataclass(frozen=True)
class ToolCall:
    tool: str
    agent: str
    task: str
    caller: str
    delegated_by: str
    depth: str
    allowed: str
    reason: str


def parse_mcp_audit(text: str) -> List[ToolCall]:
    """The `tool=... delegated_by=... depth=... allowed=...` lines of the mcp-gateway log."""
    calls: List[ToolCall] = []
    for line in text.splitlines():
        if " tool=" not in line or "delegated_by=" not in line:
            continue
        fields = dict(_FIELD.findall(line))
        calls.append(ToolCall(
            tool=fields.get("tool", ""), agent=fields.get("agent", ""), task=fields.get("task", ""),
            caller=fields.get("caller", ""), delegated_by=fields.get("delegated_by", ""),
            depth=fields.get("depth", ""), allowed=fields.get("allowed", ""), reason=fields.get("reason", ""),
        ))
    return calls


def parse_a2a_access(text: str) -> List[tuple]:
    """(target agent, HTTP status) of every POST the a2a-gateway served."""
    return [(m.group(1), int(m.group(2))) for m in _A2A_ACCESS.finditer(text)]


def delegated(calls: List[ToolCall], delegator: str, target: str) -> List[ToolCall]:
    """Tool calls made by `target` on behalf of `delegator` (the chain names the delegator first)."""
    return [c for c in calls if c.agent == target and c.delegated_by.split(",", 1)[0].startswith(f"{delegator}:")]


def evaluate(
    mcp_log: str, a2a_log: str, *, delegator: str, target: str, expect_denied_sub: Optional[str] = None
) -> tuple[bool, List[str]]:
    findings: List[str] = []
    chain_calls = delegated(parse_mcp_audit(mcp_log), delegator, target)
    ran = [c for c in chain_calls if c.allowed == "True"]
    refused = [c for c in chain_calls if c.allowed != "True"]
    served = [s for a, s in parse_a2a_access(a2a_log) if a == target]

    if not ran:
        findings.append(f"no tool call of '{target}' ran on behalf of '{delegator}' in the window")
    for c in ran:
        if c.depth != "1":
            findings.append(f"delegated call {c.tool} has depth={c.depth}, expected 1")
        if not c.caller or c.caller in ("-", "None"):
            findings.append(f"delegated call {c.tool} carries no caller identity")
    findings.append(
        f"a2a-gateway served {len(served)} call(s) to '{target}' "
        f"({sum(1 for s in served if s == 200)} x 200, {sum(1 for s in served if s == 404)} x 404)"
    )
    if refused:
        findings.append(f"{len(refused)} delegated call(s) refused by the chain rules: {sorted({c.reason for c in refused})}")
    ok = bool(ran) and not any(f.startswith(("delegated call", "no tool call")) for f in findings)
    if expect_denied_sub:
        leaked = [c for c in ran if c.caller == expect_denied_sub]
        if leaked:
            ok = False
            findings.append(f"the unentitled caller {expect_denied_sub} ran {len(leaked)} delegated call(s): it must be refused")
        else:
            findings.append("the unentitled caller ran no delegated call (as expected)")
    return ok, findings


def oc_logs(namespace: str, deployment: str, since: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    done = run(
        ["oc", "logs", "-n", namespace, f"deploy/{deployment}", "--all-containers=false", f"--since={since}"],
        capture_output=True, text=True, timeout=120,
    )
    if done.returncode != 0:
        raise RuntimeError(f"oc logs {deployment}: {done.stderr.strip()[:200]}")
    return done.stdout


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delegator", default="arkos")
    parser.add_argument("--target", default="tekos")
    parser.add_argument("--since", default="30m", help="log window passed to `oc logs --since`")
    parser.add_argument("--namespace", default="zuno-ai-run")
    parser.add_argument("--expect-denied-sub", help="`sub` of a persona without the target's group: it must have no delegated call")
    args = parser.parse_args(argv)
    try:
        mcp_log = oc_logs(args.namespace, "mcp-gateway", args.since)
        a2a_log = oc_logs(args.namespace, "a2a-gateway", args.since)
    except (RuntimeError, subprocess.SubprocessError) as exc:
        print(f"cannot read the logs: {exc}", file=sys.stderr)
        return 2
    ok, findings = evaluate(
        mcp_log, a2a_log, delegator=args.delegator, target=args.target, expect_denied_sub=args.expect_denied_sub
    )
    for line in findings:
        print(("PASS " if ok else "INFO ") + line)
    print("RESULT: " + ("delegation proven in the gateway logs" if ok else "no proof of a delegation that ran as a user"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
