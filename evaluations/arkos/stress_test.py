#!/usr/bin/env python3
"""Exploratory stress test for Arkos's image-generation capability
(ADR-0415's `generate_image` tool, declared by both
`draft-architecture-testimonial` and `workshop-presentation` -
`agents/arkos/tasks/*.md`).

Mirrors `evaluations/tekos/stress_test.py`'s structure (`StressResult`,
`_safe`, `run()`/`main()`) but is a POSITIVE check instead of that file's
negative boundary probes: Tekos never declares `generate_image`, so its
own `IMAGE_GENERATION_PROMPTS`/`check_image_generation_boundary` assert the
opposite of what this file asserts. This is the first live coverage of the
`generate_image` dispatch path for any agent - previously untested anywhere
(components/agent-runtime/tests/test_arkos_nodes.py now covers the node
logic itself with mocks; this covers the real end-to-end call).

Written after a real incident: a user's "can you generate an image of the
openshift operator" request crashed with LangGraph's own "Must write to at
least one of [...]" error - `app/graph/arkos_nodes.py:reflect_node` returned
an empty `{}` when `draft_node`'s image-generation follow-up reply came back
as an empty string. `bare_request` below reproduces that exact prompt; a
`status_code != 200` result on it is precisely what that bug looked like
from the caller's side.

Deliberately NOT wired into run_acceptance_gate.py / ADR-0053's mandatory
gate, same posture as Tekos's own stress_test.py - this exercises live model
output (an image was actually generated), not a cheap deterministic check.

This cannot be executed in the sandbox this repo was built in without a
live cluster - see README.md for required environment variables, the same
ones run_scenarios.py/security_checks.py already need.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass
from typing import List

import httpx

# Must be set before importing run_scenarios below - its AGENT constant is
# resolved at import time (os.getenv("AGENT", "tekos")), and a bare
# `python3 stress_test.py` run (this file's own README-documented
# invocation) has nothing else setting it - mirrors security_checks.py's
# own os.environ.setdefault() for the same reason.
os.environ.setdefault("AGENT", "arkos")

# Shared implementation lives in evaluations/tekos/ (ADR-0342/WP-31) -
# evaluations/arkos/run_scenarios.py inserts it onto sys.path the same way;
# this file needs the same helpers so it does the same, rather than
# importing evaluations/arkos/run_scenarios.py itself (whose own main()
# entrypoint isn't what's needed here).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, RUNTIME_URL, auth_headers  # noqa: E402

PERSONA = "consultant-01"


@dataclass
class StressResult:
    id: str
    category: str
    title: str
    passed: bool
    detail: str = ""


def _safe(id_: str, category: str, title: str, fn, *args) -> StressResult:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
        return StressResult(id_, category, title, False, f"unhandled error: {exc}")


# --------------------------------------------------------------------------
# Category: image_generation - proves the generate_image tool actually
# produces an image end to end, through Arkos's real plan/retrieve/draft/
# reflect/write shape.
# --------------------------------------------------------------------------

IMAGE_GENERATION_PROMPTS = [
    # The literal prompt from the reported incident.
    ("bare_request", "Can you generate an image of the OpenShift Operator?"),
    # ADR-0415's actual intended use case: an image embedded within a
    # document draft, not a standalone ask.
    ("dat_with_diagram", "Draft a DAT for the OpenShift AI GPU sizing project, including an architecture diagram."),
]


def check_image_generation(case: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-img-{case}", "user_sub": PERSONA, "message": message},
        # DAT-drafting-shape timeout - draft_node chains a drafting call, an
        # image-generation tool call and a follow-up call, then reflect_node
        # makes a fourth call; see evaluations/arkos/scenarios.yaml scenario
        # 7/10's own comment on this same timeout.
        timeout=180,
    )
    if resp.status_code != 200:
        return StressResult(f"img-{case}", "image_generation", message, False, f"status={resp.status_code}")
    body = resp.json()
    images = body.get("images", [])
    ok = bool(images)
    return StressResult(
        f"img-{case}", "image_generation", message, ok,
        f"images={len(images)} reply_snippet={body.get('reply', '')[:200]!r}",
    )


# --------------------------------------------------------------------------

def run() -> List[StressResult]:
    results: List[StressResult] = []

    for case, message in IMAGE_GENERATION_PROMPTS:
        results.append(_safe(f"img-{case}", "image_generation", message, check_image_generation, case, message))

    return results


def main() -> int:
    results = run()

    print(f"{'ID':<20}{'PASS':<6}{'CATEGORY':<20}{'TITLE'}")
    for r in results:
        print(f"{r.id:<20}{'✓' if r.passed else '✗':<6}{r.category:<20}{r.title}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    total_passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{total_passed}/{total} passed overall")
    print(
        "\nNOTE: this is an exploratory stress-test battery, not part of "
        "run_acceptance_gate.py / ADR-0053's mandatory gate."
    )

    return 0 if total_passed == total else 1


if __name__ == "__main__":
    # auth_headers()/get_token() require ARKOS_FRONTEND_CLIENT_SECRET and
    # DEMO_PERSONA_PASSWORD - see README.md.
    sys.exit(main())
