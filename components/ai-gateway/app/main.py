"""Zuno AI Inference Gateway (ADR-0009, ADR-0020, ADR-0021).

OpenAI-compatible `POST /v1/chat/completions`: resolves the eligible
provider fallback chain for the caller-declared `X-Zuno-Data-Classification`
header, then either invokes (non-streaming) or streams (`stream: true`)
the first provider that succeeds. See README.md for the exact HTTP API
contract, and docs/adr/0009-*.md for why this exists as a service separate
from components/agent-runtime.
"""

from __future__ import annotations

import asyncio
import json
import os
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app import classification_floor, model_tasks, signed_chain, tool_markers
from app import key_ceilings, metered_paths, stream_guard
from app import guardrails, maas_adapter, quota, quota_fail_modes, quota_windows, reasoning as reasoning_fallback, routing_decisions, semantic_cache
from app.auth import CallerIdentity, client_allowed, require_admin, validate_token
from app.image_providers import ImageProviderFactoryError, generate_image
from app.image_routing import ImageRoutingError, ImageRoutingTable
from app.model_routing_policy import AdapterDeclaration, ModelRoutingPolicy
from app.optimizer import OptimizationRefused, TuningController
from app.providers import chat_model_for
from app.routing import ProviderCandidate, RoutingError, RoutingTable
from app.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatMessage,
    ImageGenerationData,
    ImageGenerationRequest,
    ImageGenerationResponse,
    ModelList,
    ModelObject,
    RoutingDecision,
)
from app.routing_watch import ROUTING_RELOAD_INTERVAL_SECONDS, RoutingWatcher
from app.circuit_breaker import breaker
from app.model_readiness import readiness
from app.telemetry import adopt_incoming_trace_context, init_telemetry, model_call_span, record_cache_outcome, record_candidate_skipped, record_empty_response, set_caller_client, set_caller_persona, set_caller_task

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ai_gateway")

# WP-193: the display name of the `auto` model in GET /v1/models.
AUTO_MODEL_NAME = os.getenv("AUTO_MODEL_NAME", "Zuno")

init_telemetry("ai-gateway")  # ADR-0029: traces/metrics to the shared OTel Collector

app = FastAPI(
    title="Zuno AI Inference Gateway",
    version="0.1.0",
    description=(
        "OpenAI-compatible inference routing, classification-eligibility "
        "and provider fallback (ADR-0009, ADR-0020, ADR-0021)."
    ),
)

routing_table = RoutingTable()
image_routing_table = ImageRoutingTable()  # ADR-0415
model_routing_policy = ModelRoutingPolicy()  # ADR-0303 (WP-39)
tuning_controller = TuningController()  # ADR-0309 (WP-42) - inert unless the policy enables it
# The routing files are a ConfigMap of another Argo CD Application: reload them
# when the mounted copy changes instead of waiting for a pod restart.
# The model-routing policy can be generated and mounted too (ADR-0581, WP-164 lot 2).
routing_watcher = RoutingWatcher({
    routing_table.path: routing_table.reload,
    image_routing_table.path: image_routing_table.reload,
    model_routing_policy.path: model_routing_policy.reload,
    # ADR-0579 (WP-164 lot 3): generated per-agent guardrail modes, when mounted.
    **({guardrails.agent_modes.path: guardrails.agent_modes.reload} if guardrails.agent_modes.path else {}),
    # ADR-0565 clause 5 (WP-209): generated per-(agent, task) classification floors, when mounted.
    **({classification_floor.floors.path: classification_floor.floors.reload} if classification_floor.floors.path else {}),
})


@app.on_event("startup")
async def _start_routing_watch() -> None:
    if ROUTING_RELOAD_INTERVAL_SECONDS > 0:
        asyncio.create_task(routing_watcher.run(ROUTING_RELOAD_INTERVAL_SECONDS))
    # ADR-0591: model readiness (inert unless MODEL_READINESS_ENABLED) and the
    # NeMo warm-up (only with the nemo backend), both off the request path.
    if os.getenv("MODEL_READINESS_ENABLED", "false").strip().lower() == "true":
        asyncio.create_task(readiness.run())
    if guardrails.GUARDRAILS_BACKEND == "nemo" and guardrails.GUARDRAILS_NEMO_URL:
        asyncio.create_task(guardrails.keep_warm())

_ROLE_TO_MESSAGE = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    if routing_table.loaded:
        return JSONResponse({"status": "ready"})
    return JSONResponse(
        {"status": "not-ready", "reason": "provider routing config not loaded"}, status_code=503
    )


@app.post("/admin/reload-routing", dependencies=[Depends(require_admin)])
async def reload_routing() -> Dict[str, Any]:
    """Operational escape hatch: re-reads provider-routing.yaml,
    policies/model-routing/model-routing-policy.yaml and
    policies/optimization/optimization-policy.yaml from disk without a
    pod restart (mirrors mcp-gateway's /admin/reload-policy). Reloading
    an optimization policy whose kill_switch flipped to true engages the
    kill immediately (TuningController.reload_policy's own behavior).
    """
    routing_table.reload()
    image_routing_table.reload()
    model_routing_policy.reload()
    tuning_controller.reload_policy()
    classification_floor.floors.reload()
    return {"loaded": routing_table.loaded}


# --------------------------------------------------------------------------
# ADR-0309 (WP-42) - bounded autonomous tuning admin surface. These
# endpoints are the operator's window into the tuner: the audit trail,
# outcome reporting (live monitoring feeds the observed window metrics
# in), and the kill switch. Only reachable in-cluster (this service has
# no public Route; NetworkPolicy admits agent-runtime + the acceptance
# gate only), same trust model as /admin/reload-routing above.
# --------------------------------------------------------------------------


@app.get("/admin/optimizer/audit", dependencies=[Depends(require_admin)])
async def optimizer_audit() -> Dict[str, Any]:
    return {
        "enabled": tuning_controller.policy.enabled,
        "kill_switch": tuning_controller.policy.kill_switch,
        "audit": tuning_controller.audit_log(),
    }


