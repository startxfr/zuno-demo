"""Zuno AI Inference Gateway (ADR-0009, ADR-0020, ADR-0021).

OpenAI-compatible `POST /v1/chat/completions`: resolves the eligible
provider fallback chain for the caller-declared `X-Zuno-Data-Classification`
header, then either invokes (non-streaming) or streams (`stream: true`)
the first provider that succeeds. See README.md for the exact HTTP API
contract, and docs/adr/0009-*.md for why this exists as a service separate
from components/agent-runtime.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app import quota, semantic_cache
from app.auth import CallerIdentity, validate_token
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
)
from app.telemetry import init_telemetry, model_call_span, record_cache_outcome

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ai_gateway")

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


@app.post("/admin/reload-routing")
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
    return {"loaded": routing_table.loaded}


# --------------------------------------------------------------------------
# ADR-0309 (WP-42) - bounded autonomous tuning admin surface. These
# endpoints are the operator's window into the tuner: the audit trail,
# outcome reporting (live monitoring feeds the observed window metrics
# in), and the kill switch. Only reachable in-cluster (this service has
# no public Route; NetworkPolicy admits agent-runtime + the acceptance
# gate only), same trust model as /admin/reload-routing above.
# --------------------------------------------------------------------------


@app.get("/admin/optimizer/audit")
async def optimizer_audit() -> Dict[str, Any]:
    return {
        "enabled": tuning_controller.policy.enabled,
        "kill_switch": tuning_controller.policy.kill_switch,
        "audit": tuning_controller.audit_log(),
    }


@app.post("/admin/optimizer/outcome")
async def optimizer_outcome(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reports the observed evaluation-window metrics; the controller
    auto-rolls-back every open action on a trigger breach."""
    rolled_back = tuning_controller.report_outcome(
        error_rate=float(payload.get("error_rate", 0.0)),
        quality=payload.get("quality"),
    )
    return {"rolled_back": [e.parameter for e in rolled_back]}


@app.post("/admin/optimizer/kill")
async def optimizer_kill() -> Dict[str, Any]:
    reverted = tuning_controller.kill()
    return {"reverted": [e.parameter for e in reverted]}


@app.post("/admin/optimizer/apply")
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


