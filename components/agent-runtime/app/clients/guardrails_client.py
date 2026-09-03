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
import contextlib
import functools
import logging
import os
from typing import Any, Dict, List, Optional, Set

import httpx

from ..telemetry import guardrails_observe_span, record_guardrails_evaluation

logger = logging.getLogger("agent_runtime.guardrails")

# Empty URL = feature off (the chart leaves it unset until trustyai-config
# is installed). Same Service DNS convention as MCP_GATEWAY_URL.
GUARDRAILS_DETECTOR_URL = os.getenv("GUARDRAILS_DETECTOR_URL", "")
GUARDRAILS_TIMEOUT_SECONDS = float(os.getenv("GUARDRAILS_TIMEOUT_SECONDS", "10"))

# ADR-0540/WP-120. "builtin" = the GuardrailsOrchestrator built-in
# detector with DETECTOR_PARAMS below; "nemo" = the NemoGuardrails server,
# whose policy lives in a ConfigMap rendered from
# gitops/charts/trustyai-config/files/nemo-rails/observe/. Default stays
# "builtin" until the nemo path is live-proven: ADR-0534's whole posture
# is measure-before-trust, and that applies to the observer too.
GUARDRAILS_BACKEND = os.getenv("GUARDRAILS_BACKEND", "builtin").strip().lower()
GUARDRAILS_NEMO_URL = os.getenv("GUARDRAILS_NEMO_URL", "")
GUARDRAILS_CONFIG_ID = os.getenv("GUARDRAILS_CONFIG_ID", "zuno-observe")

# BUILTIN BACKEND ONLY. ADR-0540 moves this policy into NeMo rails
# config (custom_data.zuno_patterns); this dict is kept because "builtin"
# remains the declared fallback backend and this dict is that fallback's
# ENTIRE policy - the GuardrailsOrchestrator carries no patterns of its
# own, they travel on every request in detector_params. Deleting it would
# leave backend="builtin" wired, healthy and detecting nothing, which
# turns the rollback for the nemo flip into a silent loss of observation.
#
# ADR-0540 Decision 4 originally said this dies in the same commit that
# flips the default; that was amended 2026-09-03 (WP-120) once the flip
# made the contradiction concrete. It now lives as long as the
# GuardrailsOrchestrator is the declared fallback - whichever decision
# retires zuno-guardrails-smoke deletes this and PolicyParityWithRails
# together.
#
# Meanwhile the two copies must stay in step: an edit here needs the same
# edit in files/nemo-rails/observe/config.yaml. PolicyParityWithRails
# fails if they drift.
#
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
        # prompt-injection / jailbreak heuristics. Up to two filler words
        # between the verb and its object: the first live test (2026-09-02,
        # run d9445c2a) proved "ignore all PREVIOUS instructions" slipped a
        # single-filler pattern - exactly the tuning observe-mode exists to
        # surface before anything blocks.
        r"(?i)ignore\s+(?:\w+\s+){0,2}(instructions|prompts|rules)",
        r"(?i)disregard\s+(?:\w+\s+){0,2}(instructions|guidelines|rules)",
        r"(?i)you\s+are\s+now\s+(DAN|developer\s+mode)",
        r"(?i)pretend\s+(you\s+have\s+no|there\s+are\s+no)\s+(restrictions|rules|guidelines)",
        r"(?i)system\s*prompt\s*[:=]",
    ]
}

# Strong references so fire-and-forget tasks are not garbage-collected
# mid-flight (asyncio only keeps weak refs to tasks).
_pending: Set[asyncio.Task] = set()


