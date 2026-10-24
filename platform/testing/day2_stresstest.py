#!/usr/bin/env python3
"""ADR-0058: per-agent Day 2 stresstest entrypoint, run inside the
generalized per-agent Job (ansible/roles/day3/tasks/stresstest_job.yml).
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
  - stress_test          - not run: one explicit "coverage" row (see below).
An agent missing a given layer's file gets one explicit "coverage" row
instead of a failure - ADR-0058 decision 1's informational, non-blocking
posture.

WP-156: the agents are served by UnifAI (ADR-0561), the only evaluation
target. run_scenarios.py and security_checks.py sign the personas in
through the UnifAI UI route (evaluations/common/unifai_target.py); the Job
passes UNIFAI_URL, UNIFAI_TEAM_NAME and DEMO_PERSONA_PASSWORD. The
per-agent stress_test.py batteries (Tekos, Arkos, Comage) posted to the
retired agent stack's chat endpoints directly and were deleted with it; no
UnifAI port exists yet, so the stress_test layer reports one "NOT RUN"
coverage row per agent instead. The rag_ingestion layer (WP-25/ADR-0110's
live Confluence listing) is gone with rag-ingestion: UnifAI's RAG syncs
Confluence itself (ADR-0568), and its sources are checked by UnifAI, not
here.

Prints one JSON array of Day2Result-shaped dicts to stdout. The calling
Ansible task fetches this Job's pod log and folds it into the overall
cross-agent report, rendered on the control node by
platform/testing/day2_report.py - the same split
ansible/tasks/day2_availability_check.yml and
ansible/roles/day2/tasks/platform_health_check.yml already use.

The contract layer is deliberately NOT run here: since WP-165 the
contract suites run in the zuno-demo-agents CI and reach this platform as
a signed attestation of the admitted release, which needs no cluster
access, so it is reported once from the control node
(platform/testing/day2_contract_attribution.py).

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
# _load_security_checks() report "not found" for
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
    # A check that cannot apply (unifai_checks.skip, delegation_checks) carries `skipped`: it is
    # reported as NOT RUN in the coverage category, never as a pass of the security layer and
    # never as a failure of the run - the same convention as the retired layers below.
    return [
        Day2Result(AGENT, "security", r.name, "coverage", True, f"NOT RUN: {r.detail}")
        if getattr(r, "skipped", False)
        else Day2Result(AGENT, "security", r.name, "security", r.passed, r.detail)
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


def _stress_test_results() -> List[Day2Result]:
    # WP-156: the stress_test.py batteries drove the retired agent stack's
    # chat endpoints directly and were deleted with it. Reported, never
    # silently dropped, until a UnifAI port exists; nothing is loaded, so a
    # stale stress_test.py left in a mounted ConfigMap cannot run either.
    return [Day2Result(
        AGENT, "stress_test", "n/a", "coverage", True,
        "NOT RUN: the stress_test.py batteries drove the retired agent stack and are not ported to UnifAI yet (WP-156)",
    )]


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
    # WP-156 removed the per-agent quota-demo HTTPRoutes this proof drove
    # (with the retired agent stack, by user decision), so every request now
    # answers 404. The request-rate proof is reported as not run, never
    # silently dropped, until it targets a live route again; token budgets
    # are still proven below.
    return [Day2Result(
        AGENT, "quota", "n/a", "quota", True,
        "NOT RUN: the quota-demo route this request-rate proof drove was removed with the retired agent stack (WP-156)",
    )]


def _token_quota_results() -> List[Day2Result]:
    """ADR-0555/WP-142: the token-BUDGET counterpart to _quota_results()'s
    request-RATE proof - drives real short chat calls, tagged
    X-Zuno-Quota-Class: stresstest, past the dedicated `stresstest` class's
    deliberately tiny per-user token budget (policies/quotas/quota-
    policy.yaml) and asserts the resulting AI Gateway 429 as the expected,
    positive result. See platform/testing/token_quota_429.py's own header
    comment for why this targets AI Gateway's own ledger rather than RHOAI
    MaaS's Kuadrant TokenRateLimitPolicy (currently unreachable by persona
    traffic on this cluster - a separate, documented gap).
    """
    import token_quota_429

    return token_quota_429.run()


def main() -> int:
    results: List[Day2Result] = []
    results += _safe_run("scenario", _scenario_results)
    results += _safe_run("security", _security_results)
    results += _safe_run("gate", _gate_check_results)
    results += _safe_run("stress_test", _stress_test_results)
    results += _safe_run("quota", _quota_results)
    results += _safe_run("token_quota", _token_quota_results)

    print(json.dumps([asdict(r) for r in results]))

    # This process (not day2_bulk.py, a separate subprocess with its own
    # cleanup call - see that file's own main()) is where scenario and
    # security conversations actually accumulate: run_scenarios and
    # security_checks are imported in-process above, each resolving to the
    # SAME cached run_scenarios module, whose shared UnifaiTarget (only when
    # one was created) holds every UnifAI session they opened - so one call
    # here covers every layer.
    # Printed to stderr, not stdout - the Ansible task parses stdout lines
    # matching `^\[.*\]$` as this process's one JSON-array result line,
    # and a second matching line here would corrupt that.
    if os.getenv("CLEANUP_TEST_DATA", "1") != "0":
        import run_scenarios

        deleted = failed = 0
        if run_scenarios._unifai_target is not None:
            deleted, failed = run_scenarios._unifai_target.cleanup()
        print(f"cleanup: {deleted} conversation(s) removed, {failed} failed", file=sys.stderr)

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
