"""One A2A agent = one admitted OKF agent, answered with the caller's own identity.

Per turn: the agent's task prompt from the admitted agents release, a model call through the
ai-gateway (routing, guardrails and quota apply to the real user), and an optional bounded tool
loop through the mcp-gateway (the five-factor policy applies to the same token). The delegation
headers of ADR-0401/0403/0406 are checked here and passed on unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart
from a2a.utils import new_agent_text_message

from app.agent_chain import ChainError, DelegationLimits, parse_chain, verify_chain
from app.agent_declarations import AgentDeclaration, AgentDeclarationStore
from app.auth import CallerIdentity
from app.clients import (
    AiGatewayClient, DownstreamError, McpGatewayClient, parse_arguments, raise_classification, to_openai_tools,
)
from app.config import Settings

logger = logging.getLogger("a2a_gateway.executor")

CHAIN_HEADERS = ("X-Zuno-Delegated-By", "X-Zuno-Delegation-Depth")


class Refused(Exception):
    """The request is not acceptable; the message is shown to the caller."""


class ZunoAgentExecutor(AgentExecutor):
    def __init__(
        self,
        agent: AgentDeclaration,
        store: AgentDeclarationStore,
        limits: DelegationLimits,
        settings: Settings,
        llm: AiGatewayClient,
        tools: McpGatewayClient,
    ) -> None:
        self._agent = agent
        self._store = store
        self._limits = limits
        self._settings = settings
        self._llm = llm
        self._tools = tools

    # -- A2A entry points ---------------------------------------------------

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if context.current_task is None:
            await updater.submit()
        await updater.start_work()
        try:
            text = await self._answer(context)
        except (Refused, ChainError, DownstreamError) as exc:
            await updater.failed(new_agent_text_message(str(exc), context.context_id, context.task_id))
            return
        except Exception:
            logger.exception("agent %s failed", self._agent.name)
            await updater.failed(new_agent_text_message("The agent failed to answer.", context.context_id, context.task_id))
            return
        await updater.add_artifact([Part(root=TextPart(text=text))], name="answer")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

    # -- one turn -----------------------------------------------------------

    def _caller(self, context: RequestContext) -> CallerIdentity:
        caller = (context.call_context.state if context.call_context else {}).get("caller")
        if not isinstance(caller, CallerIdentity):
            raise Refused("The caller is not authenticated.")
        return caller

    def _task_name(self, context: RequestContext) -> str:
        metadata = (context.message.metadata if context.message else None) or {}
        task = str(metadata.get("task") or self._agent.primary_task)
        if task not in self._agent.tasks:
            raise Refused(f"Agent '{self._agent.name}' has no task '{task}'.")
        return task

    async def _answer(self, context: RequestContext) -> str:
        caller = self._caller(context)
        headers = (context.call_context.state.get("headers") or {}) if context.call_context else {}
        request_text = context.get_user_input().strip()
        if not request_text:
            raise Refused("The message is empty.")
        if len(request_text) > self._settings.max_message_chars:
            raise Refused("The message is too long.")

        task = self._task_name(context)
        lowered = {k.lower(): v for k, v in headers.items()}
        chain = parse_chain(lowered.get("x-zuno-delegated-by"), lowered.get("x-zuno-delegation-depth"))
        reason = verify_chain(chain, self._agent.name, task, caller.groups, self._store, self._limits)
        if reason:
            raise Refused(reason)
        chain_headers = {h: lowered[h.lower()] for h in CHAIN_HEADERS if lowered.get(h.lower())}

        classification = raise_classification(
            self._agent.classification or "C1", lowered.get("x-zuno-data-classification", "")
        )
        run_id = context.task_id or ""
        common = dict(
            token=caller.token, agent=self._agent.name, task=task,
            classification=classification, run_id=run_id, chain_headers=chain_headers,
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._agent.system_prompt(task)},
            {"role": "user", "content": request_text},
        ]
        tools = await self._available_tools(common)
        offered = {t["function"]["name"] for t in tools or []}
        for _ in range(self._settings.max_tool_rounds + 1):
            reply = await self._llm.chat(messages=messages, tools=tools, **common)
            calls = reply.get("tool_calls") or []
            if not calls or not tools:
                return str(reply.get("content") or "").strip() or "The agent has no answer."
            messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
            for call in calls:
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                if name not in offered:  # never run a tool that was not offered (read-only, listed for this task)
                    result = f"The tool {name} is not available."
                else:
                    result = await self._tools.call_tool(name, parse_arguments(function.get("arguments")), **common)
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
        # Out of rounds: ask once more without tools so the user gets a final answer.
        reply = await self._llm.chat(messages=messages, tools=None, **common)
        return str(reply.get("content") or "").strip() or "The agent has no answer."

    async def _available_tools(self, common: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        if not self._settings.tools_enabled or not self._agent.tasks.get(common["task"]):
            return None
        try:
            listed = await self._tools.list_tools(**common)
        except DownstreamError as exc:
            logger.info("no tools for %s/%s: %s", self._agent.name, common["task"], exc)
            return None
        except Exception:
            logger.warning("tool listing failed for %s", self._agent.name, exc_info=True)
            return None
        # No approval exists across hops (ADR-0409, WP-173 step 5): only tools that declare themselves
        # read-only are offered, so a write can never run here without the approval UnifAI would ask.
        read_only = [t for t in listed if (t.get("annotations") or {}).get("readOnlyHint") is True]
        return to_openai_tools(read_only) or None