@app.post("/admin/optimizer/outcome", dependencies=[Depends(require_admin)])
async def optimizer_outcome(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reports the observed evaluation-window metrics; the controller
    auto-rolls-back every open action on a trigger breach."""
    rolled_back = tuning_controller.report_outcome(
        error_rate=float(payload.get("error_rate", 0.0)),
        quality=payload.get("quality"),
    )
    return {"rolled_back": [e.parameter for e in rolled_back]}


@app.post("/admin/optimizer/kill", dependencies=[Depends(require_admin)])
async def optimizer_kill() -> Dict[str, Any]:
    reverted = tuning_controller.kill()
    return {"reverted": [e.parameter for e in reverted]}


@app.post("/admin/optimizer/apply", dependencies=[Depends(require_admin)])
async def optimizer_apply(payload: Dict[str, Any]) -> JSONResponse:
    """Applies one recommendation (evaluations/routing_report.py's own
    entry format, or {parameter: cache_ttl, value: N}) within the
    governance policy. Refusals are 403 - a definitive no, not a retry
    hint."""
    try:
        if payload.get("parameter") == "cache_ttl":
            entry = tuning_controller.apply_cache_ttl(int(payload["value"]), evidence=payload)
        elif payload.get("parameter") == "cache_enabled":
            entry = tuning_controller.apply_cache_enabled(
                model=payload["model"], enabled=bool(payload["value"]), evidence=payload,
            )
        elif payload.get("parameter") == "routing":
            entry = tuning_controller.apply_routing_override(
                agent=payload["agent"], task=payload["task"], adapter=payload["adapter"], evidence=payload,
            )
        else:
            return JSONResponse({"error": f"unknown parameter {payload.get('parameter')!r}"}, status_code=422)
    except OptimizationRefused as exc:
        return JSONResponse({"refused": str(exc)}, status_code=403)
    except (KeyError, ValueError) as exc:
        return JSONResponse({"error": f"malformed recommendation: {exc}"}, status_code=422)
    return JSONResponse({"applied": entry.parameter, "old": entry.old_value, "new": entry.new_value})


def _to_langchain_messages(messages: List[ChatMessage]) -> List[Any]:
    """ADR-0415: role="tool" (a tool's result being fed back for a
    follow-up turn) becomes a LangChain ToolMessage; an assistant message
    that itself carries tool_calls (the model's own prior turn choosing to
    call one) is rebuilt with LangChain's normalized tool_calls shape,
    converting each OpenAI-wire `function.arguments` JSON string back into
    a dict - the reverse of what _invoke_with_fallback/_stream_completion
    do when they serialize a model's response tool_calls onto the wire."""
    result: List[Any] = []
    for m in messages:
        if m.role == "tool":
            result.append(ToolMessage(content=m.content or "", tool_call_id=m.tool_call_id or ""))
            continue
        if m.role == "assistant" and m.tool_calls:
            result.append(
                AIMessage(
                    content=m.content or "",
                    tool_calls=[
                        {
                            "name": tc["function"]["name"],
                            "args": json.loads(tc["function"]["arguments"] or "{}"),
                            "id": tc.get("id", ""),
                            "type": "tool_call",
                        }
                        for tc in m.tool_calls
                    ],
                )
            )
            continue
        result.append(_ROLE_TO_MESSAGE[m.role](content=m.content or ""))
    return result


# Reply cap applied when the caller sets none (no body max_tokens /
# max_completion_tokens, no X-Zuno-Max-Tokens). 0 disables it.
MAX_TOKENS_DEFAULT = int(os.getenv("MAX_TOKENS_DEFAULT", "0") or 0)


def _effective_max_tokens(header_cap: Optional[int], payload: Any) -> Optional[int]:
    """The reply cap for one request: the smallest of the X-Zuno-Max-Tokens
    header (ADR-0544, the task's declared limit), the body's max_tokens and
    max_completion_tokens (OpenAI fields, e.g. the UnifAI client's 4096), or
    MAX_TOKENS_DEFAULT when none is given. A cap only ever narrows; a
    non-positive body value is ignored like a malformed header."""
    caps = [header_cap] + [getattr(payload, f, None) for f in ("max_tokens", "max_completion_tokens")]
    caps = [c for c in caps if isinstance(c, int) and c > 0]
    if caps:
        return min(caps)
    return MAX_TOKENS_DEFAULT or None


def _candidate_max_tokens(
    max_tokens: Optional[int], cfg: Dict[str, Any], messages: List[Any], tools: Optional[List[Dict[str, Any]]]
) -> Optional[int]:
    """The cap sent to one candidate: never more than the room the prompt
    leaves in its max_model_len (vLLM refuses prompt + max_tokens above the
    window, so a fixed cap would break long prompts that fit today). The
    prompt size is the same char/4 estimate as the pre-flight skip."""
    max_model_len = cfg.get("max_model_len")
    if not max_tokens or not max_model_len:
        return max_tokens
    estimate = _estimate_prompt_tokens(messages, tools)
    # WP-208 D8: char/4 only approximates the model's tokenizer. With no margin the cap filled the window to
    # the token (32768 - 24605 = 8163 asked for a prompt of 24606 tokens) and vLLM answered 400 on the
    # difference, on both entries of the model. Keep 5 % of the prompt, at least 256 tokens, free.
    room = int(max_model_len) - estimate - max(256, estimate // 20)
    return min(max_tokens, room) if room > 0 else max_tokens


def _parse_max_tokens(raw: str) -> Optional[int]:
    """ADR-0544: X-Zuno-Max-Tokens is an optional control header, not a
    caller-authenticated value - a malformed one must never fail a user's
    chat turn, same posture every other header in chat_completions takes.
    Degrades to None (no cap) on anything that isn't a plain positive
    decimal integer, including an out-of-range one - the OKF schema
    (zuno-okf-task-v0.2.schema.json) already bounds a declared value to
    [1, 8192], so anything past that reaching the wire is either a bug or
    a caller this endpoint doesn't need to trust.
    """
    raw = raw.strip()
    if not raw.isdigit():
        if raw:
            logger.warning("ignoring malformed X-Zuno-Max-Tokens header: %r", raw)
        return None
    value = int(raw)
    if not (0 < value <= 8192):
        logger.warning("ignoring out-of-range X-Zuno-Max-Tokens header: %r", raw)
        return None
    return value


# Deliberately duplicated char/4 heuristic (matches components/agent-runtime/
# app/graph/history.py's own estimate_tokens - same style precedent as this
# repo's other cross-service duplicated small parsing logic) rather than a
# shared dependency between the two components for one four-line function.
_CHARS_PER_TOKEN = 4


def _estimate_prompt_tokens(messages: List[Any], tools: Optional[List[Dict[str, Any]]]) -> int:
    total_chars = sum(len(getattr(m, "content", "") or "") for m in messages)
    if tools:
        total_chars += len(json.dumps(tools))
    return total_chars // _CHARS_PER_TOKEN + 1


def _last_user_text(messages: List[ChatMessage]) -> str:
    """The prompt guardrails evaluate: the last user message only - never the
    system prompt, retrieved bodies or tool results (ADR-0567)."""
    for m in reversed(messages):
        if m.role == "user":
            return m.content or ""
    return ""


async def _observed_stream(
    stream: AsyncIterator[str], *, prompt: str, agent: str, run_id: Optional[str], project_id: Optional[str],
    extra: Optional[List[str]] = None,
) -> AsyncIterator[str]:
    """Observe mode: pass the SSE stream through untouched and, once it ends,
    hand the accumulated reply to the fire-and-forget observer. Nothing is held
    back (ADR-0567); in block mode app/stream_guard.py is used instead."""
    reply: List[str] = []
    try:
        async for chunk in stream:
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                try:
                    delta = json.loads(chunk[6:])["choices"][0]["delta"]
                    reply.append(delta.get("content") or "")
                except (ValueError, KeyError, IndexError, TypeError):
                    pass
            yield chunk
    finally:
        guardrails.observe_exchange(
            message=prompt, reply="".join(reply), agent=agent or "unknown",
            run_id=run_id or "", project_id=project_id, extra=extra or (),
        )


def _chat_stream_events(stream: AsyncIterator[str]) -> AsyncIterator["tuple[str, str]"]:
    """(raw SSE chunk, reply text it adds) for app/stream_guard.py: the content
    delta, and the arguments of a tool-call delta (model output too)."""
    async def events() -> AsyncIterator["tuple[str, str]"]:
        try:
            async for chunk in stream:
                text = ""
                if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                    try:
                        delta = json.loads(chunk[6:])["choices"][0]["delta"]
                        text = delta.get("content") or ""
                        for call in delta.get("tool_calls") or []:
                            text += (call.get("function") or {}).get("arguments") or ""
                    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                        pass
                yield chunk, text
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
    return events()


def _guarded_reply_evaluator(
    *, agent: str, run_id: Optional[str], project_id: Optional[str],
):
    async def evaluate(text: str):
        return await guardrails.evaluate(
            [text], agent=agent or "unknown", run_id=run_id or "", project_id=project_id, mode="block",
        )
    return evaluate


async def _guardrails_refusal(
    stage: str, detections: List[Dict[str, Any]], *, request_id: str, classification: str,
    unavailable: bool = False,
) -> JSONResponse:
    """400 for a blocked exchange (503 for a fail-closed detector outage, ADR-0602
    clause 8), recorded in the routing-decisions store so the caller's routing
    panel shows why nothing was served."""
    await routing_decisions.set_routing_decision(
        request_id,
        {
            "provider": None,
            "model": None,
            "kind": None,
            "classification": classification,
            "blocked_by": "guardrails_unavailable" if unavailable else "guardrails",
            "guardrails_stage": stage,
            "fallback_used": False,
            "fallback_from": None,
        },
    )
    if unavailable:
        return JSONResponse(guardrails.unavailable_body(stage), status_code=503)
    return JSONResponse(guardrails.refusal_body(stage, detections), status_code=400)


def agent_chain_required_clients() -> List[str]:
    """WP-225 lot C review: the Keycloak clients (`azp`, `*` suffix a prefix) that
    must present a valid X-Zuno-Agent-Chain when they declare an agent
    (AGENT_CHAIN_REQUIRE_FOR, chart agentChain.requireFor, read per call). Empty
    (the default) requires it of nobody."""
    raw = os.getenv("AGENT_CHAIN_REQUIRE_FOR", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def _agent_identity(chain_header: str, agent: str, task: str, identity: CallerIdentity) -> "tuple[str, str, bool]":
    """ADR-0603 M14 (WP-225 lot C): the (agent, task) a call is made for, and
    whether it comes from a verified chain.

    With AGENT_CHAIN_VERIFY on and a valid X-Zuno-Agent-Chain (signed by the
    a2a-gateway, bound to this bearer, addressed to the ai-gateway;
    app/signed_chain.py), the verified pair replaces X-Zuno-Agent / X-Zuno-Task, so
    the WP-209 floor, the routing preferences and the guardrails mode key on an
    agent the caller cannot choose. A disagreeing header is ignored and logged.
    Without a verified chain the headers apply, as before, and the floor is the
    higher of the agent's and the client's. A client listed in
    AGENT_CHAIN_REQUIRE_FOR that names an agent without a valid chain gets the
    agent header ignored (logged): only its client floor applies."""
    resolved = signed_chain.resolve(
        chain_header, agent, task, token=identity.token, audience="ai-gateway", log=logger
    )
    if resolved.verified:
        return resolved.agent, resolved.task, True
    required = agent_chain_required_clients()
    if (agent or "").strip() and required and client_allowed(identity.client, required):
        logger.warning(
            "X-Zuno-Agent %r ignored: client %s must present a valid agent chain (AGENT_CHAIN_REQUIRE_FOR)",
            agent, identity.client,
        )
        return "", task, False
    return resolved.agent, resolved.task, False


@app.post("/v1/chat/completions", dependencies=[Depends(adopt_incoming_trace_context)])
async def chat_completions(
    payload: ChatCompletionRequest,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="", alias="X-Zuno-Data-Classification"),
    x_zuno_local_only: str = Header(default="false", alias="X-Zuno-Local-Only"),
    # ADR-0104: optional, degrades safely to "" (the cache key still binds
    # to it, so this can never widen a hit across tasks). ADR-0303
    # (WP-39): as of components/agent-runtime/app/clients/model_router.py,
    # every real caller now sends this alongside X-Zuno-Agent below -
    # together they're the (agent, task) key model_routing_policy.py
    # resolves an adapter declaration from.
    x_zuno_task: str = Header(default="", alias="X-Zuno-Task"),
    # ADR-0303 (WP-39): optional, degrades safely to "" - a caller that
    # never sends it simply never resolves to a declared adapter (falls
    # back to the base model, the same fail-closed-to-safe default as an
    # unresolved X-Zuno-Task).
    x_zuno_agent: str = Header(default="", alias="X-Zuno-Agent"),
    # ADR-0201 (WP-27) usage correlation: the same request id agent-runtime
    # mints per chat turn (components/agent-runtime/app/main.py's
    # _request_id) and forwards via ModelRouter - optional, so this
    # endpoint stays callable by anything that doesn't send it yet; a
    # fresh id is minted here rather than left blank, so every model_call
    # span still carries a stable id even for a caller that never sends
    # one (never blank, always joinable to something).
    x_zuno_request_id: str = Header(default="", alias="X-Zuno-Request-Id"),
    # ADR-0543: the calling chat turn's id (distinct from request_id, one
    # HTTP call) - agent-runtime's model_router forwards this so the
    # model_call span can be found by the per-run resource dashboard.
    x_zuno_run_id: str = Header(default="", alias="X-Zuno-Run-Id"),
    # ADR-0511 (WP-54): quota class per the executing task's
    # zuno.quota_class (absent = standard), and the ADR-0512/0528 verified
    # project binding. Platform-side context: honoured only when the caller's
    # token comes from a client in TRUSTED_PLATFORM_CLIENTS (app/auth.py);
    # from any other caller they are ignored (standard class, no project).
    x_zuno_quota_class: str = Header(default="", alias="X-Zuno-Quota-Class"),
    x_zuno_project_id: str = Header(default="", alias="X-Zuno-Project-Id"),
    # ADR-0544: per-request generation ceiling - components/agent-runtime's
    # ModelRouter forwards a task's own declared max_tokens (OKF frontmatter)
    # this way rather than through payload.model or per-provider config,
    # since it is a per-CALL value, not a routing decision or a provider
    # default. Optional; absent means no cap, today's exact behavior.
    x_zuno_max_tokens: str = Header(default="", alias="X-Zuno-Max-Tokens"),
    # ADR-0603 M14 (WP-225 lot C): the a2a-gateway's signed agent chain, verified
    # by _agent_identity() only when AGENT_CHAIN_VERIFY is on.
    x_zuno_agent_chain: str = Header(default="", alias=signed_chain.HEADER),
):
    x_zuno_agent, x_zuno_task, agent_verified = _agent_identity(x_zuno_agent_chain, x_zuno_agent, x_zuno_task, identity)
    set_caller_client(identity.client)  # ADR-0587: experience client on the metrics
    set_caller_persona(identity.persona)  # ADR-0593: the zuno.persona span attribute and the per-user budget
    # ADR-0596: an experience client's declared model (e.g. zuno-code) selects
    # one of its tasks; the routing policy, never the name, picks the provider.
    x_zuno_task = model_tasks.task_for(identity.client, payload.model, x_zuno_task)
    set_caller_task(x_zuno_task)
    # ADR-0565 clause 5 (WP-209): an absent header takes the configured default
    # (C1 until the callers listed in the WP-209 brief send one), and the level
    # is never below the calling (agent, task)'s generated floor. Routing,
    # local_only_for, guardrails and the counters below all use the effective level.
    floor = classification_floor.floors.effective(
        classification_floor.declared_level(x_zuno_data_classification), x_zuno_agent, x_zuno_task,
        identity.client, agent_verified=agent_verified,
    )
    if floor.raised:
        logger.info(
            "classification raised by floor: %s -> %s agent=%s task=%s client=%s",
            floor.declared, floor.effective, x_zuno_agent, x_zuno_task, identity.client,
        )
    classification = floor.effective
    # ADR-0550: a per-(agent,task) local_only_for declaration ORs into the
    # caller's own X-Zuno-Local-Only flag - it can only ever add a
    # restriction, never lift one. Needed because a provider can be
    # globally eligible for this classification (e.g. ovhcloud-gpt-oss-120b
    # at C2, shared with other agents/tasks that legitimately use it there)
    # while still being forbidden for THIS task at that same classification -
    # see model_routing_policy.py's local_only_for_classification docstring.
    local_only = x_zuno_local_only.strip().lower() == "true" or model_routing_policy.local_only_for_classification(
        x_zuno_agent, x_zuno_task, classification
    )
    # ADR-0594: raise the call from the signed classification markers of the
    # tool results in its context; for an experience client an unmarked tool
    # result, or any C2+ content, keeps the turn on local models. Only raises.
    marks = tool_markers.assess(payload.messages, classification, local_only, identity.client)
    if marks.changed:
        logger.info(
            "classification raised by tool results: %s -> %s, local_only %s -> %s (%s) client=%s",
            classification, marks.classification, local_only, marks.local_only,
            ", ".join(sorted(set(marks.reasons))), identity.client,
        )
        classification, local_only = marks.classification, marks.local_only
        local_only = local_only or model_routing_policy.local_only_for_classification(
            x_zuno_agent, x_zuno_task, classification
        )
    request_id = x_zuno_request_id.strip() or str(uuid.uuid4())
    run_id = x_zuno_run_id.strip() or None
    quota_class, project_id = _platform_context(identity, x_zuno_quota_class, x_zuno_project_id)
    max_tokens = _effective_max_tokens(_parse_max_tokens(x_zuno_max_tokens), payload)
    # ADR-0511: token-budget check BEFORE dispatch, on top of (never
    # instead of) the classification/eligibility intersection below.
    # Exhaustion is an explicit 429, never silent degradation.
    denial = quota.ledger.check(quota_class, identity.persona, identity.groups, project_id)
    if denial is not None and _budget_fault_rides_through(denial, quota_class):
        logger.warning("quota budget config fault: class %r is fail_mode open, admitting", quota_class)
        denial = None
    if denial is not None:
        headers = {"Retry-After": str(denial.retry_after)} if denial.retry_after else None
        return JSONResponse(denial.detail(), status_code=429, headers=headers)
    # ADR-0412: per-(agent,task) preference from the git-managed policy
    # only (never the ADR-0309 autonomy surface - "prefer" is on the
    # optimizer's code-level denylist). Only permutes the candidates that
    # survive the eligibility/local-only filtering inside candidates_for -
    # it can never widen what ADR-0021/0035 allow. ADR-0417: `strict`
    # narrows that permutation into an exclusion (no unlisted survivor) for
    # entries that opt in - see model_routing_policy.py/routing.py.
    preference = model_routing_policy.preference_for(x_zuno_agent, x_zuno_task)
    strict_preference = model_routing_policy.strict_for(x_zuno_agent, x_zuno_task)
    # ADR-0581: the (agent, task)'s forbidden model roles, as provider names - narrows only.
    exclude = model_routing_policy.exclude_for(x_zuno_agent, x_zuno_task)
    try:
        candidates = routing_table.candidates_for(
            classification, local_only=local_only, prefer=preference, strict=strict_preference, exclude=exclude
        )
    except RoutingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ADR-0303 (WP-39): resolved once, from the classification-eligible
    # candidate list's own request context - never itself widens or
    # narrows `candidates`, only picks which model name a `local`
    # candidate uses once the fallback loop reaches it.
    adapter_decl = model_routing_policy.adapter_for(x_zuno_agent, x_zuno_task)

    # ADR-0309 (WP-42): the tuning controller's runtime override is
    # consulted strictly AFTER the Git-declared policy resolved, and the
    # controller itself only ever holds overrides drawn from the
    # optimization policy's pre-approved-equivalents list - so this can
    # swap between human-approved equivalent candidates, never introduce
    # a new one, and never bypass the classification guard downstream
    # (providers.chat_model_for re-checks candidate.kind regardless of
    # where the adapter name came from).
    override = tuning_controller.adapter_override(x_zuno_agent, x_zuno_task)
    if override:
        adapter_decl = AdapterDeclaration(adapter=override, classification=adapter_decl.classification if adapter_decl else "C1")

    messages = _to_langchain_messages(payload.messages)

    # ADR-0567 (WP-153): guardrails mode follows the classification routing uses
    # (since WP-209 the effective level, raised by the floor and the markers),
    # so a caller cannot get a laxer guardrails mode than the routing it is subject to.
    # ADR-0579: the calling agent's declared mode and the corp minimum can only harden it.
    gr_mode = guardrails.mode_for(classification, x_zuno_agent)
    # ADR-0602 clause 8 (WP-225): the last user message AND the current turn's
    # tool results are scanned (an injection planted in a page arrives as one).
    gr_items = guardrails.chat_scan_items(payload.messages) if gr_mode != "off" else []
    gr_prompt = next((it.text for it in gr_items if it.kind == "prompt"), "")
    gr_extra = [it.text for it in gr_items if it.kind != "prompt"]
    if gr_mode == "block":
        found = await guardrails.evaluate(
            [it.text for it in gr_items], agent=x_zuno_agent or "unknown", run_id=x_zuno_run_id.strip(),
            project_id=project_id, mode="block",
        )
        if found:
            return await _guardrails_refusal(
                guardrails.stage_of(found, gr_items), found, request_id=request_id,
                classification=classification,
            )
        if found is None and guardrails.fails_closed(classification):
            return await _guardrails_refusal(
                "prompt", [], request_id=request_id, classification=classification, unavailable=True,
            )

    # ADR-0591 decision 6: every eligible candidate is unavailable - answer now,
    # with the reasons, instead of a stream that can only end in error.
    unavailable = _nothing_available(candidates)
    if unavailable:
        for candidate in candidates:
            record_candidate_skipped(
                candidate.name,
                "not_ready" if not readiness.is_ready(
                    routing_table.provider_config(candidate.name).get("inference_service")
                ) else "circuit_open",
            )
        raise HTTPException(
            status_code=503,
            detail=f"no eligible provider is available for classification {classification}: {unavailable}",
        )

    if payload.stream:
        stream = _stream_completion(
            candidates, classification, messages, request_id, adapter_decl,
            identity=identity, tools=payload.tools, agent=x_zuno_agent, run_id=run_id,
            project_id=project_id, quota_class=quota_class, max_tokens=max_tokens,
            include_usage=bool((payload.stream_options or {}).get("include_usage")),
        )
        if maas_adapter.quota_429_passthrough_enabled():
            # WP-157: a MaaS 429 must reach the caller as an HTTP 429, and a
            # StreamingResponse has sent its 200 before the first chunk is
            # produced. So the stream is driven to its first chunk here (a
            # candidate only ever raises MaasQuotaExceeded before yielding
            # anything); only with the flag on, so the default path keeps
            # sending its headers before the first token.
            try:
                first_chunk: Optional[str] = await stream.__anext__()
            except maas_adapter.MaasQuotaExceeded as quota_denial:
                return _maas_quota_response(quota_denial, quota_class, identity, project_id)
            except StopAsyncIteration:
                first_chunk = None
            stream = _prepend(first_chunk, stream)
        if gr_mode == "block":
            # ADR-0602 clause 8: held back in segments and cut on a detection.
            stream = stream_guard.guard(
                _chat_stream_events(stream),
                evaluate=_guarded_reply_evaluator(agent=x_zuno_agent, run_id=run_id, project_id=project_id),
                error_event=stream_guard.openai_chat_error_event,
                fail_closed=guardrails.fails_closed(classification),
            )
        elif gr_mode != "off":
            stream = _observed_stream(
                stream, prompt=gr_prompt, agent=x_zuno_agent, run_id=run_id, project_id=project_id,
                extra=gr_extra,
            )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        result = await _invoke_with_fallback(
            candidates,
            classification,
            messages,
            caller_sub=identity.sub,
            quota_subject=identity.persona,
            groups=identity.groups,
            caller_bearer_token=identity.token,
            local_only=local_only,
            task_id=x_zuno_task,
            requested_model=payload.model,
            raw_messages=payload.messages,
            request_id=request_id,
            adapter_decl=adapter_decl,
            quota_class=quota_class,
            project_id=project_id,
            tools=payload.tools,
            agent=x_zuno_agent,
            run_id=run_id,
            max_tokens=max_tokens,
        )
    except maas_adapter.MaasQuotaExceeded as quota_denial:
        # Raised only with MAAS_QUOTA_429_PASSTHROUGH on (WP-157).
        return _maas_quota_response(quota_denial, quota_class, identity, project_id)
    if gr_mode == "off":
        return result
    reply = result.choices[0].message.content or ""
    if gr_mode == "block":
        found = await guardrails.evaluate(
            [reply], agent=x_zuno_agent or "unknown", run_id=x_zuno_run_id.strip(),
            project_id=project_id, mode="block",
        )
        if found:
            return await _guardrails_refusal(
                "reply", found, request_id=request_id, classification=classification,
            )
        if found is None and guardrails.fails_closed(classification):
            return await _guardrails_refusal(
                "reply", [], request_id=request_id, classification=classification, unavailable=True,
            )
        return result
    guardrails.observe_exchange(
        message=gr_prompt, reply=reply, agent=x_zuno_agent or "unknown",
        run_id=x_zuno_run_id.strip(), project_id=project_id, extra=gr_extra,
    )
    return result


@app.get("/v1/models")
async def list_models(
    response: Response,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="", alias="X-Zuno-Data-Classification"),
    x_zuno_local_only: str = Header(default="false", alias="X-Zuno-Local-Only"),
) -> ModelList:
    """OpenAI-standard model list: the distinct model ids of the routing-table
    providers eligible for the caller's classification (same eligibility
    filter as chat completions, `candidates_for`), plus the `auto` alias
    clients send (routing is classification-driven, never model-name-driven).
    Cheap (in-memory table) and short-cacheable.

    WP-193: an experience client (Open WebUI, OpenClaw: the same list as
    MARKER_FAIL_CLOSED_CLIENTS) gets `auto` alone. Its menu would otherwise
    offer models that routing ignores; the gateway keeps the choice."""
    response.headers["Cache-Control"] = "private, max-age=30"
    if tool_markers.is_fail_closed_client(identity.client or ""):
        # ADR-0596: plus the declared models that select a task (Zuno Code).
        return ModelList(data=[ModelObject(id="auto", name=AUTO_MODEL_NAME)]
                         + [ModelObject(id=i, name=n) for i, n in model_tasks.listed_models()])
    classification = classification_floor.declared_level(x_zuno_data_classification)
    try:
        candidates = routing_table.candidates_for(
            classification, local_only=x_zuno_local_only.strip().lower() == "true"
        )
    except RoutingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ids: List[str] = ["auto"]
    for candidate in candidates:
        model_id = routing_table.provider_config(candidate.name).get("model", candidate.name)
        if model_id not in ids:
            ids.append(model_id)
    return ModelList(data=[ModelObject(id=i, name=AUTO_MODEL_NAME if i == "auto" else None) for i in ids])


@app.get("/v1/routing-decisions/{request_id}")
async def get_routing_decision(
    request_id: str,
    identity: CallerIdentity = Depends(validate_token),
) -> RoutingDecision:
    """ADR-0550 (WP-135): components/agent-runtime polls this once its own
    model call completes, to recover the real provider/model/fallback
    attribution neither the streaming SSE path nor LangChain's parsed
    non-streaming response can carry - see routing_decisions.py's module
    docstring. Authenticated the same as every other endpoint here;
    `request_id` itself is a short-TTL, per-call value, not a capability
    token, so this intentionally does not check that the caller "owns"
    the request_id (agent-runtime is the only real caller and always asks
    about its own immediately-preceding call)."""
    decision = await routing_decisions.get_routing_decision(request_id)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"no routing decision found for request_id={request_id!r}")
    return RoutingDecision(**decision)


