#!/usr/bin/env python3
"""Thin AGENT=finage wrapper around the canonical, shared
evaluations/tekos/run_acceptance_gate.py (ADR-0342/WP-36). Combines this
directory's scenarios.yaml/security_checks.py with the shared
run_scenarios.py/gate_checks.py into one gate, one exit code - see the
canonical module's own docstring for the full layer breakdown.

NOT wired into the automatic `make day1|d1 check agents` path yet
(ansible/roles/agents/tasks/check.yml) - WP-36 part (c)'s scenarios
require a human review checkpoint before any run of this script against a
live cluster counts (see this directory's own README.md). Intended for
the operator to run explicitly once that review has happened.

Run directly:

    cd evaluations/finage && python3 run_acceptance_gate.py
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("AGENT", "finage")
os.environ.setdefault("TASK_NAME", "answer-finance-question")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))

from run_acceptance_gate import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
