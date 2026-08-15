#!/usr/bin/env python3
"""Thin AGENT=naveo wrapper around the canonical, shared
evaluations/tekos/run_scenarios.py (ADR-0342). Sets AGENT (and this
file's own directory takes over as the scenarios.yaml source) before
delegating to its main().

Run directly:

    cd evaluations/naveo && python3 run_scenarios.py
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("AGENT", "naveo")
os.environ.setdefault("TASK_NAME", "answer-onboarding-question")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))

from run_scenarios import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