@app.post("/v1/images/generations")
async def images_generations(
    payload: ImageGenerationRequest,
    identity: CallerIdentity = Depends(validate_token),
    # ADR-0415: callers of this endpoint (the MCP Gateway's in-process
    # image_gen handler) always send C2 here, regardless of the calling
    # agent's own ambient classification - the scoped override that lets
    # arkos/cognos (C3 for everything else) use this one capability. This
    # endpoint does not special-case that; it enforces eligibility exactly
    # like /v1/chat/completions does, against whatever classification the
    # caller actually declares, and fails closed the same way.
    x_zuno_data_classification: str = Header(default="", alias="X-Zuno-Data-Classification"),
    x_zuno_request_id: str = Header(default="", alias="X-Zuno-Request-Id"),
):
    set_caller_client(identity.client)  # ADR-0587
    set_caller_persona(identity.persona)  # ADR-0593
    # WP-209: the default of a header-less call applies here too; no agent floor
    # (ADR-0415's scoped C2 override is why this endpoint takes no X-Zuno-Agent).
    classification = classification_floor.declared_level(x_zuno_data_classification)
    request_id = x_zuno_request_id.strip() or str(uuid.uuid4())

    try:
        candidates = image_routing_table.candidates_for(classification)
    except ImageRoutingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    errors: List[str] = []
    for candidate in candidates:
        cfg = image_routing_table.provider_config(candidate.name)
        try:
            logger.info(
                "image_call: provider=%s model=%s classification=%s request_id=%s caller=%s",
                candidate.name, cfg.get("model"), classification, request_id, identity.sub,
            )
            image = generate_image(candidate, cfg, prompt=payload.prompt, negative_prompt=payload.negative_prompt)
        except ImageProviderFactoryError as exc:
            errors.append(f"{candidate.name}: {exc}")
            continue
        except Exception as exc:  # pragma: no cover - defensive, mirrors _invoke_with_fallback
            logger.warning("image provider '%s' failed: %s", candidate.name, exc)
            errors.append(f"{candidate.name}: {exc}")
            continue

        return ImageGenerationResponse(
            data=[ImageGenerationData(b64_json=image.data_base64)],
            zuno_provider=candidate.name,
        )

    raise HTTPException(
        status_code=502,
        detail=f"all eligible image providers failed for classification {classification}: {'; '.join(errors)}",
    )


