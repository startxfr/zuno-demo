"""One A2A agent = one admitted OKF agent, answered with the caller's own identity.

Per turn: the agent's task prompt from the admitted agents release, a model call through the
ai-gateway (routing, guardrails and quota apply to the real user), and an optional bounded tool
loop through the mcp-gateway (the five-factor policy applies to the same token). The delegation
headers of ADR-0401/0403/0406 are checked here and passed on unchanged.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Message, Part, Role, TaskState, TextPart
from a2a.utils import new_agent_text_message

from app.agent_chain import ChainError, DelegationLimits, parse_chain, verify_chain
from app.agent_declarations import AgentDeclaration, AgentDeclarationStore
from app.approvals import APPROVAL_KEY, DECISIONS, PendingApproval, PendingStore, answer_in, redact_arguments
from app.auth import CallerIdentity
from app.clients import (
    AiGatewayClient, DownstreamError, McpGatewayClient, parse_arguments, raise_classification, to_openai_tools,
)
from app.config import Settings

logger = logging.getLogger("a2a_gateway.executor")

CHAIN_HEADERS = ("X-Zuno-Delegated-By", "X-Zuno-Delegation-Depth")
# Task metadata key carrying the classification the turn ran at (ADR-0403 clause 5): the caller raises its own
# run to at least this level. Metadata, not a response header, because a delegator polls tasks/get.
CLASSIFICATION_METADATA = "zuno.classification"


_RUN_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _run_id(value: Optional[str]) -> str:
    """The caller's run id for tracing (a UnifAI session id), only when it is a plain token."""
    return value if value and _RUN_ID.match(value) else ""


def _max_tokens(value: Optional[str]) -> str:
    """The caller's X-Zuno-Max-Tokens when it is a positive integer within the ai-gateway's range, else empty."""
    text = (value or "").strip()
    return text if text.isdigit() and 0 < int(text) <= 1_000_000 else ""


class Refused(Exception):
    """The request is not acceptable; the message is shown to the caller."""


