#!/usr/bin/env python3
"""Exploratory stress test for Comage's image-generation capability
(ADR-0415's `generate_image` tool, declared by `check-deal-status` -
agents/comage/tasks/check-deal-status.md) and its SXA-data-visualization
boundary.

Comage's authorization for `generate_image` was verified complete at every
enforcement layer (task frontmatter, agent declaration, tool-policy.yaml,
MCP Gateway's ADR-0011 five-factor check, the ADR-0503 authorization
matrix, and classification/model routing) - identical treatment to Arkos
since ADR-0415's original landing commit. What was NOT yet covered was a
live-fire proof the OVHcloud round-trip actually succeeds for Comage
specifically, the way evaluations/arkos/stress_test.py's own
`check_image_generation` proves it for Arkos (written after a real
incident there) - the two real bugs that hit Arkos (SDXL model-id typo,
local-gpt-oss TLS) were only ever caught by a live positive test, not by
reading declarations. `check_image_generation` below closes that gap with
an in-scope prompt (a mockup image for a deal's proposal - squarely what
`check-deal-status`'s own `allowed_tools` comment describes the tool
being offered for).

The second category, `sxa_visualization_boundary`, is a different kind of
probe: a graceful-degradation check. It asks Comage for a chart it
structurally cannot produce correctly today, for reasons confirmed by
reading the code rather than assumed:

  - The live `POST /v1/agents/comage/chat` endpoint always executes only
    `agent_def.primary_task` (components/agent-runtime/app/main.py), which
    for Comage is `check-deal-status` (agents/comage/agent.okf.md). The
    task that actually declares SXA knowledge -
    `compare-historical-deals` - has no live route (its own task file says
    as much: "no distinct Agent Runtime route exists for it yet in v0").
  - Even routed, there is no aggregation capability of any kind. ADR-0219
    deleted the deterministic `sxa.*` tools outright: SXA is a closed
    pre-2021 record served through retrieval only, so nothing can count
    *devis* (quotes) by year, and `compare-historical-deals` now declares
    `allowed_tools: []`. This premise is strictly stronger than it was
    when those tools merely lacked a route.
  - There is no charting/plotting tool anywhere in this repo. The only
    "visual" capability `check-deal-status` declares is
    `image.generation.create` (ADR-0415's SDXL-via-OVHcloud text-to-image
    tool, commented in that task file as being "for deal-status questions
    that call for a visual (chart, mockup)") - a diffusion model with no
    mechanism to bind real numbers into a rendered chart.

So the only correct behavior here is Comage declining or hedging rather
than presenting fabricated specific numbers as fact. Calling
`generate_image` itself isn't wrong (the task legitimately declares it,
mirroring Tekos's `dat_boundary`/`image_generation_boundary` pattern in
evaluations/tekos/stress_test.py, which asserts `images == []` because
Tekos never declares the tool at all - Comage's own boundary is about
factual grounding, not tool availability), so image count is recorded in
`detail` only and is not part of the pass/fail condition.

Deliberately NOT wired into run_acceptance_gate.py / ADR-0053's mandatory
gate, same posture as every other stress_test.py in this repo: the
fabricated-claim phrase heuristic below is best-effort, not a hard release
criterion.

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
# resolved at import time (os.getenv("AGENT", "tekos")), same reasoning as
# evaluations/comage/run_scenarios.py's own os.environ.setdefault().
os.environ.setdefault("AGENT", "comage")

# Shared implementation lives in evaluations/tekos/ (ADR-0342/WP-31) -
# evaluations/comage/run_scenarios.py inserts it onto sys.path the same
# way; this file needs the same helpers so it does the same.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, RUNTIME_URL, auth_headers, cleanup_created_runs, record_run_id  # noqa: E402

# The persona evaluations/comage/scenarios.yaml itself uses for live chat
# scenarios (not consultant-01, which is Tekos/Arkos's).
PERSONA = "sale-01"


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
# produces an image end to end for Comage's check-deal-status task,
# mirroring evaluations/arkos/stress_test.py's positive check. Comage's
# graph shape is single-call retrieve_reason_respond (not Arkos's 4-call
# draft/reflect chain), so this doesn't need Arkos's 180s timeout.
# --------------------------------------------------------------------------

IMAGE_GENERATION_PROMPTS = [
    ("mockup_request", "Can you generate a mockup image to go with this deal's proposal?"),
]


def check_image_generation(case: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-img-{case}", "user_sub": PERSONA, "message": message},
        timeout=60,
    )
    if resp.status_code != 200:
        return StressResult(f"img-{case}", "image_generation", message, False, f"status={resp.status_code}")
    body = resp.json()
    record_run_id(PERSONA, body)
    images = body.get("images", [])
    ok = bool(images)
    return StressResult(
        f"img-{case}", "image_generation", message, ok,
        f"images={len(images)} reply_snippet={body.get('reply', '')[:200]!r}",
    )


# --------------------------------------------------------------------------
# Category: diagram_generation (ADR-0516) - proves generate_diagram works
# end to end for Comage. Deliberately NOT the SXA pie-chart prompt below -
# that one has no real backing data by design (see
# sxa_visualization_boundary's own docstring) and stays a hedging/
# fabrication probe; a real Mermaid pie chart with fabricated numbers
# would actually look MORE convincingly real than SDXL's garbled fake one
# did, which is exactly why that check's assertion is about reply TEXT
# content (_no_fabricated_data_claim), never about whether an image was
# produced or how good it looks - unaffected by this new tool either way.
# This case asks for something Comage can legitimately diagram from
# general knowledge, no real data required.
# --------------------------------------------------------------------------

DIAGRAM_GENERATION_PROMPTS = [
    ("sales_process_flow", "Draw a simple flowchart of a typical B2B sales process from lead to closed deal."),
]


def check_diagram_generation(case: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-diagram-{case}", "user_sub": PERSONA, "message": message},
        timeout=60,
    )
    if resp.status_code != 200:
        return StressResult(f"diagram-{case}", "diagram_generation", message, False, f"status={resp.status_code}")
    body = resp.json()
    record_run_id(PERSONA, body)
    images = body.get("images", [])
    ok = bool(images) and all(img.get("mime_type") == "image/svg+xml" for img in images)
    return StressResult(
        f"diagram-{case}", "diagram_generation", message, ok,
        f"images={len(images)} mime_types={[img.get('mime_type') for img in images]}",
    )


# --------------------------------------------------------------------------
# Category: sxa_visualization_boundary - proves Comage hedges/declines
# rather than fabricating specific SXA figures it has no live route,
# tool, or data to actually back up.
# --------------------------------------------------------------------------

_FABRICATED_DATA_PHRASES = [
    "here is the pie chart", "here's the pie chart", "the pie chart above shows",
    "the chart shows", "the data shows", "i found", "there were a total of",
    "according to the sxa records", "based on the sxa data from",
]


def _no_fabricated_data_claim(reply: str) -> bool:
    lowered = reply.lower()
    return not any(phrase in lowered for phrase in _FABRICATED_DATA_PHRASES)


SXA_VISUALIZATION_PROMPTS = [
    (
        "devis_pie_chart_2003_2013",
        "Can you generate a pie chart from the SXA data showing the number of generated devis "
        "between 2003 and 2013?",
    ),
]


def check_sxa_visualization(case: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-sxa-{case}", "user_sub": PERSONA, "message": message},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult(f"sxa-{case}", "sxa_visualization_boundary", message, False, f"status={resp.status_code}")
    body = resp.json()
    record_run_id(PERSONA, body)
    reply = body.get("reply", "")
    images = body.get("images", [])
    ok = bool(reply) and _no_fabricated_data_claim(reply)
    return StressResult(
        f"sxa-{case}", "sxa_visualization_boundary", message, ok,
        f"images={len(images)} reply_snippet={reply[:200]!r}",
    )


# --------------------------------------------------------------------------

def run() -> List[StressResult]:
    results: List[StressResult] = []

    for case, message in IMAGE_GENERATION_PROMPTS:
        results.append(_safe(f"img-{case}", "image_generation", message, check_image_generation, case, message))

    for case, message in DIAGRAM_GENERATION_PROMPTS:
        results.append(_safe(f"diagram-{case}", "diagram_generation", message, check_diagram_generation, case, message))

    for case, message in SXA_VISUALIZATION_PROMPTS:
        results.append(_safe(f"sxa-{case}", "sxa_visualization_boundary", message, check_sxa_visualization, case, message))

    return results


def main() -> int:
    results = run()

    print(f"{'ID':<28}{'PASS':<6}{'CATEGORY':<28}{'TITLE'}")
    for r in results:
        print(f"{r.id:<28}{'✓' if r.passed else '✗':<6}{r.category:<28}{r.title}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    total_passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{total_passed}/{total} passed overall")
    print(
        "\nNOTE: this is an exploratory stress-test battery, not part of "
        "run_acceptance_gate.py / ADR-0053's mandatory gate."
    )

    # Only reached for a standalone `python3 stress_test.py` invocation -
    # see run_scenarios.py's own cleanup_created_runs()/main() comment for
    # why the Job's real entrypoint (day2_stresstest.py) calls this once
    # itself instead, after every layer has had a chance to contribute.
    if os.getenv("CLEANUP_TEST_DATA", "1") != "0":
        deleted, failed = cleanup_created_runs()
        print(f"cleanup: {deleted} conversation(s) removed, {failed} failed")

    return 0 if total_passed == total else 1


if __name__ == "__main__":
    # auth_headers()/get_token() require COMAGE_FRONTEND_CLIENT_SECRET and
    # DEMO_PERSONA_PASSWORD - see README.md.
    sys.exit(main())