def _adapter_skips_maas(
    cfg: Dict[str, Any],
    adapter_decl: Optional[AdapterDeclaration],
) -> bool:
    """ADR-0521 (WP-076) closeout: an adapter-resolved request must never
    ride a via_maas candidate. A LoRA adapter id replaces the request
    body's `model` field, which MaaS's whole auth chain keys on (ipp-pre
    copies it into X-Gateway-Model-Name for the OPA rules; no MaaSModelRef
    exists for adapter ids) - and app/providers.py's own guard would
    otherwise silently drop the adapter on a via_maas candidate, degrading
    the task to the base model without any signal. Skipping lands the
    request on the same model's direct sibling instead (provider-routing
    .yaml guarantees one immediately after each -maas entry). Deliberately
    coarse: it also skips a via_maas candidate whose model doesn't serve
    adapters at all (e.g. local-gpt-oss-maas) - for an adapter-declared
    (agent, task) that's a same-model transport downgrade, not a
    behavior change, and cheaper than resolving sibling capabilities
    here."""
    return adapter_decl is not None and bool(cfg.get("via_maas", False))


# ---------------------------------------------------------------------------
# WP-157 (ADR-0570) preparatory switches. Each helper below returns today's
# behaviour unless its env flag is on (all default off; see
# gitops/charts/ai-gateway/values.yaml's maasAdapter block).


def _platform_context(
    identity: CallerIdentity, quota_class_header: str, project_id_header: str,
) -> "tuple[str, Optional[str]]":
    """The quota class and project id the request runs under. Both are
    platform-side context (ADR-0511, ADR-0528): taken from the headers only
    for a trusted platform client, otherwise no project and the caller's
    default class, whatever the caller sent. The default class is
    `evaluation` for a member of the evaluation group (the eval-* and
    stress-* personas, whose chats reach the gateway through UnifAI with
    their own token), once the loaded budgets define that class; `standard`
    otherwise."""
    default_class = _default_quota_class(identity)
    quota_class = quota_class_header.strip() or default_class
    project_id = project_id_header.strip() or None
    if identity.is_trusted_platform_client:
        return quota_class, project_id
    if quota_class != default_class or project_id:
        logger.info(
            "ignoring platform context headers from untrusted client %r (caller=%s)",
            (identity.raw_claims or {}).get("azp"), identity.sub,
        )
    return default_class, None


EVALUATION_QUOTA_CLASS = "evaluation"


def _default_quota_class(identity: CallerIdentity) -> str:
    """`evaluation` for a member of EVALUATION_GROUP (default
    zuno-evaluation, the group the Keycloak evaluation-personas Job gives the
    eval-* and stress-* personas), provided the budgets define the class -
    an image older than the policy that adds it keeps them on `standard`
    rather than denying them as an unknown class."""
    # WP-184: a stresstest group (empty = off) puts its members under the tight
    # `stresstest` budget class, so the shared-quota proof needs no budget
    # change. Leaving the group ends it.
    stresstest_group = os.getenv("QUOTA_STRESSTEST_GROUP", "").strip().lstrip("/")
    if (
        stresstest_group and stresstest_group in (identity.groups or [])
        and "stresstest" in (getattr(quota.ledger, "_classes", None) or {})
    ):
        return "stresstest"
    group = os.getenv("EVALUATION_GROUP", "zuno-evaluation").strip().lstrip("/")
    if not group or group not in (identity.groups or []):
        return "standard"
    if EVALUATION_QUOTA_CLASS not in (getattr(quota.ledger, "_classes", None) or {}):
        return "standard"
    return EVALUATION_QUOTA_CLASS


def _maas_call_kwargs(
    sub: Optional[str], groups: Optional[List[str]], quota_class: str, project_id: Optional[str],
) -> Dict[str, Any]:
    """D5: the attested context for chat_model_for, or {} so the default
    call is exactly today's (MAAS_GATEWAY_IDENTITY off)."""
    if not maas_adapter.gateway_identity_enabled():
        return {}
    return {
        "maas_context": maas_adapter.MaasCallContext(
            sub=sub or "",
            groups=tuple(groups or ()),
            quota_class=quota_class or "standard",
            project_id=project_id,
        )
    }


def _skips_direct_sibling(candidate: ProviderCandidate, quota_class: str) -> bool:
    """ADR-0570 clause 7 (QUOTA_FAIL_MODES_ENFORCED): a direct-Service
    sibling bypasses MaaS's quota, so it serves only classes whose
    fail_mode is `open`. Applies to every sibling of a closed class, also
    when an adapter declaration made the via_maas twin skip itself: a LoRA
    adapter has no MaaS path, so a closed-class adapter request is served
    by the next eligible model instead (recorded in the WP-157 brief)."""
    if not quota_fail_modes.enforced():
        return False
    if quota_fail_modes.fail_modes.fail_open(quota_class):
        return False
    return candidate.name in routing_table.direct_sibling_names()


def _skips_unmetered_candidate(candidate: ProviderCandidate, cfg: Dict[str, Any], quota_class: str) -> bool:
    """QUOTA_CLOSED_CLASS_MAAS_ONLY (WP-157 inventory V13): a `closed` class
    (stresstest, intensive) is served only through MaaS, where its quota is
    counted. Any other candidate - a direct SaaS provider, a direct sibling -
    is skipped, so when no MaaS path is left the request ends in the usual
    all-candidates-failed error instead of a quota-free SaaS answer."""
    if not quota_fail_modes.closed_class_maas_only():
        return False
    if quota_fail_modes.fail_modes.fail_open(quota_class):
        return False
    return not maas_adapter.should_use_maas(cfg, candidate.kind)


def _budget_fault_rides_through(denial: "quota.QuotaDenial", quota_class: str) -> bool:
    """QUOTA_FAIL_MODES_ENFORCED: app/quota.py denies every class, `standard`
    included, when its budget file is unreadable (WP-157 inventory finding 2,
    contrary to its own docstring). With the flag on, an `open` class rides
    through that fault; a class unknown to a healthy config stays denied."""
    if not quota_fail_modes.enforced() or denial.dimension != "class":
        return False
    config_fault = bool(getattr(quota.ledger, "_config_error", None)) or not getattr(quota.ledger, "_classes", None)
    return config_fault and quota_fail_modes.fail_modes.fail_open(quota_class)


def _maas_quota_denial(
    candidate: ProviderCandidate, cfg: Dict[str, Any], exc: BaseException,
) -> Optional[maas_adapter.MaasQuotaExceeded]:
    """MAAS_QUOTA_429_PASSTHROUGH: a 429 from a candidate reached THROUGH
    MaaS is a quota denial, never a reason to try the direct sibling (which
    would bypass the quota) or a SaaS model. A 429 from a direct SaaS
    provider stays an ordinary provider failure (the vendor's own rate
    limit), as today."""
    if not maas_adapter.quota_429_passthrough_enabled():
        return None
    if not maas_adapter.should_use_maas(cfg, candidate.kind):
        return None
    return maas_adapter.quota_exceeded_from(exc, candidate.name)


# WP-208 D8: a request the model itself refuses as malformed or too long (HTTP 400, 413, 422) is refused by
# every entry serving that same model. The `-maas` entry and the direct entry of one model (local-maas and
# local, local-gpt-oss-maas and local-gpt-oss, ...) are the same weights over two paths, so replaying the
# request on the sibling only doubles the error count and the load; a different model may still accept it
# (a larger context window) and stays in the fallback order.
_CLIENT_REJECTION_STATUSES = frozenset({400, 413, 422})


def _client_rejection_status(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) and status in _CLIENT_REJECTION_STATUSES else None


def _model_family(provider_name: str) -> str:
    return provider_name[: -len("-maas")] if provider_name.endswith("-maas") else provider_name


def _note_maas_call(
    candidate: ProviderCandidate, cfg: Dict[str, Any], quota_class: str,
    sub: Optional[str], groups: Optional[List[str]], project_id: Optional[str],
) -> None:
    """MAAS_QUOTA_429_PASSTHROUGH: a call about to go through MaaS starts the
    window of each counter key it will be charged to (app/quota_windows.py),
    so a later 429 can say when the budget refills."""
    if not maas_adapter.quota_429_passthrough_enabled():
        return
    if not maas_adapter.should_use_maas(cfg, candidate.kind):
        return
    quota_windows.clock.hit(quota_class, sub, maas_adapter.groups_key(groups), project_id)
    quota_windows.clock.hit_model(candidate.name, cfg.get("maas_quota_window"))


