#!/usr/bin/env python3
"""Layered acceptance-gate capability checks required by ADR-0053 that are
neither part of the fixed 20-scenario Tekos acceptance count (ADR-0027 -
scenarios.yaml/run_scenarios.py) nor security-negative checks tied to a
specific identity/classification ADR (security_checks.py). ADR-0053's own
Decision text names "local model inference" and "permitted SaaS fallback"
as checks `make check` must run; local model inference is already proven
live by scenarios 8/9 (a real token stream from the always-preferred local
provider), so the one genuine gap this file closes is "permitted SaaS
fallback" - config-consistency only, no live cluster needed, same style
and for the same reason as run_scenarios.py's model_router_fails_closed/
model_router_prefers_local: proving a live SaaS *fallback* would require
deliberately breaking the local model's availability, which a `make check`
gate has no safe way to do and shouldn't attempt.

Like security_checks.py, every check here is mandatory (100%) - these are
capability guarantees ADR-0053 requires, not part of the 75% quality
threshold reserved for the fixed 20 scenarios.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

import yaml


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def c2_permits_saas_fallback_when_not_local_only() -> CheckResult:
    """ADR-0053 "permitted SaaS fallback": unlike C3 (local-only, see
    run_scenarios.py's model_router_fails_closed), C2 must remain able to
    fall back to an approved SaaS provider when nothing source-level
    (ADR-0035's X-Zuno-Local-Only, e.g. Confluence content - see
    security_checks.py's confluence_policy_is_c2_and_local_only and
    ai_gateway_local_only_forces_local_provider) forces local-only. This
    checks platform/ai-gateway/provider-routing.yaml directly, the same
    config components/ai-gateway/app/routing.py's RoutingTable.candidates_for
    loads at runtime.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    routing = yaml.safe_load((repo_root / "platform/ai-gateway/provider-routing.yaml").read_text())
    providers = routing.get("providers", [])
    saas_c2_providers = [p["name"] for p in providers if p.get("kind") == "saas" and "C2" in p.get("eligible_for", [])]
    ok = len(saas_c2_providers) > 0
    return CheckResult(
        "c2_permits_saas_fallback_when_not_local_only",
        ok,
        f"C2-eligible SaaS providers={saas_c2_providers}",
    )


CHECKS = [
    c2_permits_saas_fallback_when_not_local_only,
]


def run() -> list[CheckResult]:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            results.append(CheckResult(check.__name__, False, f"unhandled error: {exc}"))
    return results


def main() -> int:
    results = run()
    print(f"{'PASS':<6}{'CHECK'}")
    for r in results:
        print(f"{'✓' if r.passed else '✗':<6}{r.name}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    if all(r.passed for r in results):
        print("\nRESULT: PASS")
        return 0
    print("\nRESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
