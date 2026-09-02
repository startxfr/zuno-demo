"""Observe-only guardrails client (ADR-0534/WP-109).

After an agent exchange completes, the converged exchange (user prompt +
final reply) is POSTed to the TrustyAI built-in detector service deployed
by gitops/charts/trustyai-config (GuardrailsOrchestrator, standalone
built-in detectors) and any detections are LOGGED - never raised, never
blocked on, never allowed to alter the response. The call runs as a
fire-and-forget asyncio task spawned after the response is already on its
way to the client, so even a hung detector costs the user nothing.

Enforcement (blocking a request on a detection) is explicitly out of
scope: ADR-0534's Operational considerations make the observe-to-block
transition a separate, later decision that needs the evidence this module
is here to collect.

What is sent: the user's message and the model's reply, verbatim - the
two things detections are ABOUT. What is deliberately NOT sent: the
caller's bearer token, the (up to 54000-char) project context, retrieved
document bodies and raw tool results - those stay in the log line's
metadata as counts/names only, so a detector-service compromise never
sees credentials or bulk corpus content.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Set

import httpx

logger = logging.getLogger("agent_runtime.guardrails")

# Empty URL = feature off (the chart leaves it unset until trustyai-config
# is installed). Same Service DNS convention as MCP_GATEWAY_URL.
GUARDRAILS_DETECTOR_URL = os.getenv("GUARDRAILS_DETECTOR_URL", "")
GUARDRAILS_TIMEOUT_SECONDS = float(os.getenv("GUARDRAILS_TIMEOUT_SECONDS", "10"))

# Built-in detector params, live-verified 2026-09-02 against this
# cluster's detector (quay.io/trustyai/guardrails-detector-built-in via
# the operator): named PII patterns plus custom regexes for
# prompt-injection heuristics (detection name comes back "custom-regex").
# Heuristic by design - the point of observe-only is to measure how these
# behave on real traffic before anyone trusts them to block.
DETECTOR_PARAMS: Dict[str, List[str]] = {
    "regex": [
        "email",
        "us-social-security-number",
        "credit-card",
        # prompt-injection / jailbreak heuristics
        r"(?i)ignore\s+(all|any|previous|prior|above)\s+(instructions|prompts|rules)",
        r"(?i)disregard\s+(your|the|all)\s+(instructions|guidelines|rules)",
        r"(?i)you\s+are\s+now\s+(DAN|developer\s+mode)",
        r"(?i)pretend\s+(you\s+have\s+no|there\s+are\s+no)\s+(restrictions|rules|guidelines)",
        r"(?i)system\s*prompt\s*[:=]",
    ]
}

# Strong references so fire-and-forget tasks are not garbage-collected
# mid-flight (asyncio only keeps weak refs to tasks).
_pending: Set[asyncio.Task] = set()


async def _evaluate(
    *,
    contents: List[str],
    run_id: str,
    agent: str,
    project_id: Optional[str],
    tool_names: List[str],
    retrieved_doc_count: int,
) -> None:
    """POST to the detector and log the outcome. Never raises."""
    try:
        async with httpx.AsyncClient(timeout=GUARDRAILS_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{GUARDRAILS_DETECTOR_URL}/api/v1/text/contents",
                json={"contents": contents, "detector_params": DETECTOR_PARAMS},
                headers={"detector-id": "built-in"},
            )
        resp.raise_for_status()
        per_content = resp.json()
    except Exception as exc:  # noqa: BLE001 - observe-only: log, never propagate
        logger.warning(
            "guardrails evaluation unavailable (observe-only, response unaffected): "
            "run_id=%s agent=%s: %s", run_id, agent, exc,
        )
        return

    detections = [
        {"content_index": i, "detection": d.get("detection"),
         "detection_type": d.get("detection_type"), "score": d.get("score")}
        for i, dets in enumerate(per_content) if isinstance(dets, list)
        for d in dets
    ]
    if detections:
        # WARNING on a hit so real-traffic detections are impossible to
        # miss in the log stream; the flagged exchange still reached the
        # user unmodified - that asymmetry IS the observe-only contract.
        logger.warning(
            "guardrails DETECTED (observe-only, response delivered unmodified): "
            "run_id=%s agent=%s project_id=%s detections=%s tools=%s retrieved_docs=%d",
            run_id, agent, project_id or "", detections, tool_names, retrieved_doc_count,
        )
    else:
        logger.info(
            "guardrails clean: run_id=%s agent=%s contents=%d tools=%s retrieved_docs=%d",
            run_id, agent, len(contents), tool_names, retrieved_doc_count,
        )


def observe_exchange(
    *,
    message: str,
    reply: str,
    run_id: str,
    agent: str,
    project_id: Optional[str] = None,
    tool_results: Optional[Dict[str, Any]] = None,
    retrieved_doc_count: int = 0,
) -> None:
    """Fire-and-forget entry point for both chat paths (sync + SSE).

    Spawned AFTER the response is already being returned/streamed, so it
    can never delay or alter it. A no-op when GUARDRAILS_DETECTOR_URL is
    unset or there is nothing to evaluate.
    """
    if not GUARDRAILS_DETECTOR_URL:
        return
    contents = [c for c in (message, reply) if c and c.strip()]
    if not contents:
        return
    task = asyncio.create_task(_evaluate(
        contents=contents,
        run_id=run_id,
        agent=agent,
        project_id=project_id,
        tool_names=sorted(tool_results or {}),
        retrieved_doc_count=retrieved_doc_count,
    ))
    _pending.add(task)
    task.add_done_callback(_pending.discard)