def _maas_quota_response(
    denial: maas_adapter.MaasQuotaExceeded,
    quota_class: str,
    identity: Optional[CallerIdentity] = None,
    project_id: Optional[str] = None,
) -> JSONResponse:
    """The gateway's own 429 contract (WP-148): status 429, `quota_exceeded`
    body, Retry-After. MaaS sends none (WP-157 inventory V12), so when it is
    missing the gateway computes it from the policy windows and the first
    call it saw in each (app/quota_windows.py); UnifAI turns the header into
    metadata.error.retry_after."""
    if denial.retry_after is None:
        try:
            model_window = routing_table.provider_config(denial.provider).get("maas_quota_window")
        except StopIteration:
            model_window = None
        denial.retry_after = quota_windows.clock.retry_after(
            quota_class,
            identity.persona if identity else None,
            maas_adapter.groups_key(identity.groups if identity else None),
            project_id,
            provider=denial.provider,
            model_window=model_window,
        )
    headers = {"Retry-After": str(denial.retry_after)} if denial.retry_after else None
    return JSONResponse(denial.detail(quota_class), status_code=429, headers=headers)


async def _prepend(first: Optional[str], rest: AsyncIterator[str]) -> AsyncIterator[str]:
    if first is not None:
        yield first
    async for chunk in rest:
        yield chunk


def _resolve_adapter(
    candidate: ProviderCandidate,
    cfg: Dict[str, Any],
    adapter_decl: Optional[AdapterDeclaration],
) -> Optional[str]:
    """None unless the candidate is local, its provider entry declares
    `serves_adapters: true` (ADR-0412: with two local runtimes, only the
    qwen one registers loraAdapters - a LoRA module name must never reach
    a runtime that doesn't serve it), and a declaration exists for this
    request's (agent, task) - the same guard app/providers.py's
    chat_model_for() re-checks itself (ADR-0303/WP-39 defense in depth)."""
    if adapter_decl and candidate.kind == "local" and cfg.get("serves_adapters", False):
        return adapter_decl.adapter
    return None


def _usage_tokens(result: Any) -> tuple[int, int]:
    """Shared by both the non-streaming (`result` is the final message) and
    streaming (`result` is the chunks' `__add__`-accumulated final chunk,
    see `_stream_completion`) paths - `usage_metadata` has the same shape
    either way once ChatOpenAI's `stream_usage=True` is set
    (app/providers.py)."""
    usage = getattr(result, "usage_metadata", None) or {}
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def _availability_skip(candidate: ProviderCandidate, cfg: Dict[str, Any]) -> Optional[str]:
    """ADR-0591: "not_ready" when the candidate's LLMInferenceService reports
    Ready=False, "circuit_open" when its breaker is open, else None. Claims
    the breaker's half-open trial: call it only right before the call."""
    if not readiness.is_ready(cfg.get("inference_service")):
        return "not_ready"
    if breaker.is_open(candidate.name):
        return "circuit_open"
    return None


def _only_availability_skips(errors: List[str]) -> bool:
    return bool(errors) and all(
        e.endswith(": skipped (not_ready)") or e.endswith(": skipped (circuit_open)") for e in errors
    )


def _nothing_available(candidates: List[ProviderCandidate]) -> Optional[str]:
    """ADR-0591 decision 6, before a stream sends its 200: the per-candidate
    reasons when not one candidate is available, else None. Uses the breaker's
    peek (no trial claimed), so the loop still gets the half-open trial."""
    reasons = []
    for candidate in candidates:
        cfg = routing_table.provider_config(candidate.name)
        if not readiness.is_ready(cfg.get("inference_service")):
            reasons.append(f"{candidate.name}: not ready")
        elif breaker.peek_open(candidate.name):
            reasons.append(f"{candidate.name}: circuit open")
        else:
            return None
    return "; ".join(reasons) if reasons else None


async def _invoke_with_fallback(
    candidates: List[ProviderCandidate],
    classification: str,
    messages: List[Any],
    caller_sub: str,
    local_only: bool,
    task_id: str,
    requested_model: str,
    raw_messages: List[ChatMessage],
    request_id: str,
    adapter_decl: Optional[AdapterDeclaration] = None,
    groups: Optional[List[str]] = None,
    quota_class: str = "standard",
    project_id: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    agent: str = "",
    run_id: Optional[str] = None,
    # 2026-09-01 (identity-per-caller): forwarded to chat_model_for() so
    # maas_adapter can present the real caller's own Keycloak identity to
    # the MaaS Gateway instead of ai-gateway's fixed ServiceAccount - see
    # maas_adapter._maas_bearer_token's own docstring.
    caller_bearer_token: Optional[str] = None,
    max_tokens: Optional[int] = None,
    # ADR-0593: the persona the per-user budget, the quota windows and the
    # MaaS attestation are keyed by; `caller_sub` stays the raw token subject
    # (logs, span, semantic cache). None = the sub, the behaviour before.
    quota_subject: Optional[str] = None,
) -> ChatCompletionResponse:
    quota_subject = quota_subject or caller_sub
    # ADR-0104: cache check happens strictly AFTER routing_table.candidates_for()
    # already ran in chat_completions() above - a cache hit can never bypass
    # an eligibility/policy denial, only ever short-circuit an already-authorized
    # call. Gated on the most-preferred candidate's config (per-model
    # enablement); the cache key itself binds to `requested_model`, not the
    # specific candidate, so this stays correct regardless of which
    # candidate ends up serving an uncached request.
    # ADR-0415: a tools= request is never served from (or written to) the
    # cache - whether the model chooses to call a tool can depend on
    # context this cache's key doesn't capture, and a stale cached
    # tool_calls decision replayed onto a different turn would be wrong.
    cache_key: Optional[str] = None
    if tools is None and candidates and semantic_cache.should_use_cache(routing_table.provider_config(candidates[0].name)):
        prompt_text = "\n".join(f"{m.role}: {m.content or ''}" for m in raw_messages)
        context = semantic_cache.CacheContext(
            model_name=requested_model,
            user_sub=caller_sub,
            classification=classification,
            local_only=local_only,
            task_id=task_id,
        )
        try:
            cache_key = await semantic_cache.compute_cache_key(prompt_text, context)
            cached = await semantic_cache.get_cached_response(cache_key)
        except semantic_cache.CacheUnavailable as exc:
            logger.warning("semantic cache unavailable, proceeding uncached: %s", exc)
            record_cache_outcome("unavailable", requested_model)
            cached = None
            cache_key = None
        else:
            record_cache_outcome("hit" if cached is not None else "miss", requested_model)
        if cached is not None:
            # `cached` carries only the CACHEABLE_FIELDS below - id/created
            # are freshly generated by ChatCompletionResponse's own
            # default_factory here, since a response's own id/timestamp
            # describing "when was this returned" should reflect this
            # call, not the original one that populated the cache entry.
            #
            # ADR-0550 (WP-135): a cache hit never re-runs the fallback loop
            # below, so the ORIGINAL call's fallback_used/fallback_from are
            # not recoverable here - published as False/None rather than
            # left unpublished, which would make the routing panel show
            # stale data from an unrelated earlier request_id instead.
            cached_provider = cached.get("zuno_provider", "")
            try:
                cached_kind = routing_table.provider_config(cached_provider).get("kind", "local")
            except StopIteration:
                # provider_config() raises if the cached name no longer
                # matches any entry (provider-routing.yaml changed since
                # this response was cached) - never let a best-effort
                # observability lookup take down an otherwise-successful
                # cached response.
                cached_kind = "local"
            await routing_decisions.set_routing_decision(
                request_id,
                {
                    "provider": cached_provider,
                    "model": cached.get("model", ""),
                    "kind": cached_kind,
                    "classification": classification,
                    "fallback_used": False,
                    "fallback_from": None,
                },
            )
            return ChatCompletionResponse(**cached)

    errors: List[str] = []
    rejected_families: set = set()  # WP-208 D8
    other_failure = False
    for idx, candidate in enumerate(candidates):
        if _model_family(candidate.name) in rejected_families:
            errors.append(f"{candidate.name}: skipped, the same model already rejected the request")
            continue
        cfg = routing_table.provider_config(candidate.name)
        # ADR-0544 pre-flight: skip a candidate whose own max_model_len
        # (provider-routing.yaml) the prompt clearly can't fit, rather
        # than dispatch and let vLLM fail - today that failure is caught
        # by the same generic `except Exception` as a network blip
        # (below), indistinguishable in logs from one. Never skip the
        # LAST candidate: trying it anyway and surfacing the real
        # upstream error beats inventing a refusal this estimate (char/4,
        # deliberately approximate) could be wrong about. Also the only
        # protection non-agent-runtime callers (Lightspeed) get -
        # app/graph/prompt_budget.py's clamp never runs for them.
        max_model_len = cfg.get("max_model_len")
        if max_model_len and idx < len(candidates) - 1:
            estimated = _estimate_prompt_tokens(messages, tools)
            if estimated > max_model_len:
                logger.info(
                    "skipping candidate %s: estimated prompt ~%d tokens exceeds "
                    "its max_model_len=%d", candidate.name, estimated, max_model_len,
                )
                errors.append(
                    f"{candidate.name}: estimated prompt (~{estimated} tokens) exceeds "
                    f"max_model_len={max_model_len}"
                )
                continue
        if _adapter_skips_maas(cfg, adapter_decl):
            logger.debug(
                "skipping via_maas candidate %s: adapter declaration resolved, "
                "adapters cannot traverse MaaS", candidate.name,
            )
            continue
        if _skips_direct_sibling(candidate, quota_class):
            logger.info(
                "skipping direct sibling %s: quota class %r is fail_mode closed "
                "(ADR-0570 clause 7)", candidate.name, quota_class,
            )
            errors.append(f"{candidate.name}: direct sibling skipped for closed quota class {quota_class!r}")
            continue
        if _skips_unmetered_candidate(candidate, cfg, quota_class):
            logger.info(
                "skipping candidate %s: quota class %r is fail_mode closed and "
                "this candidate is not reached through MaaS", candidate.name, quota_class,
            )
            errors.append(f"{candidate.name}: not reached through MaaS, skipped for closed quota class {quota_class!r}")
            continue
        # ADR-0591: availability, after every policy skip above - a model its
        # controller reports not ready, or a provider whose breaker is open,
        # is skipped instead of waited for (a *-maas candidate of a down model
        # waited its full 180 s on the llm-d scheduler, 2026-11-02).
        availability = _availability_skip(candidate, cfg)
        if availability:
            logger.info("skipping candidate %s: %s (ADR-0591)", candidate.name, availability)
            record_candidate_skipped(candidate.name, availability)
            errors.append(f"{candidate.name}: skipped ({availability})")
            continue
        model_name = cfg.get("model", candidate.name)
        # ADR-0303 (WP-39): adapter_name is None unless this candidate is
        # local AND a declaration exists - effective_model_name is what
        # actually gets served/traced/returned, always the adapter's own
        # name when one applies.
        adapter_name = _resolve_adapter(candidate, cfg, adapter_decl)
        effective_model_name = adapter_name or model_name
        try:
            with model_call_span(
                candidate.name, effective_model_name, classification, request_id,
                adapter=adapter_name, caller_sub=caller_sub, groups=groups, agent=agent,
                run_id=run_id, model_kind=candidate.kind,
                # ADR-0528: the engagement dimension. Reached the quota
                # ledger already; this is the first time it reaches a trace.
                project_id=project_id,
            ) as call:
                _note_maas_call(candidate, cfg, quota_class, quota_subject, groups, project_id)
                model = chat_model_for(
                    candidate, cfg, request_id=request_id, adapter=adapter_name,
                    caller_bearer_token=caller_bearer_token,
                    max_tokens=_candidate_max_tokens(max_tokens, cfg, messages, tools),
                    **_maas_call_kwargs(quota_subject, groups, quota_class, project_id),
                )
                if tools:
                    model = model.bind_tools(tools)
                result = await model.ainvoke(messages)
                prompt_tokens, completion_tokens = _usage_tokens(result)
                call.record_usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
                # ADR-0511: attribute consumption per the precedence order
                # (project first when bound, then user; group ceiling always).
                # `_stream_completion` does NOT call this - since agent-runtime
                # (the only real caller) always streams, ADR-0511 quota
                # enforcement is effectively unmetered today. A known,
                # separate gap from record_usage's own streaming coverage
                # below (ADR-0029) - tracked as a follow-up, not fixed here.
                quota.ledger.consume(
                    quota_class, quota_subject, groups, project_id,
                    prompt_tokens + completion_tokens,
                )
        except Exception as exc:
            quota_denial = _maas_quota_denial(candidate, cfg, exc)
            if quota_denial is not None:
                logger.warning(
                    "provider '%s' (via MaaS) answered 429 for caller=%s: quota "
                    "exceeded, not falling back", candidate.name, caller_sub,
                )
                raise quota_denial from exc
            rejected_status = _client_rejection_status(exc)
            if rejected_status is not None:
                rejected_families.add(_model_family(candidate.name))
                logger.warning(
                    "provider '%s' rejected the request for caller=%s (HTTP %s), skipping its same-model sibling: %s: %s",
                    candidate.name, caller_sub, rejected_status, type(exc).__name__, exc,
                )
                errors.append(f"{candidate.name}: {exc}")
                continue
            other_failure = True
            breaker.record_failure(candidate.name, exc)
            logger.warning(
                "provider '%s' failed for caller=%s, trying next fallback: %s: %s",
                candidate.name, caller_sub, type(exc).__name__, exc,
            )
            errors.append(f"{candidate.name}: {exc}")
            continue
        breaker.record_success(candidate.name)

        content = result.content if hasattr(result, "content") else str(result)
        # ADR-0415: serialize LangChain's normalized tool_calls
        # ([{"name", "args": dict, "id"}]) back into OpenAI wire format -
        # the reverse of _to_langchain_messages' conversion, so a caller
        # that sends a prior assistant tool_calls message back in on the
        # next turn round-trips correctly.
        result_tool_calls = getattr(result, "tool_calls", None) or []
        wire_tool_calls = [
            {
                "id": tc.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
            }
            for tc in result_tool_calls
        ] or None
        folded = False
        if not wire_tool_calls:
            reasoning_text = reasoning_fallback.reasoning_of(result)
            if not (content if isinstance(content, str) else str(content or "")).strip():
                folded = reasoning_fallback.should_fold(content, False, reasoning_text)
                record_empty_response(candidate.name, effective_model_name, recovered=folded)
                if folded:
                    logger.warning(
                        "provider '%s' returned blank content; serving its reasoning block "
                        "(%d chars) as content", candidate.name, len(reasoning_text),
                    )
                    content = reasoning_text.strip()
        response = ChatCompletionResponse(
            model=effective_model_name,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content=content, tool_calls=wire_tool_calls),
                    finish_reason="tool_calls" if wire_tool_calls else "stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            zuno_provider=candidate.name,
            zuno_reasoning_fallback=folded,
        )
        # A blank answer is never cached (it would pin a transient glitch).
        if cache_key is not None and (content or "").strip():
            cacheable = response.model_dump(
                include={"model", "choices", "usage", "zuno_provider", "zuno_reasoning_fallback"}
            )
            await semantic_cache.set_cached_response(cache_key, cacheable)
        # ADR-0550 (WP-135): published unconditionally (not gated on
        # anything cache-related) - agent-runtime fetches this by
        # request_id regardless of whether the response itself was served
        # from cache, since a cache hit still needs a real answer to "what
        # would have served this request".
        await routing_decisions.set_routing_decision(
            request_id,
            {
                "provider": candidate.name,
                "model": effective_model_name,
                "kind": candidate.kind,
                "classification": classification,
                "fallback_used": idx > 0,
                "fallback_from": candidates[0].name if idx > 0 else None,
            },
        )
        return response

    raise HTTPException(
        # ADR-0591 decision 6: nothing was even tried - every candidate was
        # skipped for availability - is a 503, distinct from real failures.
        # WP-208 D8: a request every candidate refused as malformed or too long is the caller's, a 400.
        status_code=400 if (rejected_families and not other_failure) else (503 if _only_availability_skips(errors) else 502),
        detail=f"all eligible providers failed for classification {classification}: {'; '.join(errors)}",
    )


