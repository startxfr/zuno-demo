#!/usr/bin/env python3
"""ADR-0058: per-agent Day 2 stresstest entrypoint, run inside the
generalized per-agent Job (ansible/roles/day2/tasks/stresstest_job.yml).
The Job is recreated once per agent (not looped internally) - AGENT names
which one this particular run is for, set by the Ansible task loop the
same way evaluations/<agent>/run_scenarios.py's thin wrappers already set
it (ADR-0342/WP-31).

Best-effort runs whichever of these layers apply to AGENT, normalizing
every result into platform/testing/day2_report.py::Day2Result:
  - run_scenarios.py    - every agent (the shared, AGENT-parameterized
                           acceptance-scenario runner).
  - security_checks.py  - every agent, dynamically loaded the same way
                           evaluations/tekos/run_acceptance_gate.py's own
                           _load_security_checks() already does (a static
                           top-level import would only ever resolve to
                           whichever agent's module sys.path finds first).
  - gate_checks.py       - Tekos only (no other agent has this file or a
                           wrapper for it - see ADR-0058's Context).
  - stress_test.py       - whichever agents have one (Tekos, and, as of
                           ADR-0415's image-generation coverage, Arkos),
                           dynamically loaded the same way security_checks.py
                           already is above.
An agent missing a given layer's file gets one explicit "coverage" row
instead of a failure - ADR-0058 decision 1's informational, non-blocking
posture.

Prints one JSON array of Day2Result-shaped dicts to stdout. The calling
Ansible task fetches this Job's pod log and folds it into the overall
cross-agent report, rendered on the control node by
platform/testing/day2_report.py - the same split
ansible/tasks/day2_availability_check.yml and
ansible/roles/day2/tasks/platform_health_check.yml already use.

Contract tests (platform/okf/run_agent_contract_tests.py) are
deliberately NOT run here: that script has no per-agent hook and needs no
cluster access at all, so it runs once, directly from the control node
(platform/testing/day2_contract_attribution.py) - running it once per
agent inside this Job would just repeat the same whole-repo scan six
times for no benefit.

Bulk-interaction load mode (ADR-0058 decision 3) is a separate script,
platform/testing/day2_bulk.py, invoked by the same Job when
BULK_INTERACTIONS is set and > 0 - kept separate so a plain stresstest
run (no bulk mode) never pays for it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
from dataclasses import asdict
from typing import List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from day2_report import Day2Result  # noqa: E402

AGENT = os.getenv("AGENT", "tekos")
# .parent.resolve(), NOT .resolve().parent: the Job mounts this file at
# /gate/day2_stresstest.py as a ConfigMap symlink
# (/gate/day2_stresstest.py -> ..data/day2_stresstest.py -> the
# ConfigMap's own internal timestamped directory). .resolve() on __file__
# itself follows that chain all the way through, landing SCRIPT_DIR
# inside the ConfigMap's private directory - which has no idea that
# /gate/<agent>/ is a SEPARATE volume mounted alongside it, not nested
# inside it. Live-cluster-confirmed 2026-08-23: this silently made
# _load_security_checks()/_load_stress_test() report "not found" for
# every agent, always, whenever run via the Job (never when run
# standalone against a real repo checkout, which is why this went
# unnoticed). Resolving only the parent (a real mountpoint directory,
# never itself a symlink) keeps SCRIPT_DIR at the mount point instead.
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()


def _load_security_checks():
    """Mirrors evaluations/tekos/run_acceptance_gate.py's own
    _load_security_checks(): registers the module in sys.modules before
    exec_module() runs, since security_checks.py's @dataclass needs
    sys.modules[cls.__module__] to already resolve to something.
    """
    path = SCRIPT_DIR / AGENT / "security_checks.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("security_checks", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_run(layer: str, fn) -> List[Day2Result]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a layer erroring is one failed row, not a crashed script
        return [Day2Result(AGENT, layer, "error", "error", False, f"unhandled error: {exc}")]


def _scenario_results() -> List[Day2Result]:
    import run_scenarios

    return [
        Day2Result(AGENT, "scenario", str(r.id), "acceptance", r.passed, r.detail)
        for r in run_scenarios.run()
    ]


def _security_results() -> List[Day2Result]:
    module = _load_security_checks()
    if module is None:
        return [Day2Result(AGENT, "security", "n/a", "coverage", True, "no security_checks.py for this agent")]
    return [
        Day2Result(AGENT, "security", r.name, "security", r.passed, r.detail)
        for r in module.run()
    ]


def _gate_check_results() -> List[Day2Result]:
    if AGENT != "tekos":
        return [Day2Result(AGENT, "gate", "n/a", "coverage", True, "gate_checks.py is Tekos-only today")]
    import gate_checks

    return [
        Day2Result(AGENT, "gate", r.name, "gate", r.passed, r.detail)
        for r in gate_checks.run()
    ]


def _load_stress_test():
    """Mirrors _load_security_checks() above: dynamically loads THIS
    agent's own stress_test.py when it has one, rather than assuming
    Tekos's fixed module name/path. Not every agent has this file (only
    Tekos and, as of ADR-0415's image-generation coverage, Arkos do) - see
    _stress_test_results()'s "coverage" fallback below for agents that
    don't."""
    path = SCRIPT_DIR / AGENT / "stress_test.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("stress_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stress_test_results() -> List[Day2Result]:
    module = _load_stress_test()
    if module is None:
        return [Day2Result(AGENT, "stress_test", "n/a", "coverage", True, "no stress_test.py for this agent")]
    return [
        Day2Result(AGENT, "stress_test", r.id, r.category, r.passed, r.detail)
        for r in module.run()
    ]


