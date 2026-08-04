#!/usr/bin/env python3
"""Security-negative checks for ADR-0032 (propagate trusted identity end to
end) and ADR-0033 (derive user identity only from validated tokens).

Kept separate from scenarios.yaml/run_scenarios.py rather than added as
scenarios 21+: ADR-0027 fixes Tekos's acceptance suite at exactly 20
scenarios, and these are security-negative checks for a specific pair of
ADRs, not part of that fixed acceptance count. Reuses run_scenarios.py's
token-fetch helpers rather than duplicating them.

This cannot be executed in the sandbox this repo was built in (no live
cluster) - written to be genuinely runnable once one exists, same as
run_scenarios.py.
"""
from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass

import httpx

from run_scenarios import BFF_URL, RUNTIME_URL, auth_headers


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def bff_forwards_identity_to_runtime() -> CheckResult:
    """ADR-0032: the BFF must forward the validated end-user bearer token to
    the Agent Runtime, which requires one (app/auth.py:validate_token) and
    rejects calls without it. Before this ADR's fix, every BFF -> Runtime
    call was unauthenticated and the Runtime would have rejected it with
    401, surfaced to the client as a 502 from the BFF - so a 200 here with a
    real reply is direct evidence the token now reaches the Runtime.
    """
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers("chris"),
        json={"session_id": "sec-check-1", "message": "What GPU does the local model run on?"},
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult(
        "bff_forwards_identity_to_runtime",
        ok,
        f"status={resp.status_code} body={resp.text[:200]}",
    )


def runtime_ignores_mismatched_user_sub() -> CheckResult:
    """ADR-0033: a request body's user_sub is informational only - the
    Runtime must derive the authoritative subject from the validated token,
    not this field. Submitting a token for one real persona (chris) with a
    body user_sub claiming to be an unrelated, nonexistent identity must
    not be rejected or otherwise change the outcome (impersonation via the
    body field is impossible because the field is never trusted).
    """
    forged_sub = f"not-a-real-user-{uuid.uuid4().hex[:8]}"
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers("chris"),
        json={
            "session_id": "sec-check-2",
            "user_sub": forged_sub,
            "message": "What GPU does the local model run on?",
        },
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult(
        "runtime_ignores_mismatched_user_sub",
        ok,
        f"status={resp.status_code} forged_sub={forged_sub} body={resp.text[:200]}",
    )


CHECKS = [
    bff_forwards_identity_to_runtime,
    runtime_ignores_mismatched_user_sub,
]


def main() -> int:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            results.append(CheckResult(check.__name__, False, f"unhandled error: {exc}"))

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
    # auth_headers()/get_token() require TEKOS_FRONTEND_CLIENT_SECRET - see README.md.
    sys.exit(main())