def _with_observe_span(fn):
    """WP-120: open a `guardrails_observe` span around one evaluation.

    A decorator rather than a wrapper inside observe_exchange, for two
    reasons. It applies identically to both backends without duplicating
    the span code, and functools.wraps keeps __qualname__ intact - which
    matters because the backend-selection test identifies the chosen
    coroutine by name, and a closure would have hidden exactly the thing
    that test exists to check.

    The span is opened INSIDE the coroutine, so its duration is the
    observer's own cost and not however long the event loop took to
    schedule the fire-and-forget task.
    """
    @functools.wraps(fn)
    async def wrapper(**kwargs: Any) -> None:
        # ExitStack, not a plain `with`: if opening the span raises, the
        # stack stays empty and the evaluation still runs unspanned. A
        # tracer fault must not be able to stop guardrails observation -
        # that would be a telemetry bug silently disabling the observer,
        # which is the exact failure the WP-120 dashboard panels exist to
        # catch and a poor thing to introduce while adding them.
        with contextlib.ExitStack() as stack:
            try:
                stack.enter_context(guardrails_observe_span(
                    run_id=kwargs.get("run_id", ""),
                    agent=kwargs.get("agent", ""),
                    backend=GUARDRAILS_BACKEND,
                    project_id=kwargs.get("project_id"),
                ))
            except Exception:  # noqa: BLE001 - observability is never a dependency
                logger.debug("guardrails span unavailable", exc_info=True)
            await fn(**kwargs)
    return wrapper


@_with_observe_span
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
        record_guardrails_evaluation(agent, "unavailable")
        return

    detections = [
        {"content_index": i, "detection": d.get("detection"),
         "detection_type": d.get("detection_type"), "score": d.get("score")}
        for i, dets in enumerate(per_content) if isinstance(dets, list)
        for d in dets
    ]
    _report(
        detections=detections, contents=contents, run_id=run_id, agent=agent,
        project_id=project_id, tool_names=tool_names,
        retrieved_doc_count=retrieved_doc_count,
    )


def _report(
    *,
    detections: List[Dict[str, Any]],
    contents: List[str],
    run_id: str,
    agent: str,
    project_id: Optional[str],
    tool_names: List[str],
    retrieved_doc_count: int,
) -> None:
    """Log + record one evaluation outcome. Shared by every backend.

    Both backends route through here so a backend switch can never change
    the log shape or the metric semantics - only where the detections came
    from.
    """
    if detections:
        # WARNING on a hit so real-traffic detections are impossible to
        # miss in the log stream; the flagged exchange still reached the
        # user unmodified - that asymmetry IS the observe-only contract.
        logger.warning(
            "guardrails DETECTED (observe-only, response delivered unmodified): "
            "run_id=%s agent=%s project_id=%s detections=%s tools=%s retrieved_docs=%d",
            run_id, agent, project_id or "", detections, tool_names, retrieved_doc_count,
        )
        record_guardrails_evaluation(
            agent, "detected", [str(d.get("detection")) for d in detections]
        )
    else:
        logger.info(
            "guardrails clean: run_id=%s agent=%s contents=%d tools=%s retrieved_docs=%d",
            run_id, agent, len(contents), tool_names, retrieved_doc_count,
        )
        record_guardrails_evaluation(agent, "clean")