def _quota_results() -> List[Day2Result]:
    """ADR-0511/WP-54: proves Kuadrant actually returns 429 once a demo
    persona crosses a per-class request limit.

    Belongs in the harness rather than staying an operator one-liner
    because the failure mode it guards is invisible from every other
    angle: when the AuthPolicy stops publishing the identity the counter
    expressions read, the wasm-shim skips the rate-limit call and every
    request returns a clean 200, while the RateLimitPolicy still reports
    Accepted+Enforced and Limitador still holds the compiled limits. Only
    driving real traffic past the threshold distinguishes "enforcing" from
    "silently inert" (confirmed live 2026-08-25 - see the WP-54 State log).
    """
    import quota_429

    return quota_429.run()


def _rag_ingestion_results() -> List[Day2Result]:
    """WP-25/ADR-0110: a fast, bounded, read-only proof that
    reconcile-acls's live Confluence listing path is reachable and
    returns real content. Deliberately NOT a full space walk the way
    reconcile-acls itself does - live-cluster-confirmed 2026-08-23: a real
    listing of the "SXSI" space (the one every knowledge.tech Confluence
    source points at) can run for the better part of an hour, unsuitable
    for a recurring stresstest job with a normal timeout. A single
    small-limit, unpaginated CQL request is enough to prove auth +
    connectivity + real content without that cost. Tekos-only - it's the
    one agent whose knowledge.tech domain has Confluence sources
    configured at all.
    """
    if AGENT != "tekos":
        return [
            Day2Result(
                AGENT, "rag_ingestion", "n/a", "coverage", True,
                "reconcile-acls live check is Tekos-only (knowledge.tech domain)",
            )
        ]

    base_url = os.environ.get("CONFLUENCE_URL")
    username = os.environ.get("CONFLUENCE_USERNAME")
    token = os.environ.get("CONFLUENCE_TOKEN")
    if not (base_url and username and token):
        return [
            Day2Result(
                AGENT, "rag_ingestion", "confluence-live-listing", "coverage", True,
                "no CONFLUENCE_URL/CONFLUENCE_USERNAME/CONFLUENCE_TOKEN mounted in this Job",
            )
        ]

    import httpx

    try:
        resp = httpx.get(
            f"{base_url}/wiki/rest/api/content/search",
            params={"cql": 'space="SXSI" and type=page', "limit": 5},
            auth=(username, token),
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        passed = len(results) > 0
        detail = f"{len(results)} real page(s) returned" if passed else "listing succeeded but returned zero pages"
    except Exception as exc:  # noqa: BLE001 - reported as a failed row, not a crash
        passed = False
        detail = f"live listing failed: {exc}"

    return [Day2Result(AGENT, "rag_ingestion", "confluence-live-listing", "connectivity", passed, detail)]


def main() -> int:
    results: List[Day2Result] = []
    results += _safe_run("scenario", _scenario_results)
    results += _safe_run("security", _security_results)
    results += _safe_run("gate", _gate_check_results)
    results += _safe_run("stress_test", _stress_test_results)
    results += _safe_run("rag_ingestion", _rag_ingestion_results)
    results += _safe_run("quota", _quota_results)

    print(json.dumps([asdict(r) for r in results]))

    # This process (not day2_bulk.py, a separate subprocess with its own
    # cleanup call - see that file's own main()) is where scenario,
    # security and stress_test conversations all actually accumulate:
    # run_scenarios/security_checks/stress_test are imported in-process
    # above, each `from run_scenarios import ..., record_run_id`
    # resolving to the SAME cached module object, so one call here covers
    # every layer's created run_ids. Printed to stderr, not stdout - the
    # Ansible task parses stdout lines matching `^\[.*\]$` as this
    # process's one JSON-array result line, and a second matching line
    # here would corrupt that.
    if os.getenv("CLEANUP_TEST_DATA", "1") != "0":
        import run_scenarios

        deleted, failed = run_scenarios.cleanup_created_runs()
        print(f"cleanup: {deleted} conversation(s) removed, {failed} failed", file=sys.stderr)

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
