#!/usr/bin/env python3
"""Thin AGENT=advantage wrapper around the canonical, shared
evaluations/tekos/run_scenarios.py (ADR-0342/WP-35 - see that file's own
module docstring for why the implementation lives there rather than being
copied per agent). Sets AGENT (and this file's own directory takes over
as the scenarios.yaml source, via that module's AGENT-driven path
resolution) before delegating to its main().

Run directly:

    cd evaluations/advantage && python3 run_scenarios.py
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("AGENT", "advantage")
os.environ.setdefault("TASK_NAME", "answer-project-question")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))

from run_scenarios import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