def _sse_chunk(completion_id: str, created: int, model_name: str, delta: Dict[str, Any], finish_reason: Optional[str] = None) -> str:
    return "data: " + json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
    ) + "\n\n"


def _sse_usage_chunk(completion_id: str, created: int, model_name: str, prompt_tokens: int, completion_tokens: int) -> str:
    """The OpenAI usage-only chunk (empty `choices`) sent when the request set stream_options.include_usage."""
    return "data: " + json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    ) + "\n\n"


async def _stream_completion(
    candidates: List[ProviderCandidate],
    classification: str,
    messages: List[Any],
    request_id: str,
    adapter_decl: Optional[AdapterDeclaration] = None,
    identity: Optional[CallerIdentity] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    agent: str = "",
    run_id: Optional[str] = None,
    # ADR-0528: the engagement dimension, so the streaming path tags its
    # model_call span the same way the non-streaming one does. Streaming is
    # the common case (agent-runtime always streams), so omitting it here
    # would have left the attribute effectively absent in practice.
    project_id: Optional[str] = None,
    # ADR-0511 (WP-54): same reasoning as project_id just above - streaming
    # is the common case (agent-runtime always streams), so until this was
    # threaded through, quota.ledger.consume() below was only ever reached
    # by the non-streaming path, and the ledger never reflected real chat
    # usage at all (confirmed live 2026-09-01: only test/stresstest traffic,
    # which calls this endpoint non-streaming, ever drew the budget down).
    quota_class: str = "",
    max_tokens: Optional[int] = None,
    # R-543: the caller asked for stream_options.include_usage, so the tokens this gateway read from
    # the provider's terminal chunk are republished as the OpenAI usage-only chunk before [DONE].
    include_usage: bool = False,
) -> AsyncIterator[str]:
    """Streams the first candidate that produces at least one token. A
    candidate that fails *before* yielding any token falls back to the next
    one, same as the non-streaming path. A candidate that fails *after*
    already streaming tokens to the caller cannot be silently retried
    (the client has already received partial content that a different
    provider's answer wouldn't continue coherently) - that case ends the
    stream with an error chunk instead. This mirrors the fallback boundary
    the pre-refactor `ModelRouter.streaming_model_for()` docstring
    described but never actually wired up.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    errors: List[str] = []
    rejected_families: set = set()  # WP-208 D8

    for idx, candidate in enumerate(candidates):
        if _model_family(candidate.name) in rejected_families:
            errors.append(f"{candidate.name}: skipped, the same model already rejected the request")
            continue
        cfg = routing_table.provider_config(candidate.name)
        # ADR-0544 pre-flight: skip a candidate whose own max_model_len
        # (provider-routing.yaml) the prompt clearly can't fit, rather
        # than dispatch and let vLLM fail - today that failure is caught
        # by the same generic `except Exception` as a network blip
        # (below), indistinguishable in logs from one. Never skip the
        # LAST candidate: trying it anyway and surfacing the real
        # upstream error beats inventing a refusal this estimate (char/4,
        # deliberately approximate) could be wrong about. Also the only
        # protection non-agent-runtime callers (Lightspeed) get -
        # app/graph/prompt_budget.py's clamp never runs for them.
        max_model_len = cfg.get("max_model_len")
        if max_model_len and idx < len(candidates) - 1:
            estimated = _estimate_prompt_tokens(messages, tools)
            if estimated > max_model_len:
                logger.info(
                    "skipping candidate %s: estimated prompt ~%d tokens exceeds "
                    "its max_model_len=%d", candidate.name, estimated, max_model_len,
                )
                errors.append(
                    f"{candidate.name}: estimated prompt (~{estimated} tokens) exceeds "
                    f"max_model_len={max_model_len}"
                )
                continue
        if _adapter_skips_maas(cfg, adapter_decl):
            logger.debug(
                "skipping via_maas candidate %s: adapter declaration resolved, "
                "adapters cannot traverse MaaS", candidate.name,
            )
            continue
        if _skips_direct_sibling(candidate, quota_class):
            logger.info(
                "skipping direct sibling %s: quota class %r is fail_mode closed "
                "(ADR-0570 clause 7)", candidate.name, quota_class,
            )
            errors.append(f"{candidate.name}: direct sibling skipped for closed quota class {quota_class!r}")
            continue
        if _skips_unmetered_candidate(candidate, cfg, quota_class):
            logger.info(
                "skipping candidate %s: quota class %r is fail_mode closed and "
                "this candidate is not reached through MaaS", candidate.name, quota_class,
            )
            errors.append(f"{candidate.name}: not reached through MaaS, skipped for closed quota class {quota_class!r}")
            continue
        # ADR-0591: availability, after every policy skip above - a model its
        # controller reports not ready, or a provider whose breaker is open,
        # is skipped instead of waited for (a *-maas candidate of a down model
        # waited its full 180 s on the llm-d scheduler, 2026-11-02).
        availability = _availability_skip(candidate, cfg)
        if availability:
            logger.info("skipping candidate %s: %s (ADR-0591)", candidate.name, availability)
            record_candidate_skipped(candidate.name, availability)
            errors.append(f"{candidate.name}: skipped ({availability})")
            continue
        model_name = cfg.get("model", candidate.name)
        adapter_name = _resolve_adapter(candidate, cfg, adapter_decl)
        effective_model_name = adapter_name or model_name
        sent_any = False
        try:
            with model_call_span(
                candidate.name, effective_model_name, classification, request_id,
                adapter=adapter_name,
                caller_sub=identity.sub if identity else None,
                groups=identity.groups if identity else None,
                agent=agent,
                run_id=run_id, model_kind=candidate.kind,
                project_id=project_id,  # ADR-0528
            ) as call:
                _note_maas_call(
                    candidate, cfg, quota_class,
                    identity.persona if identity else None,
                    identity.groups if identity else None,
                    project_id,
                )
                model = chat_model_for(
                    candidate, cfg, request_id=request_id, adapter=adapter_name,
                    caller_bearer_token=identity.token if identity else None,
                    max_tokens=_candidate_max_tokens(max_tokens, cfg, messages, tools),
                    **_maas_call_kwargs(
                        identity.persona if identity else None,
                        identity.groups if identity else None,
                        quota_class, project_id,
                    ),
                )
                if tools:
                    model = model.bind_tools(tools)
                # ADR-0029: accumulate chunks via AIMessageChunk.__add__ so the
                # terminal usage-only chunk (vLLM/OpenAI's stream_options.
                # include_usage extension, enabled in app/providers.py) merges
                # into a message with populated usage_metadata - without this,
                # zuno.model_tokens/zuno.model_cost_usd have zero series in
                # Grafana, since every real chat turn streams (agent-runtime
                # always does) and this path never read anything past
                # `.content` before. That terminal chunk's content is always
                # "", so it never reaches the `if token:` forward below - no
                # wire-format change.
                # ADR-0415: the same accumulation also reconstructs a fully
                # merged tool_calls list from a provider's streamed
                # tool-call-argument deltas (AIMessageChunk.__add__ already
                # merges tool_call_chunks) - forwarded as ONE consolidated
                # delta once the loop ends, rather than incremental
                # argument-fragment deltas like OpenAI's own API does; the
                # only real client (langchain_openai.ChatOpenAI) parses a
                # single complete tool_calls delta the same as it would
                # multiple partial ones.
                final_chunk = None
                reasoning_parts: List[str] = []
                async for event in model.astream(messages):
                    final_chunk = event if final_chunk is None else final_chunk + event
                    token = getattr(event, "content", "") or ""
                    if token:
                        sent_any = True
                        yield _sse_chunk(completion_id, created, effective_model_name, {"content": token})
                    elif (r_delta := reasoning_fallback.reasoning_of(event)):
                        # Held back, never forwarded as it arrives: only served
                        # if the stream ends with no content and no tool call.
                        reasoning_parts.append(r_delta)
                prompt_tokens, completion_tokens = _usage_tokens(final_chunk)
                call.record_usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
                # ADR-0511: attribute consumption per the precedence order,
                # same call as the non-streaming path above - see this
                # function's own quota_class parameter comment for why this
                # was missing until now.
                if identity is not None:
                    quota.ledger.consume(
                        quota_class, identity.persona, identity.groups, project_id,
                        prompt_tokens + completion_tokens,
                    )
        except Exception as exc:
            # Only before the first token: a quota 429 comes at request start,
            # and once tokens went out the stream can only end in error.
            quota_denial = None if sent_any else _maas_quota_denial(candidate, cfg, exc)
            if quota_denial is not None:
                logger.warning(
                    "provider '%s' (via MaaS) answered 429: quota exceeded, not "
                    "falling back", candidate.name,
                )
                raise quota_denial from exc
            rejected_status = None if sent_any else _client_rejection_status(exc)
            if rejected_status is not None:
                rejected_families.add(_model_family(candidate.name))
                logger.warning(
                    "provider '%s' rejected the request (HTTP %s), skipping its same-model sibling: %s: %s",
                    candidate.name, rejected_status, type(exc).__name__, exc,
                )
                errors.append(f"{candidate.name}: {exc}")
                continue
            breaker.record_failure(candidate.name, exc)
            logger.warning(
                "provider '%s' failed mid-stream-setup: %s: %s", candidate.name, type(exc).__name__, exc,
            )
            errors.append(f"{candidate.name}: {exc}")
            if sent_any:
                yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="error")
                yield "data: [DONE]\n\n"
                return
            continue

        breaker.record_success(candidate.name)
        # ADR-0550 (WP-135): this is the ONLY routing-attribution channel
        # for a streaming call - see schemas.py's own ChatCompletionResponse
        # docstring ("streaming responses do not carry an equivalent
        # field") and routing_decisions.py's module docstring for why.
        # agent-runtime always streams, so without this the routing panel
        # would only ever work for non-agent-runtime callers.
        await routing_decisions.set_routing_decision(
            request_id,
            {
                "provider": candidate.name,
                "model": effective_model_name,
                "kind": candidate.kind,
                "classification": classification,
                "fallback_used": idx > 0,
                "fallback_from": candidates[0].name if idx > 0 else None,
            },
        )

        final_tool_calls = getattr(final_chunk, "tool_calls", None) or []
        if not sent_any and not final_tool_calls:
            reasoning_text = "".join(reasoning_parts)
            recovered = reasoning_fallback.should_fold("", False, reasoning_text)
            record_empty_response(candidate.name, effective_model_name, recovered=recovered)
            if recovered:
                logger.warning(
                    "provider '%s' streamed no content; serving its reasoning block "
                    "(%d chars) as content", candidate.name, len(reasoning_text),
                )
                yield _sse_chunk(
                    completion_id, created, effective_model_name,
                    {"content": reasoning_text.strip(), "zuno_reasoning_fallback": True},
                )
        if final_tool_calls:
            # `index` is required on a streamed tool_call delta (OpenAI wire
            # format): Open WebUI drops a delta without one, so the tool call
            # was lost and the turn showed blank (WP-191, 2026-11-03).
            wire_tool_calls = [
                {
                    "index": i,
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                }
                for i, tc in enumerate(final_tool_calls)
            ]
            yield _sse_chunk(completion_id, created, effective_model_name, {"tool_calls": wire_tool_calls})
            yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="tool_calls")
        else:
            yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="stop")
        if include_usage:
            yield _sse_usage_chunk(completion_id, created, effective_model_name, prompt_tokens, completion_tokens)
        yield "data: [DONE]\n\n"
        return

    logger.error("all eligible providers failed for classification %s: %s", classification, "; ".join(errors))
    yield _sse_chunk(completion_id, created, "none", {}, finish_reason="error")
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# ADR-0602 clause 9 (WP-225 lot A): `/v1/messages` (Anthropic Messages) and
# `/v1/responses` (OpenAI Responses), metered pass-through to a local model
# that speaks the protocol. Off by default (404, as before); see
# app/metered_paths.py. Open by decision: metered, never blocked by the
# metering, and capped only when the chart sets a ceiling (app/key_ceilings.py).


def _metered_upstream(
    model: str, classification: str, local_only: bool, agent: str, task: str,
) -> "tuple[Optional[str], Dict[str, Any], str]":
    """(provider, cfg, "") for the first provider mapped to `model` that is
    eligible for the effective classification and reachable, else (None, {}, why)."""
    names = metered_paths.model_map().get(model or "")
    if not names:
        return None, {}, f"model {model!r} is not served on this path"
    try:
        eligible = {c.name for c in routing_table.candidates_for(
            classification, local_only=local_only, exclude=model_routing_policy.exclude_for(agent, task),
        )}
    except RoutingError as exc:
        return None, {}, str(exc)
    for name in names:
        try:
            cfg = routing_table.provider_config(name)
        except StopIteration:
            continue
        if cfg.get("kind", "saas") != "local" or not cfg.get("endpoint") or name not in eligible:
            continue
        if cfg.get("via_maas") and not maas_adapter.should_use_maas(cfg, "local"):
            continue
        if _availability_skip(ProviderCandidate(name=name, kind="local"), cfg):
            continue
        return name, cfg, ""
    return None, {}, f"no provider serving {model!r} is eligible for classification {classification} and available"


def _metered_upstream_headers(
    cfg: Dict[str, Any], identity: CallerIdentity, request_id: str, quota_class: str,
    project_id: Optional[str], forwarded: Dict[str, str],
) -> Dict[str, str]:
    headers = {"Content-Type": "application/json", "X-Zuno-Request-Id": request_id, **forwarded}
    if cfg.get("via_maas"):
        headers["Authorization"] = f"Bearer {maas_adapter._maas_bearer_token(identity.token)}"
        if maas_adapter.gateway_identity_enabled():
            headers.update(maas_adapter.attested_headers(maas_adapter.MaasCallContext(
                sub=identity.persona, groups=tuple(identity.groups or ()),
                quota_class=quota_class or "standard", project_id=project_id,
            )))
    else:
        headers["Authorization"] = f"Bearer {os.getenv('LOCAL_MODEL_API_KEY', 'not-required')}"
    return headers


def _metered_client(cfg: Dict[str, Any]):
    ca_bundle = os.getenv("LOCAL_GPT_OSS_CA_BUNDLE")
    return httpx.AsyncClient(timeout=float(cfg.get("timeout_seconds", 60)), verify=ca_bundle or True)


def _meter(
    identity: CallerIdentity, quota_class: str, project_id: Optional[str],
    reservation: "key_ceilings.Reservation", prompt: int, completion: int,
) -> None:
    """The same quota path as a chat call: the token-budget ledger; and the
    metered-path ceiling, whose reservation the real usage replaces."""
    tokens = prompt + completion
    quota.ledger.consume(quota_class, identity.persona, identity.groups, project_id, tokens)
    key_ceilings.ceilings.settle(reservation, tokens)


class _MeteredStreamingResponse(StreamingResponse):
    """A StreamingResponse that runs `on_close` whatever happens to it: the body
    iterated to the end, cut, the client gone before the first byte, or the body
    never started. The upstream is closed and the call metered in every case."""

    def __init__(self, content, *, on_close, **kwargs):
        super().__init__(content, **kwargs)
        self._on_close = on_close

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._on_close()


async def _metered_call(
    api: str, body: Dict[str, Any], identity: CallerIdentity, *,
    classification_header: str, local_only_header: str, agent: str, task: str,
    request_id_header: str, run_id_header: str, quota_class_header: str, project_id_header: str,
    forwarded: Dict[str, str], count_tokens: bool = False, agent_verified: bool = False,
) -> Response:
    if not metered_paths.enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    if not isinstance(body, dict):
        return metered_paths.error(api, 400, "invalid_request", "the request body must be a JSON object")
    problem = metered_paths.request_problem(api, body)
    if problem:
        return metered_paths.error(api, 400, "unsupported_parameter", problem)
    model = str(body.get("model") or "")
    set_caller_client(identity.client)
    set_caller_persona(identity.persona)
    # The same classification as a chat call: the client's model alias selects a
    # task (ADR-0596), the WP-209 floor includes the per-client floor, and the
    # ADR-0594 markers of the tool results raise the level and can make it local-only.
    task = model_tasks.task_for(identity.client, model, task)
    set_caller_task(task)
    floor = classification_floor.floors.effective(
        classification_floor.declared_level(classification_header), agent, task, identity.client,
        agent_verified=agent_verified,
    )
    classification = floor.effective
    local_only = local_only_header.strip().lower() == "true" or model_routing_policy.local_only_for_classification(
        agent, task, classification
    )
    marks = tool_markers.assess(metered_paths.marker_messages(api, body), classification, local_only, identity.client)
    if marks.changed:
        logger.info(
            "metered %s: classification raised by tool results: %s -> %s, local_only %s -> %s (%s) client=%s",
            api, classification, marks.classification, local_only, marks.local_only,
            ", ".join(sorted(set(marks.reasons))), identity.client,
        )
        classification = marks.classification
        local_only = marks.local_only or model_routing_policy.local_only_for_classification(
            agent, task, classification
        )
    request_id = request_id_header.strip() or str(uuid.uuid4())
    run_id = run_id_header.strip() or None
    quota_class, project_id = _platform_context(identity, quota_class_header, project_id_header)

    provider, cfg, why = _metered_upstream(model, classification, local_only, agent, task)
    if provider is None:
        status = 404 if "not served" in why else 400
        return metered_paths.error(api, status, "model_not_available", why)
    upstream_body = metered_paths.upstream_body(api, body, cfg.get("maas_model_ref", cfg.get("model", model)))
    headers = _metered_upstream_headers(cfg, identity, request_id, quota_class, project_id, forwarded)
    unreachable = f"the model behind {model!r} is unreachable"

    if count_tokens:
        # Counting generates nothing: not metered, not scanned.
        try:
            async with _metered_client(cfg) as client:
                resp = await client.post(metered_paths.upstream_url(cfg, api, "/count_tokens"),
                                         json=upstream_body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("metered upstream %s failed: %s: %s", provider, type(exc).__name__, exc)
            return metered_paths.error(api, 502, "upstream_unavailable", unreachable)
        return Response(resp.content, status_code=resp.status_code,
                        media_type=resp.headers.get("content-type", "application/json"))

    streaming = bool(body.get("stream"))
    prompt_estimate = metered_paths.estimate_prompt_tokens(api, body)
    # The ceiling (with a reservation, so parallel calls see each other), then the
    # token budget: both refuse in the protocol's 429 shape.
    ceiling, reservation = key_ceilings.ceilings.admit(
        identity.persona, identity.client, identity.groups,
        estimate=prompt_estimate + metered_paths.requested_output_tokens(api, body), stream=streaming,
    )
    if ceiling is not None:
        logger.warning("metered-path ceiling reached: api=%s %s=%s ceiling=%d/%s",
                       api, ceiling.dimension, ceiling.subject, ceiling.ceiling, ceiling.window)
        return metered_paths.error(api, 429, "rate_limit_exceeded", ceiling.message(),
                                   headers={"Retry-After": str(ceiling.retry_after)},
                                   dimension=ceiling.dimension)

    def refuse(response: Response) -> Response:
        key_ceilings.ceilings.settle(reservation, 0)
        return response

    try:
        denial = quota.ledger.check(quota_class, identity.persona, identity.groups, project_id)
        if denial is not None and _budget_fault_rides_through(denial, quota_class):
            denial = None
        if denial is not None:
            return refuse(metered_paths.error(
                api, 429, "quota_exceeded",
                f"token budget exhausted: {denial.dimension} budget of {denial.budget} tokens per {denial.window}",
                headers={"Retry-After": str(denial.retry_after)} if denial.retry_after else None,
                dimension=denial.dimension,
            ))

        gr_mode = guardrails.mode_for(classification, agent)
        # Block mode also scans the system-level text: a client may carry
        # retrieved context there (ADR-0602 clause 8).
        gr_items = metered_paths.scan_items(api, body, include_system=gr_mode == "block") if gr_mode != "off" else []
        gr_prompt = next((it.text for it in gr_items if it.kind == "prompt"), "")
        gr_extra = [it.text for it in gr_items if it.kind not in ("prompt", "system")]
        fail_closed = guardrails.fails_closed(classification)
        if gr_mode == "block":
            found = await guardrails.evaluate(
                [it.text for it in gr_items], agent=agent or "unknown", run_id=run_id or "",
                project_id=project_id, mode="block",
            )
            if found:
                stage = guardrails.stage_of(found, gr_items)
                return refuse(metered_paths.error(
                    api, 400, "guardrails_blocked", f"the {stage} was refused by the guardrails policy",
                    stage=stage, detections=sorted({str(d.get("detection")) for d in found})))
            if found is None and fail_closed:
                return refuse(metered_paths.error(
                    api, 503, "guardrails_unavailable", guardrails.unavailable_body("prompt")["error"]["message"],
                    stage="prompt"))

        url = metered_paths.upstream_url(cfg, api)
        span_args = dict(
            provider=provider, model=upstream_body["model"], classification=classification,
            request_id=request_id, caller_sub=identity.sub, groups=identity.groups, agent=agent,
            run_id=run_id, model_kind="local", project_id=project_id,
        )

        if not streaming:
            return await _metered_unary(
                api, url, cfg, upstream_body, headers, span_args, identity, quota_class, project_id,
                reservation, prompt_estimate, gr_mode, gr_prompt, gr_extra, fail_closed, agent, run_id,
                provider, unreachable,
            )

        client = _metered_client(cfg)
        try:
            resp = await client.send(client.build_request("POST", url, json=upstream_body, headers=headers),
                                     stream=True)
        except httpx.HTTPError as exc:
            await client.aclose()
            breaker.record_failure(provider, exc)
            logger.warning("metered upstream %s failed: %s: %s", provider, type(exc).__name__, exc)
            return refuse(metered_paths.error(api, 502, "upstream_unavailable", unreachable))
        if resp.status_code != 200:
            content = await resp.aread()
            await resp.aclose()
            await client.aclose()
            return refuse(Response(content, status_code=resp.status_code,
                                   media_type=resp.headers.get("content-type", "application/json")))
    except BaseException:
        key_ceilings.ceilings.settle(reservation, 0)
        raise

    meter = metered_paths.StreamMeter(api)
    reply: List[str] = []
    closed = {"done": False}

    def usage() -> "tuple[int, int]":
        prompt = meter.prompt if meter.usage_seen and meter.prompt else prompt_estimate
        completion = meter.completion
        if not completion and meter.generated:
            # Cut, or disconnected, before the final usage event.
            completion = meter.generated // _CHARS_PER_TOKEN + 1
        return prompt, completion

    async def finish() -> None:
        """Close the upstream and meter the call, once."""
        if closed["done"]:
            return
        closed["done"] = True
        try:
            await resp.aclose()
            await client.aclose()
        finally:
            prompt, completion = usage()
            _meter(identity, quota_class, project_id, reservation, prompt, completion)
            if gr_mode == "observe":
                guardrails.observe_exchange(message=gr_prompt, reply="".join(reply), agent=agent or "unknown",
                                            run_id=run_id or "", project_id=project_id, extra=gr_extra)

    async def events() -> AsyncIterator["tuple[str, str]"]:
        try:
            with model_call_span(**span_args) as call:
                try:
                    async for raw, data in metered_paths.sse_events(resp.aiter_lines()):
                        text = meter.observe(data)
                        if text:
                            reply.append(text)
                        yield raw, text
                finally:
                    prompt, completion = usage()
                    call.record_usage(prompt_tokens=prompt, completion_tokens=completion)
        finally:
            await finish()

    if gr_mode == "block":
        stream = stream_guard.guard(
            events(),
            evaluate=_guarded_reply_evaluator(agent=agent, run_id=run_id, project_id=project_id),
            error_event=stream_guard.anthropic_error_event if api == metered_paths.ANTHROPIC
            else stream_guard.responses_error_event,
            fail_closed=fail_closed,
        )
    else:
        async def stream_raw() -> AsyncIterator[str]:
            inner = events()
            try:
                async for raw, _text in inner:
                    yield raw
            finally:
                await inner.aclose()
        stream = stream_raw()
    return _MeteredStreamingResponse(stream, on_close=finish, media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _metered_unary(
    api, url, cfg, upstream_body, headers, span_args, identity, quota_class, project_id,
    reservation, prompt_estimate, gr_mode, gr_prompt, gr_extra, fail_closed, agent, run_id,
    provider, unreachable,
) -> Response:
    with model_call_span(**span_args) as call:
        try:
            async with _metered_client(cfg) as client:
                resp = await client.post(url, json=upstream_body, headers=headers)
        except httpx.HTTPError as exc:
            key_ceilings.ceilings.settle(reservation, 0)
            breaker.record_failure(provider, exc)
            logger.warning("metered upstream %s failed: %s: %s", provider, type(exc).__name__, exc)
            return metered_paths.error(api, 502, "upstream_unavailable", unreachable)
        if resp.status_code != 200:
            key_ceilings.ceilings.settle(reservation, 0)
            return Response(resp.content, status_code=resp.status_code,
                            media_type=resp.headers.get("content-type", "application/json"))
        try:
            payload = resp.json()
            if not isinstance(payload, dict):
                raise ValueError("not a JSON object")
        except ValueError:
            # The model ran (a 200) but the reply is unreadable: metered by estimate.
            call.record_usage(prompt_tokens=prompt_estimate, completion_tokens=0)
            _meter(identity, quota_class, project_id, reservation, prompt_estimate, 0)
            logger.warning("metered upstream %s answered 200 with a body that is not a JSON object", provider)
            return metered_paths.error(api, 502, "upstream_invalid_reply", "the model's reply is not valid JSON")
        prompt_tokens, completion_tokens = metered_paths.usage_of(api, payload)
        if not prompt_tokens and not completion_tokens:
            prompt_tokens = prompt_estimate
            text = metered_paths.reply_text(api, payload)
            completion_tokens = len(text) // _CHARS_PER_TOKEN + 1 if text else 0
        call.record_usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        _meter(identity, quota_class, project_id, reservation, prompt_tokens, completion_tokens)
    if gr_mode == "block":
        found = await guardrails.evaluate(
            [metered_paths.reply_text(api, payload)], agent=agent or "unknown", run_id=run_id or "",
            project_id=project_id, mode="block",
        )
        if found:
            return metered_paths.error(api, 400, "guardrails_blocked",
                                       "the reply was refused by the guardrails policy", stage="reply",
                                       detections=sorted({str(d.get("detection")) for d in found}))
        if found is None and fail_closed:
            return metered_paths.error(api, 503, "guardrails_unavailable",
                                       guardrails.unavailable_body("reply")["error"]["message"], stage="reply")
    elif gr_mode == "observe":
        guardrails.observe_exchange(message=gr_prompt, reply=metered_paths.reply_text(api, payload),
                                    agent=agent or "unknown", run_id=run_id or "",
                                    project_id=project_id, extra=gr_extra)
    return JSONResponse(payload)


def _forwarded(request: Request) -> Dict[str, str]:
    return {h: request.headers[h] for h in metered_paths.FORWARDED_HEADERS if h in request.headers}


async def _metered_endpoint(api: str, request: Request, identity: CallerIdentity, count_tokens: bool = False) -> Response:
    if not metered_paths.enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        body = await request.json()
    except ValueError:
        return metered_paths.error(api, 400, "invalid_request", "the request body is not valid JSON")
    h = request.headers
    agent, task, agent_verified = _agent_identity(
        h.get(signed_chain.HEADER, ""), h.get("X-Zuno-Agent", ""), h.get("X-Zuno-Task", ""), identity
    )
    return await _metered_call(
        api, body, identity,
        classification_header=h.get("X-Zuno-Data-Classification", ""),
        local_only_header=h.get("X-Zuno-Local-Only", "false"),
        agent=agent, task=task,
        request_id_header=h.get("X-Zuno-Request-Id", ""), run_id_header=h.get("X-Zuno-Run-Id", ""),
        quota_class_header=h.get("X-Zuno-Quota-Class", ""), project_id_header=h.get("X-Zuno-Project-Id", ""),
        forwarded=_forwarded(request), count_tokens=count_tokens, agent_verified=agent_verified,
    )


@app.post("/v1/messages", dependencies=[Depends(adopt_incoming_trace_context)])
async def anthropic_messages(request: Request, identity: CallerIdentity = Depends(validate_token)) -> Response:
    return await _metered_endpoint(metered_paths.ANTHROPIC, request, identity)


@app.post("/v1/messages/count_tokens", dependencies=[Depends(adopt_incoming_trace_context)])
async def anthropic_count_tokens(request: Request, identity: CallerIdentity = Depends(validate_token)) -> Response:
    return await _metered_endpoint(metered_paths.ANTHROPIC, request, identity, count_tokens=True)


@app.post("/v1/responses", dependencies=[Depends(adopt_incoming_trace_context)])
async def openai_responses(request: Request, identity: CallerIdentity = Depends(validate_token)) -> Response:
    return await _metered_endpoint(metered_paths.RESPONSES, request, identity)
