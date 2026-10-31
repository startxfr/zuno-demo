"""ADR-0567/WP-153: TrustyAI guardrails at the one place every model call crosses.

Moved from components/agent-runtime/app/clients/guardrails_client.py (ADR-0534,
ADR-0540) rather than rewritten: same detector payloads, same backend switch
(built-in detector vs NemoGuardrails), same empty-URL-means-off rule, same
metric names. What is new is the mode, chosen per data classification:

- ``off``     - nothing is evaluated.
- ``observe`` - the exchange is evaluated after the response is on its way,
  fire-and-forget; detections are logged and counted, the response is never
  touched. Exactly the behaviour agent-runtime had.
- ``block``   - the prompt is evaluated before routing and the reply before it
  is returned; a detection yields an HTTP 400 with a typed error body.

What is sent: the last user message and the model's reply, verbatim - the two
things detections are ABOUT. Never sent: the caller's bearer token, system
prompts, retrieved document bodies or tool results.

Per agent (ADR-0579 clause 3, WP-164 lot 3): GUARDRAILS_AGENT_MODES_PATH
names a file generated from the agents release (corp minimum mode per
classification, and the `zuno.guardrails.mode` each agent declares). The
effective mode is the STRICTEST of the per-classification mode below, that
corp minimum and the calling agent's mode. X-Zuno-Agent is caller-supplied,
so it may only ever harden the mode, never relax it. A missing or unreadable
file leaves the per-classification mode alone.

A detector outage never breaks a request in either mode (it is counted as
``unavailable``): a guardrail that can take inference down would be a worse
failure than the one it guards against. Making ``block`` fail closed is a
separate decision.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

import httpx
import yaml

from app.telemetry import guardrails_observe_span, record_guardrails_evaluation

logger = logging.getLogger("ai_gateway.guardrails")

# Empty URL = feature off for that backend (the chart leaves it unset until
# trustyai-config is installed).
GUARDRAILS_DETECTOR_URL = os.getenv("GUARDRAILS_DETECTOR_URL", "")
GUARDRAILS_TIMEOUT_SECONDS = float(os.getenv("GUARDRAILS_TIMEOUT_SECONDS", "10"))
GUARDRAILS_BACKEND = os.getenv("GUARDRAILS_BACKEND", "builtin").strip().lower()
GUARDRAILS_NEMO_URL = os.getenv("GUARDRAILS_NEMO_URL", "")
GUARDRAILS_CONFIG_ID = os.getenv("GUARDRAILS_CONFIG_ID", "zuno-observe")

MODES = ("off", "observe", "block")
DEFAULT_MODE = "observe"
_RANK = {mode: rank for rank, mode in enumerate(MODES)}
GUARDRAILS_AGENT_MODES_PATH = os.getenv("GUARDRAILS_AGENT_MODES_PATH", "")


def _strictest(*modes: str) -> str:
    return max(modes, key=lambda m: _RANK.get(m, _RANK[DEFAULT_MODE]))


def _load_modes(raw: str) -> Dict[str, str]:
    """Parse GUARDRAILS_MODE_BY_CLASSIFICATION (a JSON object, e.g.
    {"C1":"observe","C3":"block"}). A malformed value, or an unknown mode,
    falls back to observe for that class - never to off, never to block."""
    modes: Dict[str, str] = {}
    if not raw.strip():
        return modes
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.warning("ignoring malformed GUARDRAILS_MODE_BY_CLASSIFICATION: %r", raw)
        return modes
    if not isinstance(parsed, dict):
        logger.warning("GUARDRAILS_MODE_BY_CLASSIFICATION must be a JSON object: %r", raw)
        return modes
    for cls, mode in parsed.items():
        mode = str(mode).strip().lower()
        if mode not in MODES:
            logger.warning("unknown guardrails mode %r for %s, using %s", mode, cls, DEFAULT_MODE)
            mode = DEFAULT_MODE
        modes[str(cls).strip().upper()] = mode
    return modes


MODE_BY_CLASSIFICATION = _load_modes(os.getenv("GUARDRAILS_MODE_BY_CLASSIFICATION", ""))


class AgentModes:
    """The generated per-agent modes and corp minimums (ADR-0579 clause 3), reloadable."""

    def __init__(self, path: str = GUARDRAILS_AGENT_MODES_PATH):
        self.path = path
        self.minimum: Dict[str, str] = {}
        self.agents: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            logger.info("no guardrails agent modes at %s; per-classification modes only", self.path)
            return
        except Exception as exc:  # noqa: BLE001 - keep the loaded modes
            logger.error("failed to read guardrails agent modes %s: %s", self.path, exc)
            return
        self.minimum = self._modes(doc.get("minimum_mode_by_classification"), upper=True)
        self.agents = self._modes(doc.get("agents"), upper=False)
        logger.info("loaded guardrails agent modes from %s (%d agent(s))", self.path, len(self.agents))

    @staticmethod
    def _modes(raw: Any, *, upper: bool) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, mode in (raw or {}).items() if isinstance(raw, dict) else []:
            mode = str(mode).strip().lower()
            if mode not in MODES:
                logger.warning("ignoring unknown guardrails mode %r for %s", mode, key)
                continue
            key = str(key).strip()
            out[key.upper() if upper else key] = mode
        return out


agent_modes = AgentModes()


def mode_for(classification: str, agent: str = "") -> str:
    """Effective mode for a (declared) data classification and calling agent:
    the strictest of the per-classification mode (unlisted classes get
    DEFAULT_MODE), the corp minimum for that class and the agent's declared
    mode. A mode only applies when the selected backend has a URL: an
    unconfigured backend disables the guardrail instead of erroring on every
    exchange."""
    if not _endpoint():
        return "off"
    cls = (classification or "").upper()
    modes = [MODE_BY_CLASSIFICATION.get(cls, DEFAULT_MODE)]
    if cls in agent_modes.minimum:
        modes.append(agent_modes.minimum[cls])
    if agent and agent in agent_modes.agents:
        modes.append(agent_modes.agents[agent])
    return _strictest(*modes)


def _endpoint() -> str:
    return GUARDRAILS_NEMO_URL if GUARDRAILS_BACKEND == "nemo" else GUARDRAILS_DETECTOR_URL


# BUILTIN BACKEND ONLY. Kept in step with
# gitops/charts/trustyai-config/files/nemo-rails/observe/config.yaml - the
# GuardrailsOrchestrator carries no patterns of its own, they travel on every
# request in detector_params; test_guardrails.PolicyParityWithRails fails if
# the two copies drift. Deleted together with the builtin fallback.
DETECTOR_PARAMS: Dict[str, List[str]] = {
    "regex": [
        "email",
        "us-social-security-number",
        "credit-card",
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


async def _detect_builtin(contents: List[str]) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=GUARDRAILS_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{GUARDRAILS_DETECTOR_URL}/api/v1/text/contents",
            json={"contents": contents, "detector_params": DETECTOR_PARAMS},
            headers={"detector-id": "built-in"},
        )
    resp.raise_for_status()
    return [
        {"content_index": i, "detection": d.get("detection"),
         "detection_type": d.get("detection_type"), "score": d.get("score")}
        for i, dets in enumerate(resp.json()) if isinstance(dets, list)
        for d in dets
    ]


async def _detect_nemo(contents: List[str]) -> List[Dict[str, Any]]:
    """One request per content against the NemoGuardrails server.

    The rails are pattern-only (no `models:` block) so this costs no LLM
    inference. The request shape is not guessable and fails silently when
    wrong (established live 2026-09-03, WP-120): `config_id` and `options`
    are nested under `guardrails` (unknown top-level keys are dropped, not
    rejected), and `model` is required by the schema though no rail uses it.
    """
    detections: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=GUARDRAILS_TIMEOUT_SECONDS) as client:
        for index, content in enumerate(contents):
            resp = await client.post(
                f"{GUARDRAILS_NEMO_URL}/v1/chat/completions",
                json={
                    "model": GUARDRAILS_CONFIG_ID,
                    "messages": [{"role": "user", "content": content}],
                    "guardrails": {
                        "config_id": GUARDRAILS_CONFIG_ID,
                        "options": {"rails": ["input"], "log": {"activated_rails": True}},
                    },
                },
            )
            resp.raise_for_status()
            detections.extend(
                {"content_index": index, "detection": name,
                 "detection_type": "nemo-rail", "score": None}
                for name in _detection_names(resp.json())
            )
    return detections


def _detection_names(payload: Any) -> List[str]:
    """Pull zuno_scan's matched pattern names out of an activated-rails log
    (`guardrails.log.activated_rails[].executed_actions[]`). Tolerant by
    design: an unrecognised payload yields no detections, visible as a flat
    series on the zuno-trustyai dashboard."""
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


async def evaluate(
    contents: List[str], *, agent: str, run_id: str = "", project_id: Optional[str] = None,
    mode: str = "observe",
) -> Optional[List[Dict[str, Any]]]:
    """Run the selected backend over `contents` and record the outcome.

    Returns the detections (possibly empty), or None when the detector was
    unavailable. Never raises. Opens a `guardrails_observe` span around the
    call; a tracer fault degrades to no span, never to no evaluation.
    """
    contents = [c for c in contents if c and c.strip()]
    if not contents or not _endpoint():
        return []
    backend = _detect_nemo if GUARDRAILS_BACKEND == "nemo" else _detect_builtin
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(guardrails_observe_span(
                run_id=run_id, agent=agent, backend=GUARDRAILS_BACKEND,
                project_id=project_id, mode=mode,
            ))
        except Exception:  # noqa: BLE001 - observability is never a dependency
            logger.debug("guardrails span unavailable", exc_info=True)
        try:
            detections = await backend(contents)
        except Exception as exc:  # noqa: BLE001 - a detector outage never breaks a request
            logger.warning(
                "guardrails evaluation unavailable (response unaffected): "
                "backend=%s mode=%s agent=%s run_id=%s: %s",
                GUARDRAILS_BACKEND, mode, agent, run_id, exc,
            )
            record_guardrails_evaluation(agent, "unavailable")
            return None
        _report(detections, contents, agent=agent, run_id=run_id, mode=mode)
        return detections


def _report(
    detections: List[Dict[str, Any]], contents: List[str], *, agent: str, run_id: str, mode: str,
) -> None:
    """Log + record one outcome. Detection NAMES only, never matched text."""
    if detections:
        logger.warning(
            "guardrails DETECTED (mode=%s): run_id=%s agent=%s detections=%s",
            mode, run_id, agent, detections,
        )
        record_guardrails_evaluation(
            agent, "detected", [str(d.get("detection")) for d in detections]
        )
    else:
        logger.info("guardrails clean (mode=%s): run_id=%s agent=%s contents=%d",
                    mode, run_id, agent, len(contents))
        record_guardrails_evaluation(agent, "clean")


def observe_exchange(
    *, message: str, reply: str, agent: str, run_id: str = "", project_id: Optional[str] = None,
) -> None:
    """Fire-and-forget evaluation of one finished exchange (observe mode).

    Spawned after the response is already on its way, so even a hung
    detector costs the caller nothing.
    """
    contents = [c for c in (message, reply) if c and c.strip()]
    if not contents or not _endpoint():
        return
    task = asyncio.create_task(evaluate(
        contents, agent=agent, run_id=run_id, project_id=project_id, mode="observe",
    ))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def refusal_body(stage: str, detections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Typed 400 body. Detection names only - never the matched text."""
    return {
        "error": {
            "type": "guardrails_blocked",
            "code": "guardrails_blocked",
            "stage": stage,  # "prompt" or "reply"
            "message": f"the {stage} was refused by the guardrails policy",
            "detections": sorted({str(d.get("detection")) for d in detections}),
        }
    }
