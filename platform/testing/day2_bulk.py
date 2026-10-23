#!/usr/bin/env python3
"""ADR-0058 decision 3: the bulk-interaction load mode. Given AGENT (set
the same way day2_stresstest.py's Job iteration sets it) and
BULK_INTERACTIONS (a positive integer), replays the chat prompts already
defined in this agent's own scenarios.yaml - every `message:`-bearing
entry, regardless of scenario `type`; that field is common to every
agent's scenarios.yaml per ADR-0027 - and, for Tekos specifically, also
evaluations/tekos/stress_test.py's own per-category prompt lists (a
richer corpus, but Tekos-only since those lists are hardcoded Tekos
content) - cycling through the corpus to reach the requested count. No
new prompt content is authored here (ADR-0058's own scope boundary:
aggregation and execution, not new test-content authoring).

Each call is one UnifAI turn (WP-156: UnifAI serves the agents, ADR-0561),
through the same shared transport evaluations/tekos/run_scenarios.py's
chat_basic_qa handler uses under its default unifai target
(evaluations/common/unifai_target.py: the persona signs in through the
UnifAI UI route and runs the agent's workflow in its team workspace).
pass/fail reuses that same minimal assertion ("got a non-empty reply"),
plus per-call latency is recorded - the execute call only: the workflow is
resolved once and each call's session is created before the clock starts,
so the latency is the agent's, not the session bookkeeping's. Produces one Day2Result summary row
(category="bulk_load") per agent - interaction count, error rate,
p50/p95/max latency - not one row per call, so the report table stays
readable at any BULK size.

Run inside the same per-agent Job as day2_stresstest.py (not a separate
Job): it needs the exact same AGENT/UNIFAI_URL/UNIFAI_TEAM_NAME/
DEMO_PERSONA_PASSWORD env vars and the same mounted unifai_target.py -
duplicating that setup in a second Job would be pure overhead.

Prints a JSON array (usually one summary Day2Result, or none when
BULK_INTERACTIONS is unset/zero) to stdout, same convention as
day2_stresstest.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from dataclasses import asdict
from typing import List, Optional

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from day2_report import Day2Result, log_test_line  # noqa: E402

AGENT = os.getenv("AGENT", "tekos")
BULK_INTERACTIONS = int(os.getenv("BULK_INTERACTIONS", "0") or "0")
# advantage/finage/naveo declare zuno.status: placeholder (ADR-0007/
# ADR-0011/ADR-0040/ADR-0533 - none is promoted to active yet), so UnifAI
# deliberately serves no workflow for them - live-confirmed 2026-09-02 on
# the BFF as a 100% bulk_load error rate at ~30ms latency (an immediate
# policy denial, not a slow backend or a real defect). Set by ansible
# (stresstest_job_run_one.yml) from the admitted release
# (platform/okf/stack-config.generated.yaml); WP-156's stresstest_job.yml
# no longer even creates a Job for a placeholder, this guard keeps a
# standalone run honest.
ZUNO_AGENT_STATUS = os.getenv("ZUNO_AGENT_STATUS", "")
# consultant-01 is a member of agent_comage, agent_tekos and agent_arkos
# (gitops/charts/keycloak/files/realm-zuno.json), so it reaches every
# active agent's team workspace.
PERSONA = os.getenv("STRESS_TEST_PERSONA", "consultant-01")
# Matches the local-provider timeout in platform/ai-gateway/provider-routing.yaml
# (60s). The old hardcoded 30s here made every /api/chat call that took
# longer than that under normal single-replica load count as a hard
# "error" indistinguishable from a real backend failure.
BULK_TIMEOUT_SECONDS = float(os.getenv("BULK_TIMEOUT_SECONDS", "60"))

# .parent.resolve(), not .resolve().parent - same ConfigMap-symlink bug
# and fix as platform/testing/day2_stresstest.py's own SCRIPT_DIR (see
# that file's comment for the full explanation). Live-cluster-confirmed
# 2026-08-23: this silently made _scenario_prompts() always return []
# when run via the Job, which is why bulk_load's result was always the
# "no message-bearing scenario content to replay" coverage fallback
# rather than an actual replay of scenarios.yaml's prompts.
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()


def _scenario_prompts() -> List[str]:
    path = SCRIPT_DIR / AGENT / "scenarios.yaml"
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    return [s["message"] for s in data.get("scenarios", []) if s.get("message")]


def _tekos_stress_test_prompts() -> List[str]:
    if AGENT != "tekos":
        return []
    try:
        import stress_test
    except Exception:  # noqa: BLE001 - missing/broken stress_test.py just yields no extra prompts
        return []
    prompts: List[str] = []
    for group in (
        stress_test.TECHNICAL_QA_PROMPTS,
        stress_test.CONFLUENCE_TRIGGER_PROMPTS,
        stress_test.CODE_GENERATION_PROMPTS,
    ):
        prompts += [message for _, message in group]
    return prompts


_TARGET = None


def _target():
    """The shared UnifAI transport, created on first use. Imported lazily:
    the percentile/corpus helpers below need neither httpx nor a password,
    and the unit tests exercise them without either. Mounted flat next to
    this file in the Job; under evaluations/common/ in the repo."""
    global _TARGET
    if _TARGET is None:
        for candidate in (SCRIPT_DIR, SCRIPT_DIR.parent.parent / "evaluations" / "common"):
            if str(candidate) not in sys.path:
                sys.path.append(str(candidate))
        from unifai_target import UnifaiTarget

        _TARGET = UnifaiTarget(
            os.getenv("DEMO_PERSONA_PASSWORD", ""),
            agent=AGENT,
            team_name=os.getenv("UNIFAI_TEAM_NAME") or f"agent-{AGENT}",
        )
    return _TARGET


def _cleanup_created_runs() -> "tuple[int, int]":
    # Deletes exactly the sessions this process created (UnifaiTarget keeps
    # their ids) - never a sweep of the persona's sessions.
    return _TARGET.cleanup() if _TARGET is not None else (0, 0)


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return sorted_values[index]


def _post_chat(blueprint_id: str, message: str, i: int) -> "tuple[bool, bool, Optional[int], float]":
    """One UnifAI turn in a fresh session. Returns (ok, timed_out, status_code, elapsed_ms).

    UnifaiTarget.run() reports a transport failure as status 599 with the
    exception text, so a timeout is recognised by that text (httpx's
    timeout exceptions all say "timed out"); it is the stream's per-read
    timeout, which heartbeats keep from tripping on a merely slow answer.
    """
    target = _target()
    try:
        session_id = target.create(PERSONA, blueprint_id)
    except Exception:  # noqa: BLE001 - a failed session create counts as one failed interaction
        return False, False, None, 0.0
    start = time.monotonic()
    try:
        run = target.run(PERSONA, message, session_id=session_id, timeout=BULK_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - a call erroring counts as one failed interaction, not a crash
        return False, False, None, (time.monotonic() - start) * 1000
    elapsed_ms = (time.monotonic() - start) * 1000
    if run.status == 599:
        timed_out = "timed out" in str(run.raw.get("error", "")).lower()
        return False, timed_out, None, elapsed_ms
    return run.status == 200 and bool(run.reply), False, run.status, elapsed_ms


def run() -> List[Day2Result]:
    if BULK_INTERACTIONS <= 0:
        return []
    if ZUNO_AGENT_STATUS == "placeholder":
        return [Day2Result(
            AGENT, "bulk_load", "n/a", "coverage", True,
            "bulk_load skipped - zuno.status: placeholder (not yet "
            "promoted, ADR-0007/ADR-0011/ADR-0040/ADR-0533); UnifAI serves "
            "no workflow for it by design, not a backend failure",
        )]

    corpus = _scenario_prompts() + _tekos_stress_test_prompts()
    if not corpus:
        return [Day2Result(
            AGENT, "bulk_load", "n/a", "coverage", True,
            "no message-bearing scenario content to replay",
        )]

    try:
        blueprint_id = _target().workflow_id(PERSONA)
    except Exception as exc:  # noqa: BLE001 - no workflow to drive is one failed row, not a crash
        return [Day2Result(AGENT, "bulk_load", "summary", "bulk_load", False, f"cannot resolve {AGENT}'s UnifAI workflow as {PERSONA}: {exc}")]

    latencies: List[float] = []
    errors = 0
    timeouts = 0
    for i in range(BULK_INTERACTIONS):
        message = corpus[i % len(corpus)]
        ok, timed_out, status_code, elapsed_ms = _post_chat(blueprint_id, message, i)
        if not ok and timed_out:
            # One retry on a bare timeout absorbs a single slow response
            # instead of counting normal single-replica backend latency
            # as a hard failure.
            ok, timed_out, status_code, retry_ms = _post_chat(blueprint_id, message, i)
            elapsed_ms += retry_ms
        latencies.append(elapsed_ms)
        if not ok:
            errors += 1
            if timed_out:
                timeouts += 1
        log_test_line(
            AGENT, "bulk_load", str(i), f"call {i + 1}/{BULK_INTERACTIONS}", ok,
            f"status={status_code}" if status_code is not None else "status=timeout",
        )

    latencies.sort()
    error_rate = errors / BULK_INTERACTIONS
    detail = (
        f"count={BULK_INTERACTIONS} errors={errors} (timeouts={timeouts}) "
        f"error_rate={error_rate:.1%} "
        f"p50={_percentile(latencies, 0.50):.0f}ms p95={_percentile(latencies, 0.95):.0f}ms "
        f"max={max(latencies):.0f}ms"
    )
    return [Day2Result(AGENT, "bulk_load", "summary", "bulk_load", error_rate == 0.0, detail)]


def main() -> int:
    results = run()
    print(json.dumps([asdict(r) for r in results]))

    # day2_bulk.py always runs as its own subprocess (see this file's own
    # module docstring: "Run inside the same per-agent Job... [but] not a
    # separate Job" refers to sharing the Job/container, not the process -
    # the shell command invokes it as a second `python3` after
    # day2_stresstest.py exits), so its own _CREATED_RUN_IDS is never
    # shared with that other process - needs its own cleanup call.
    if os.getenv("CLEANUP_TEST_DATA", "1") != "0":
        deleted, failed = _cleanup_created_runs()
        print(f"cleanup: {deleted} conversation(s) removed, {failed} failed", file=sys.stderr)

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
