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

Each call goes through the same BFF /api/chat path
evaluations/tekos/run_scenarios.py's chat_basic_qa handler already uses;
pass/fail reuses that same minimal assertion ("got a non-empty reply"),
plus per-call latency is recorded. Produces one Day2Result summary row
(category="bulk_load") per agent - interaction count, error rate,
p50/p95/max latency - not one row per call, so the report table stays
readable at any BULK size.

Run inside the same per-agent Job as day2_stresstest.py (not a separate
Job): it needs the exact same AGENT/<AGENT>_FRONTEND_CLIENT_SECRET/
DEMO_PERSONA_PASSWORD env vars and the same mounted run_scenarios.py
(reused here for its token-fetch helper) - duplicating that setup in a
second Job would be pure overhead.

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
from typing import Dict, List, Optional

import httpx
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from day2_report import Day2Result, log_test_line  # noqa: E402

AGENT = os.getenv("AGENT", "tekos")
BULK_INTERACTIONS = int(os.getenv("BULK_INTERACTIONS", "0") or "0")
BFF_URL = os.getenv("BFF_URL", f"http://{AGENT}-bff.zuno-ai-run.svc.cluster.local:8080")
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


def _auth_headers() -> Dict[str, str]:
    # Reuses run_scenarios.py's own ROPC token-fetch helper (mounted
    # alongside this file) instead of duplicating that grant logic.
    import run_scenarios

    return run_scenarios.auth_headers(PERSONA)


def _cleanup_created_runs() -> "tuple[int, int]":
    # Imported lazily, same reasoning as _auth_headers() above - avoids a
    # hard import-time dependency for callers that never invoke this.
    import run_scenarios

    return run_scenarios.cleanup_created_runs()


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return sorted_values[index]


def _post_chat(headers: Dict[str, str], message: str, i: int) -> "tuple[bool, bool, Optional[int], float]":
    """One /api/chat call. Returns (ok, timed_out, status_code, elapsed_ms)."""
    import run_scenarios

    start = time.monotonic()
    try:
        resp = httpx.post(
            f"{BFF_URL}/api/chat",
            headers=headers,
            json={"session_id": f"day2-bulk-{AGENT}-{i}", "message": message},
            timeout=BULK_TIMEOUT_SECONDS,
        )
        body = resp.json() if resp.status_code == 200 else {}
        if resp.status_code == 200:
            run_scenarios.record_run_id(PERSONA, body)
        ok = resp.status_code == 200 and bool(body.get("reply"))
        return ok, False, resp.status_code, (time.monotonic() - start) * 1000
    except httpx.TimeoutException:
        return False, True, None, (time.monotonic() - start) * 1000
    except Exception:  # noqa: BLE001 - a call erroring counts as one failed interaction, not a crash
        return False, False, None, (time.monotonic() - start) * 1000


def run() -> List[Day2Result]:
    if BULK_INTERACTIONS <= 0:
        return []

    corpus = _scenario_prompts() + _tekos_stress_test_prompts()
    if not corpus:
        return [Day2Result(
            AGENT, "bulk_load", "n/a", "coverage", True,
            "no message-bearing scenario content to replay",
        )]

    headers = _auth_headers()
    latencies: List[float] = []
    errors = 0
    timeouts = 0
    for i in range(BULK_INTERACTIONS):
        message = corpus[i % len(corpus)]
        ok, timed_out, status_code, elapsed_ms = _post_chat(headers, message, i)
        if not ok and timed_out:
            # One retry on a bare timeout absorbs a single slow response
            # instead of counting normal single-replica backend latency
            # as a hard failure.
            ok, timed_out, status_code, retry_ms = _post_chat(headers, message, i)
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
