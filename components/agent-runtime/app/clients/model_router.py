"""Thin client for the AI Inference Gateway (ADR-0009, ADR-0020, ADR-0021).

Routing, fallback-across-providers and classification-eligibility now live
entirely in components/ai-gateway - this module only builds a
langchain_openai.ChatOpenAI pointed at the gateway's OpenAI-compatible
/v1/chat/completions endpoint. Using ChatOpenAI (rather than a raw httpx
client) means app/graph/nodes.py's reason_node and app/main.py's
_stream_chat need zero changes: LangGraph's astream_events(version="v2")
keeps emitting on_chat_model_stream events exactly as it did when this
module talked to providers directly - it's still a real LangChain chat
model object being invoked, only what's on the other end of the HTTP call
changed. See components/ai-gateway/README.md's "Why agent-runtime's
streaming needs no code changes" for the full reasoning.

Before this split, this module held five provider-specific factory
functions and the classification-eligibility/fallback loop itself (moved
verbatim to components/ai-gateway/app/{routing,providers}.py) - this file
holds no provider API key and does not resolve routing/eligibility.

ADR-0544's one exception: app/graph/prompt_budget.py (imported by
app/graph/nodes.py and arkos_nodes.py, not by this module itself) reads
ONE field out of the same provider-routing.yaml ConfigMap - `max_model_len`
per local provider, never `eligible_for`/`prefer`/anything routing-shaped -
to clamp an assembled prompt before it ever reaches this client. Noted
here since the paragraph above otherwise reads as a blanket "never", which
this narrow exception does not actually contradict: nothing in THIS module
reads that file.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

logger = logging.getLogger("agent_runtime.model_router")

AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc:8080")


async def fetch_routing_decision(request_id: Optional[str], bearer_token: str) -> Optional[Dict[str, Any]]:
    """ADR-0550 (WP-135): best-effort fetch of ai-gateway's own record of
    which provider/model actually served this turn's model call(s),
    published via components/ai-gateway/app/routing_decisions.py and keyed
    by the same request_id every model call in this turn already forwards
    as X-Zuno-Request-Id.

    This client genuinely cannot recover that from the model call's own
    return value: `langchain_openai.ChatOpenAI` only parses the standard
    OpenAI response schema, silently dropping ai-gateway's own
    `zuno_provider` extension field, and the streaming SSE path this
    gateway actually uses for every real chat turn carries no equivalent
    field at all - see ai-gateway's schemas.py/routing_decisions.py
    docstrings. Called once per turn (app/main.py), not once per internal
    model call - a turn with more than one call (e.g. Arkos's draft then
    reflect) shares one request_id, so this naturally reports whichever
    call ran last, the same "what actually answered you" a user expects.

    Never raises - a fetch failure (network, 404, malformed body) degrades
    to None, and the caller must fall back to its own placeholder routing
    metadata. This is purely an ADR-0550 decision 9 observability feature,
    never a routing or security control.
    """
    if not request_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{AI_GATEWAY_URL}/v1/routing-decisions/{request_id}",
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - a fetch failure must never affect the chat turn already served
        logger.warning("routing-decision fetch failed for request_id=%s: %s", request_id, exc)
        return None


@dataclass
class ProviderCandidate:
    """Kept only so callers (app/graph/nodes.py:reason_node) can keep
    reading `provider.name` unchanged. Always "ai-gateway" now - this
    client genuinely doesn't know which downstream provider served a
    request anymore; that detail lives in the gateway's own OTel traces.
    """

    name: str


class ModelRouterError(RuntimeError):
    pass


class ModelRouter:
    def chat_model_for(
        self,
        classification: str,
        bearer_token: str,
        local_only: bool = False,
        request_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        task_name: Optional[str] = None,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> BaseChatModel:
        headers = {
            "X-Zuno-Data-Classification": classification.upper(),
            # ADR-0035: source-level restriction independent of
            # classification - set when a source this turn (e.g.
            # Confluence) declared external_model_policy.allow_context:
            # false, forcing the gateway to only consider local
            # candidates regardless of what this classification would
            # otherwise allow.
            "X-Zuno-Local-Only": "true" if local_only else "false",
        }
        # ADR-0303 (WP-39): lets ai-gateway's model_routing_policy.py
        # resolve a declared adapter for this (agent, task) pair -
        # X-Zuno-Task existed before this WP but nothing sent it yet;
        # this is the first real caller of both headers.
        if agent_name:
            headers["X-Zuno-Agent"] = agent_name
        if task_name:
            headers["X-Zuno-Task"] = task_name
        if request_id:
            # ADR-0201/WP-27: lets ai-gateway (and, when routed via MaaS,
            # MaaS's own usage metrics) correlate back to this exact chat
            # turn - see components/ai-gateway/app/telemetry.py's
            # model_call_span and app/maas_adapter.py.
            headers["X-Zuno-Request-Id"] = request_id
        if project_id:
            # ADR-0528 (superseding ADR-0512 clause 3's keying): this is
            # the ZUNO project id - a server-minted UUID - and never the
            # Salesforce opportunity id, which is not emitted in any header
            # or span.
            #
            # It used to be gated on the task's own project_required mark,
            # because state["project_id"] was copied verbatim from the
            # request body and a caller could otherwise shift consumption
            # onto an arbitrary project's quota bucket by asserting a
            # string nothing verified. That gate is gone, and the guarantee
            # is stronger rather than weaker: ADR-0527 removed the
            # client-asserted value from _initial_state entirely, so the id
            # reaching here was resolved by app/main.py's agent_chat from
            # the conversation's own projects row AFTER verifying the
            # caller holds a grant on it. Database-verified membership beats
            # a frontmatter mark, and it covers every project - customer or
            # free - rather than only Salesforce-backed ones.
            #
            # ai-gateway's quota.py draws the project budget down first when
            # this header is present (ADR-0511 clause 2's precedence).
            headers["X-Zuno-Project-Id"] = project_id
        if run_id:
            # ADR-0543: lets ai-gateway tag its model_call span with the
            # calling chat turn's run_id, distinct from X-Zuno-Request-Id
            # (per-call correlation id) - run_id is the whole conversation
            # turn's identifier, needed for the per-run resource dashboard.
            headers["X-Zuno-Run-Id"] = run_id
        if max_tokens:
            # ADR-0544: per-REQUEST generation ceiling (app/registry.py's
            # TaskDefinition.max_tokens, from the task's own OKF
            # frontmatter) - distinct from every other header above,
            # which are per-CALL identity/routing metadata, not a
            # provider-config value. Positive decimal integer, no units,
            # no sign, no whitespace; omitted (not "0"/"") when absent so
            # ai-gateway's own parsing stays a simple presence check.
            headers["X-Zuno-Max-Tokens"] = str(int(max_tokens))
        return ChatOpenAI(
            base_url=f"{AI_GATEWAY_URL}/v1",
            # ADR-0032: forward the same validated end-user token the
            # Runtime itself received (langchain-openai sends `api_key` as
            # `Authorization: Bearer <api_key>`) - never the
            # "not-required" placeholder ADR-0032 explicitly forbids
            # outside local dev mocks. ai-gateway's own validate_token
            # (components/ai-gateway/app/auth.py) only needs a valid
            # authenticated caller and doesn't key any authorization
            # decision on identity/groups (routing is classification-header
            # driven, see that module's docstring) - reusing the end-user
            # token here satisfies that requirement without standing up a
            # separate Keycloak service-identity/client-credentials flow
            # that nothing downstream would actually consume yet.
            api_key=bearer_token,
            # Ignored by the gateway for v0 - routing is entirely
            # classification-driven (see the X-Zuno-Data-Classification
            # default_header below), not model-name-driven. Required by
            # the OpenAI wire schema regardless.
            model="zuno-auto",
            default_headers=headers,
        )

    async def invoke_with_fallback(
        self,
        classification: str,
        messages: List[Any],
        bearer_token: str,
        local_only: bool = False,
        request_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        task_name: Optional[str] = None,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tools: Optional[List[Any]] = None,
        max_tokens: Optional[int] = None,
    ):
        """Kept as async + same name/signature as before this split (plus
        `bearer_token`/`local_only`, added for ADR-0032/ADR-0035) so
        app/graph/nodes.py:reason_node barely changes. The multi-provider
        fallback loop this name used to describe runs server-side in the
        gateway now (app/main.py:_invoke_with_fallback there) - this is a
        single HTTP call.

        `tags` (ADR-0215): passed through to LangChain's own `config`,
        surfacing on every event `astream_events` emits for this call
        (`event["tags"]`) without changing what's sent over the wire to
        ai-gateway. app/main.py:_stream_chat uses this to filter the
        conversation-history compaction node's internal model call
        (tagged "zuno-internal") out of the user-visible SSE token
        stream - every other caller passes nothing and keeps today's
        exact behavior.

        `tools` (ADR-0415): LangChain tool schemas (or raw OpenAI-format
        dicts - bind_tools accepts either), applied via the model's own
        `.bind_tools()` before invoking - components/ai-gateway's
        ChatCompletionRequest.tools field and _to_langchain_messages/
        _invoke_with_fallback/_stream_completion are what actually forward
        them to the selected provider and parse back any tool_calls the
        model chose to make. The returned `result` is the raw AIMessage;
        callers inspect `result.tool_calls` themselves (reason_node), same
        as they already read `result.content`.
        """
        model = self.chat_model_for(
            classification=classification,
            bearer_token=bearer_token,
            local_only=local_only,
            request_id=request_id,
            agent_name=agent_name,
            task_name=task_name,
            project_id=project_id,
            run_id=run_id,
            max_tokens=max_tokens,
        )
        if tools:
            model = model.bind_tools(tools)
        try:
            if tags:
                result = await model.ainvoke(messages, config={"tags": tags})
            else:
                result = await model.ainvoke(messages)
        except Exception as exc:
            logger.error(
                "AI Inference Gateway call failed for classification %s: %s", classification, exc
            )
            raise ModelRouterError(f"AI Inference Gateway call failed: {exc}") from exc
        return result, ProviderCandidate(name="ai-gateway")