class ApprovalRequested(Exception):
    """A delegated write needs the initiating user's approval: the turn stops at `input-required` here."""

    def __init__(self, operation: str, payload: Dict[str, Any], pending: PendingApproval) -> None:
        super().__init__(operation)
        self.operation, self.payload, self.pending = operation, payload, pending


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
        self._approvals = PendingStore()

    # -- A2A entry points ---------------------------------------------------

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        answer = answer_in(context.message)
        if answer is not None and context.current_task is not None:
            await self._resume(context, updater, answer)
            return
        if context.current_task is None:
            await updater.submit()
        self._approvals.drop(context.task_id)  # a fresh turn on this task supersedes any approval still pending
        await updater.start_work()
        await self._turn(context, updater, None)

    async def _resume(self, context: RequestContext, updater: TaskUpdater, answer: Dict[str, Any]) -> None:
        """The user's answer to a pending approval (ADR-0409): run the write if approved, then go on with the turn."""
        try:
            caller = self._caller(context)
        except Refused as exc:
            await updater.failed(new_agent_text_message(str(exc), context.context_id, context.task_id))
            return
        pending = self._approvals.take(context.task_id, str(answer.get("request_id") or ""), caller.sub)
        if pending is None:
            await updater.failed(new_agent_text_message(
                "No approval is pending for this task (it expired after 300 seconds, was answered, or the gateway "
                "restarted). The operation was not run.", context.context_id, context.task_id,
            ))
            return
        await updater.start_work()
        await self._turn(context, updater, (pending, answer))

    async def _turn(
        self, context: RequestContext, updater: TaskUpdater, resume: Optional[tuple[PendingApproval, Dict[str, Any]]]
    ) -> None:
        try:
            text, classification = await self._answer(context, updater, resume)
        except ApprovalRequested as request:
            self._approvals.put(context.task_id, request.pending)
            logger.info("approval requested agent=%s task_id=%s operation=%s",
                        self._agent.name, context.task_id, request.operation)
            await updater.requires_input(Message(
                role=Role.agent, message_id=uuid.uuid4().hex, task_id=context.task_id, context_id=context.context_id,
                parts=[Part(root=TextPart(text=f"Approval required to run {request.operation}."))],
                metadata={APPROVAL_KEY: request.payload},
            ), final=True)
            return
        except (Refused, ChainError, DownstreamError) as exc:
            await updater.failed(new_agent_text_message(str(exc), context.context_id, context.task_id))
            return
        except Exception:
            logger.exception("agent %s failed", self._agent.name)
            await updater.failed(new_agent_text_message("The agent failed to answer.", context.context_id, context.task_id))
            return
        await updater.add_artifact([Part(root=TextPart(text=text))], name="answer")
        await updater.update_status(
            TaskState.completed, final=True, metadata={CLASSIFICATION_METADATA: classification}
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # A delegating UnifAI run that is interrupted or times out sends tasks/cancel (UnifAI >= 0.1.57). Log it at
        # info level so the gateway side of the cancel is readable here, not only inferred from the caller's logs.
        caller = (context.call_context.state if context.call_context else {}).get("caller")
        logger.info(
            "tasks/cancel agent=%s task_id=%s caller=%s",
            self._agent.name,
            context.task_id,
            getattr(caller, "sub", "unknown"),
        )
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

    # -- one turn -----------------------------------------------------------

    def _caller(self, context: RequestContext) -> CallerIdentity:
        caller = (context.call_context.state if context.call_context else {}).get("caller")
        if not isinstance(caller, CallerIdentity):
            raise Refused("The caller is not authenticated.")
        return caller

    def _task_name(self, context: RequestContext, headers: Optional[Dict[str, str]] = None) -> str:
        # The message names the task; a delegating UnifAI workflow names it in X-Zuno-Task (the operator's
        # A2A node); else the agent's primary task. The chain check below holds the result to what the
        # delegator declares.
        metadata = (context.message.metadata if context.message else None) or {}
        task = str(metadata.get("task") or (headers or {}).get("x-zuno-task") or self._agent.primary_task)
        if task not in self._agent.tasks:
            raise Refused(f"Agent '{self._agent.name}' has no task '{task}'.")
        return task

    async def _answer(
        self, context: RequestContext, updater: TaskUpdater, resume: Optional[tuple[PendingApproval, Dict[str, Any]]]
    ) -> tuple[str, str]:
        caller = self._caller(context)
        if resume is not None:
            # An approval answered: the turn goes on from where it stopped, with the state kept at the request.
            pending, answer = resume
            task, chain_headers, classification, run_id = (
                pending.task, pending.chain_headers, pending.classification, pending.run_id,
            )
            messages, backlog, rounds_left = pending.messages, pending.backlog, pending.rounds_left
            # Re-tested now: a write_allowed entry revoked during the wait is no longer honoured.
            writes = (self._agent.name, task) in self._limits.write_allowed
        else:
            headers = (context.call_context.state.get("headers") or {}) if context.call_context else {}
            request_text = context.get_user_input().strip()
            if not request_text:
                raise Refused("The message is empty.")
            if len(request_text) > self._settings.max_message_chars:
                raise Refused("The message is too long.")

            lowered = {k.lower(): v for k, v in headers.items()}
            task = self._task_name(context, lowered)
            chain = parse_chain(lowered.get("x-zuno-delegated-by"), lowered.get("x-zuno-delegation-depth"))
            reason = verify_chain(chain, self._agent.name, task, caller.groups, self._store, self._limits)
            if reason:
                raise Refused(reason)
            chain_headers = {h: lowered[h.lower()] for h in CHAIN_HEADERS if lowered.get(h.lower())}
            # The caller's reply cap crosses the hop (the ai-gateway keeps the smallest of it and its own default).
            max_tokens = _max_tokens(lowered.get("x-zuno-max-tokens"))
            if max_tokens:
                chain_headers["X-Zuno-Max-Tokens"] = max_tokens
            classification = raise_classification(
                self._agent.classification or "C1", lowered.get("x-zuno-data-classification", "")
            )
            run_id = _run_id(lowered.get("x-zuno-run-id")) or context.task_id or ""
            messages = [
                {"role": "system", "content": self._agent.system_prompt(task)},
                {"role": "user", "content": request_text},
            ]
            backlog, rounds_left = [], self._settings.max_tool_rounds + 1
            # A write tool is offered only on a delegated call to a target listed in delegation.write_allowed, and
            # each call of it waits for the initiating user's approval (ADR-0409).
            writes = bool(chain) and (self._agent.name, task) in self._limits.write_allowed
        common = dict(
            token=caller.token, agent=self._agent.name, task=task,
            classification=classification, run_id=run_id, chain_headers=chain_headers,
        )
        tools, read_only = await self._available_tools(common, writes)
        offered = {t["function"]["name"] for t in tools or []}

        if resume is not None:
            call = backlog.pop(0)
            function = call.get("function") or {}
            name = str(function.get("name") or "")
            decision = str(answer.get("decision") or "reject")
            if decision not in DECISIONS:
                note = f"The decision '{decision}' is not supported."
            else:
                note = str(answer.get("feedback") or "")[:300]
            logger.info("approval answered agent=%s task_id=%s operation=%s decision=%s",
                        self._agent.name, context.task_id, name, decision)
            if decision == "approve" and name in offered:
                result = await self._tools.call_tool(name, parse_arguments(function.get("arguments")), **common)
            else:
                # The caller's own model decides whether to ask again: say plainly that the user declined, so that it
                # reports the refusal instead of delegating the same write once more (seen live: a request every 5 minutes).
                result = (f"The operation {name} was not approved and was not run. The user declined it: do not ask for it "
                          f"again, and tell the caller that it was declined. {note}").strip()
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

        while backlog or rounds_left > 0:  # the calls of the last assistant message are always answered
            if not backlog:
                reply = await self._llm.chat(messages=messages, tools=tools, **common)
                calls = reply.get("tool_calls") or []
                if not calls or not tools:
                    return str(reply.get("content") or "").strip() or "The agent has no answer.", classification
                messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
                backlog = list(calls)
                rounds_left -= 1
            while backlog:
                call = backlog[0]
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                if name not in offered:  # never run a tool that was not offered (listed for this task)
                    result = f"The tool {name} is not available."
                elif name in read_only:
                    result = await self._tools.call_tool(name, parse_arguments(function.get("arguments")), **common)
                else:
                    request_id = uuid.uuid4().hex
                    arguments = parse_arguments(function.get("arguments"))
                    assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})
                    payload = {
                        "request_id": request_id, "operation": name, "args": redact_arguments(arguments),
                        "reasoning": str(assistant.get("content") or "")[:500],
                    }
                    raise ApprovalRequested(name, payload, PendingApproval(
                        request_id=request_id, caller_sub=caller.sub, task=task, classification=classification,
                        run_id=run_id, chain_headers=chain_headers, messages=messages, backlog=backlog,
                        rounds_left=rounds_left,
                    ))
                backlog.pop(0)
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
        # Out of rounds: ask once more without tools so the user gets a final answer.
        reply = await self._llm.chat(messages=messages, tools=None, **common)
        return str(reply.get("content") or "").strip() or "The agent has no answer.", classification

    async def _available_tools(self, common: Dict[str, Any], writes: bool = False):
        """The tools offered for this turn and the names of the read-only ones among them."""
        if not self._settings.tools_enabled or not self._agent.tasks.get(common["task"]):
            return None, set()
        try:
            listed = await self._tools.list_tools(**common)
        except DownstreamError as exc:
            logger.info("no tools for %s/%s: %s", self._agent.name, common["task"], exc)
            return None, set()
        except Exception:
            logger.warning("tool listing failed for %s", self._agent.name, exc_info=True)
            return None, set()
        # Only tools that declare themselves read-only run freely. A write tool is offered solely when the call is
        # a delegation to a target listed in delegation.write_allowed, and then every call of it asks the user.
        read_only = [t for t in listed if (t.get("annotations") or {}).get("readOnlyHint") is True]
        chosen = listed if writes else read_only
        return to_openai_tools(chosen) or None, {t["name"] for t in read_only}
