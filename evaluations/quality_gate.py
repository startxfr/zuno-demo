#!/usr/bin/env python3
"""ADR-0107 model/agent promotion quality gate (roadmap WP-10).

"A model or agent change may only be promoted when the target agent's
ADR-0027 acceptance suite passes at the ADR-0028 threshold (75%) against
the candidate configuration, and no per-scenario security check
regresses... Thresholds are data (per-agent configuration), not code."

`evaluations/<agent>/run_acceptance_gate.py` already runs the three
layered checks (scenarios, security_checks, gate_checks - see that
script's own docstring) and prints a final JSON summary line, but its
75%-threshold decision is a hardcoded Python constant
(`SCENARIO_THRESHOLD`), and it isn't parameterized by agent (it imports
`run_scenarios`/`security_checks`/`gate_checks` via relative imports, so
it can only run as `evaluations/<agent>/run_acceptance_gate.py`, one
agent at a time, from its own directory). That script remains untouched
and keeps its own default threshold - it is still the entrypoint `make
check`'s acceptance-gate Job uses (ADR-0053), a related but distinct
concern from ADR-0107's promotion gate.

This module is the promotion-gate layer ADR-0107 adds on top: it invokes
the target agent's `run_acceptance_gate.py` as a subprocess (its own
directory-relative-import requirement), parses the JSON summary it
already prints, and re-derives the PASS/FAIL decision using a threshold
read from `evaluations/<agent>/gate_config.yaml` (data, not code) instead
of trusting that script's own hardcoded 75%. security_checks/gate_checks
stay 100% mandatory regardless of the configured scenario threshold - no
config can weaken those. An agent with no `gate_config.yaml` fails
closed (unknown agent = no declared gate = cannot be promoted), per
ADR-0107's blocking intent.

Usage:

    python3 evaluations/quality_gate.py --agent tekos [--candidate <label>]

`--candidate` is an informational label only (e.g. a model tag or commit
SHA) threaded through into the printed/JSON output for traceability -
this module does not select or switch which model/config the target
agent's own evaluation suite runs against; it evaluates whatever is
currently deployed/configured, same as `run_acceptance_gate.py` itself.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Any, Dict, Optional

import yaml

EVALUATIONS_DIR = pathlib.Path(__file__).resolve().parent


class QualityGateError(Exception):
    pass


def load_gate_config(agent: str) -> Dict[str, Any]:
    config_path = EVALUATIONS_DIR / agent / "gate_config.yaml"
    if not config_path.exists():
        raise QualityGateError(
            f"unknown agent {agent!r}: {config_path} does not exist - "
            "fail closed, an agent with no declared gate configuration cannot be promoted"
        )
    with config_path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    if "scenario_threshold" not in config:
        raise QualityGateError(f"{config_path} is missing the required key 'scenario_threshold'")
    return config


def run_acceptance_gate(agent: str) -> Dict[str, Any]:
    """Runs evaluations/<agent>/run_acceptance_gate.py as a subprocess and
    parses its final JSON summary line. Reuses that script's own layered
    scenario/security/gate-check logic entirely via its machine-readable
    output - does not reimplement any of it (ADR-0107's Decision text:
    "The gate consumes the machine-readable output of
    evaluations/<agent>/run_acceptance_gate.py").
    """
    agent_dir = EVALUATIONS_DIR / agent
    script = agent_dir / "run_acceptance_gate.py"
    if not script.exists():
        raise QualityGateError(f"unknown agent {agent!r}: {script} does not exist")

    proc = subprocess.run(
        [sys.executable, "run_acceptance_gate.py"],
        cwd=str(agent_dir),
        capture_output=True,
        text=True,
    )
    stdout_lines = proc.stdout.strip().splitlines()
    last_line = stdout_lines[-1] if stdout_lines else ""
    try:
        summary = json.loads(last_line)
    except ValueError as exc:
        raise QualityGateError(
            f"could not parse a JSON summary line from {script} (exit code {proc.returncode}): {exc}\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        ) from exc
    return summary


def evaluate(agent: str, candidate: Optional[str] = None) -> Dict[str, Any]:
    """The gate itself. See module docstring for why this re-derives
    PASS/FAIL from the raw summary rather than trusting
    run_acceptance_gate.py's own (fixed-threshold) `overall` field."""
    config = load_gate_config(agent)
    threshold = float(config["scenario_threshold"])
    summary = run_acceptance_gate(agent)

    scenario_rate = summary.get("scenarios", {}).get("rate", 0.0)
    scenario_ok = scenario_rate >= threshold
    security_ok = summary.get("security_checks", {}).get("result") == "PASS"
    gate_checks_ok = summary.get("gate_checks", {}).get("result") == "PASS"
    overall_ok = scenario_ok and security_ok and gate_checks_ok

    return {
        "agent": agent,
        "candidate": candidate,
        "scenario_rate": scenario_rate,
        "scenario_threshold": threshold,
        "scenario_ok": scenario_ok,
        "security_ok": security_ok,
        "gate_checks_ok": gate_checks_ok,
        "overall": "PASS" if overall_ok else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0107 model/agent promotion quality gate")
    parser.add_argument("--agent", required=True, help="agent name, e.g. tekos (must have evaluations/<agent>/)")
    parser.add_argument(
        "--candidate", default=None, help="informational label for this candidate/run (e.g. a model tag or commit SHA)"
    )
    args = parser.parse_args()

    try:
        result = evaluate(args.agent, args.candidate)
    except QualityGateError as exc:
        print(f"QUALITY GATE ERROR: {exc}", file=sys.stderr)
        return 2

    label = f" candidate={result['candidate']!r}" if result["candidate"] else ""
    print(f"Quality gate for agent={result['agent']!r}{label}")
    print(
        f"  scenarios: {result['scenario_rate']:.0%} "
        f"(threshold {result['scenario_threshold']:.0%}) -> {'PASS' if result['scenario_ok'] else 'FAIL'}"
    )
    print(f"  security_checks: {'PASS' if result['security_ok'] else 'FAIL'} (100% mandatory)")
    print(f"  gate_checks: {'PASS' if result['gate_checks_ok'] else 'FAIL'} (100% mandatory)")
    print(f"OVERALL: {result['overall']}")
    print(json.dumps(result))

    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
