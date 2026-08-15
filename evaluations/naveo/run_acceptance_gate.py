#!/usr/bin/env python3
"""Thin AGENT=naveo wrapper around the canonical, shared
evaluations/tekos/run_acceptance_gate.py (ADR-0342). Combines this
directory's scenarios.yaml/security_checks.py with the shared
run_scenarios.py/gate_checks.py into one gate, one exit code.

NOT wired into the automatic `make day1|d1 check agents` path yet - the
human review checkpoint WP-41's own brief gates on comes first.

Run directly:

    cd evaluations/naveo && python3 run_acceptance_gate.py
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("AGENT", "naveo")
os.environ.setdefault("TASK_NAME", "answer-onboarding-question")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))

from run_acceptance_gate import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