@app.post("/v1/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    identity: CallerIdentity = Depends(validate_token),
    x_zuno_data_classification: str = Header(default="C1", alias="X-Zuno-Data-Classification"),
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
    # zuno.quota_class (absent = standard), and the ADR-0512 verified
    # project binding - both only ever set platform-side (agent-runtime);
    # the BFF strips inbound copies from end users. The same two headers
    # key the Kuadrant request-rate dimension.
    x_zuno_quota_class: str = Header(default="standard", alias="X-Zuno-Quota-Class"),
    x_zuno_project_id: str = Header(default="", alias="X-Zuno-Project-Id"),
    # ADR-0544: per-request generation ceiling - components/agent-runtime's
    # ModelRouter forwards a task's own declared max_tokens (OKF frontmatter)
    # this way rather than through payload.model or per-provider config,
    # since it is a per-CALL value, not a routing decision or a provider
    # default. Optional; absent means no cap, today's exact behavior.
    x_zuno_max_tokens: str = Header(default="", alias="X-Zuno-Max-Tokens"),
):
    classification = x_zuno_data_classification.upper()
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
    request_id = x_zuno_request_id.strip() or str(uuid.uuid4())
    run_id = x_zuno_run_id.strip() or None
    quota_class = x_zuno_quota_class.strip() or "standard"
    project_id = x_zuno_project_id.strip() or None
    max_tokens = _parse_max_tokens(x_zuno_max_tokens)
    # ADR-0511: token-budget check BEFORE dispatch, on top of (never
    # instead of) the classification/eligibility intersection below.
    # Exhaustion is an explicit 429, never silent degradation.
    denial = quota.ledger.check(quota_class, identity.sub, identity.groups, project_id)
    if denial is not None:
        return JSONResponse(denial.detail(), status_code=429)
    # ADR-0412: per-(agent,task) preference from the git-managed policy
    # only (never the ADR-0309 autonomy surface - "prefer" is on the
    # optimizer's code-level denylist). Only permutes the candidates that
    # survive the eligibility/local-only filtering inside candidates_for -
    # it can never widen what ADR-0021/0035 allow. ADR-0417: `strict`
    # narrows that permutation into an exclusion (no unlisted survivor) for
    # entries that opt in - see model_routing_policy.py/routing.py.
    preference = model_routing_policy.preference_for(x_zuno_agent, x_zuno_task)
    strict_preference = model_routing_policy.strict_for(x_zuno_agent, x_zuno_task)
    try:
        candidates = routing_table.candidates_for(
            classification, local_only=local_only, prefer=preference, strict=strict_preference
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

    if payload.stream:
        return StreamingResponse(
            _stream_completion(
                candidates, classification, messages, request_id, adapter_decl,
                identity=identity, tools=payload.tools, agent=x_zuno_agent, run_id=run_id,
                project_id=project_id, quota_class=quota_class, max_tokens=max_tokens,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return await _invoke_with_fallback(
        candidates,
        classification,
        messages,
        caller_sub=identity.sub,
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
    x_zuno_data_classification: str = Header(default="C1", alias="X-Zuno-Data-Classification"),
    x_zuno_request_id: str = Header(default="", alias="X-Zuno-Request-Id"),
):
    classification = x_zuno_data_classification.upper()
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
) -> ChatCompletionResponse:
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
            return ChatCompletionResponse(**cached)

    errors: List[str] = []
    for idx, candidate in enumerate(candidates):
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
                model = chat_model_for(
                    candidate, cfg, request_id=request_id, adapter=adapter_name,
                    caller_bearer_token=caller_bearer_token, max_tokens=max_tokens,
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
                    quota_class, caller_sub, groups, project_id,
                    prompt_tokens + completion_tokens,
                )
        except Exception as exc:
            logger.warning(
                "provider '%s' failed for caller=%s, trying next fallback: %s",
                candidate.name, caller_sub, exc,
            )
            errors.append(f"{candidate.name}: {exc}")
            continue

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
        )
        if cache_key is not None:
            cacheable = response.model_dump(include={"model", "choices", "usage", "zuno_provider"})
            await semantic_cache.set_cached_response(cache_key, cacheable)
        return response

    raise HTTPException(
        status_code=502,
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

    for idx, candidate in enumerate(candidates):
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
                model = chat_model_for(
                    candidate, cfg, request_id=request_id, adapter=adapter_name,
                    caller_bearer_token=identity.token if identity else None,
                    max_tokens=max_tokens,
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
                async for event in model.astream(messages):
                    final_chunk = event if final_chunk is None else final_chunk + event
                    token = getattr(event, "content", "") or ""
                    if token:
                        sent_any = True
                        yield _sse_chunk(completion_id, created, effective_model_name, {"content": token})
                prompt_tokens, completion_tokens = _usage_tokens(final_chunk)
                call.record_usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
                # ADR-0511: attribute consumption per the precedence order,
                # same call as the non-streaming path above - see this
                # function's own quota_class parameter comment for why this
                # was missing until now.
                if identity is not None:
                    quota.ledger.consume(
                        quota_class, identity.sub, identity.groups, project_id,
                        prompt_tokens + completion_tokens,
                    )
        except Exception as exc:
            logger.warning("provider '%s' failed mid-stream-setup: %s", candidate.name, exc)
            errors.append(f"{candidate.name}: {exc}")
            if sent_any:
                yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="error")
                yield "data: [DONE]\n\n"
                return
            continue

        final_tool_calls = getattr(final_chunk, "tool_calls", None) or []
        if final_tool_calls:
            wire_tool_calls = [
                {
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                }
                for tc in final_tool_calls
            ]
            yield _sse_chunk(completion_id, created, effective_model_name, {"tool_calls": wire_tool_calls})
            yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="tool_calls")
        else:
            yield _sse_chunk(completion_id, created, effective_model_name, {}, finish_reason="stop")
        yield "data: [DONE]\n\n"
        return

    logger.error("all eligible providers failed for classification %s: %s", classification, "; ".join(errors))
    yield _sse_chunk(completion_id, created, "none", {}, finish_reason="error")
    yield "data: [DONE]\n\n"