@_with_observe_span
async def _evaluate_nemo(
    *,
    contents: List[str],
    run_id: str,
    agent: str,
    project_id: Optional[str],
    tool_names: List[str],
    retrieved_doc_count: int,
) -> None:
    """Same contract as _evaluate, against the NemoGuardrails server.

    The rails are pattern-only (config.yaml carries no `models:` block), so
    this costs no LLM inference - which matters, because the GPU quota on
    this cluster is fully saturated. `options.rails` restricts execution
    to the input rail and `log.activated_rails` is what carries the
    detection names back; the generated message is ignored entirely.

    REQUEST SHAPE, established live 2026-09-03 against the RHOAI operand
    (WP-120 discovery questions 3 and 5). Two things about it are not
    guessable and both fail silently rather than loudly:

    - `config_id` and `options` are nested under `guardrails`, NOT at the
      top level. The server's request model simply DROPS unknown top-level
      keys, so a flat `options` is not rejected - it is ignored, the dialog
      rails run, and the request needs an LLM the config does not have.
      Live, that produced a 401 against api.openai.com and the string
      "Internal server error" as the assistant message, with HTTP 200.
    - `model` is required by the schema even though no rail uses it. Its
      absence is the one loud failure here: HTTP 422.

    With the correct nesting the stats come back `llm_calls_count: 0` and
    `dialog_rails_duration: null` - ADR-0540 Decision 2's cost gate holds,
    but only on this exact shape.

    Never raises: every failure path funnels to outcome "unavailable",
    exactly as the builtin backend does.
    """
    detections: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=GUARDRAILS_TIMEOUT_SECONDS) as client:
            for index, content in enumerate(contents):
                resp = await client.post(
                    f"{GUARDRAILS_NEMO_URL}/v1/chat/completions",
                    json={
                        # Required by the schema, unused by the rails: no
                        # rail generates, so nothing ever resolves it.
                        "model": GUARDRAILS_CONFIG_ID,
                        "messages": [{"role": "user", "content": content}],
                        "guardrails": {
                            "config_id": GUARDRAILS_CONFIG_ID,
                            "options": {
                                "rails": ["input"],
                                "log": {"activated_rails": True},
                            },
                        },
                    },
                )
                resp.raise_for_status()
                detections.extend(
                    {"content_index": index, "detection": name,
                     "detection_type": "nemo-rail", "score": None}
                    for name in _detection_names(resp.json())
                )
    except Exception as exc:  # noqa: BLE001 - observe-only: log, never propagate
        logger.warning(
            "guardrails evaluation unavailable (observe-only, response unaffected): "
            "backend=nemo run_id=%s agent=%s: %s", run_id, agent, exc,
        )
        record_guardrails_evaluation(agent, "unavailable")
        return

    _report(
        detections=detections, contents=contents, run_id=run_id, agent=agent,
        project_id=project_id, tool_names=tool_names,
        retrieved_doc_count=retrieved_doc_count,
    )


def _detection_names(payload: Any) -> List[str]:
    """Pull zuno_scan's matched pattern names out of an activated-rails log.

    The log lives at `guardrails.log.activated_rails`, one level deeper
    than the top-level `log` this originally assumed - confirmed live
    2026-09-03 (WP-120 question 5). Verified shape, per activated rail:

        {"type": "input", "name": "zuno scan input",
         "executed_actions": [{"action_name": "zuno_scan",
                               "return_value": ["injection-ignore-instructions"]}],
         "stop": false}

    A clean pass returns the same single rail with `return_value: []`, so
    "the rail ran and found nothing" and "the rail never ran" are
    distinguishable in the raw payload - though not in this function's
    return, which is [] either way.

    Tolerant by design: the operand's log shape is not pinned by the CRD,
    so an unrecognised payload yields no detections rather than an
    exception. A silent zero here is visible as a flat detections series
    on the zuno-trustyai dashboard, which is the intended failure mode for
    an observer.
    """
    names: List[str] = []
    log_block = ((payload or {}).get("guardrails") or {}).get("log") or {}
    for rail in log_block.get("activated_rails") or []:
        for executed in (rail or {}).get("executed_actions") or []:
            if (executed or {}).get("action_name") != "zuno_scan":
                continue
            result = executed.get("return_value")
            if isinstance(result, list):
                names.extend(str(item) for item in result)
    return names


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
    can never delay or alter it. A no-op when the selected backend's URL
    is unset or there is nothing to evaluate - so an unconfigured or
    half-configured backend disables the observer instead of erroring on
    every exchange.
    """
    backend = _evaluate_nemo if GUARDRAILS_BACKEND == "nemo" else _evaluate
    endpoint = GUARDRAILS_NEMO_URL if backend is _evaluate_nemo else GUARDRAILS_DETECTOR_URL
    if not endpoint:
        return
    contents = [c for c in (message, reply) if c and c.strip()]
    if not contents:
        return
    task = asyncio.create_task(backend(
        contents=contents,
        run_id=run_id,
        agent=agent,
        project_id=project_id,
        tool_names=sorted(tool_results or {}),
        retrieved_doc_count=retrieved_doc_count,
    ))
    _pending.add(task)
    task.add_done_callback(_pending.discard)
