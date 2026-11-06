"""The A2A gateway, driven by the same A2A SDK client UnifAI uses (JSON-RPC, agent-card.json).

Synthetic agents (no dependency on the admitted release), a fake token validator, and mock
transports for the two downstream gateways, so the tests assert exactly what each one receives.

Run from the component directory:

    cd components/a2a-gateway && python3 -m pytest tests -q
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
import uuid
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import yaml  # noqa: E402
from a2a.client import A2ACardResolver, A2AClient  # noqa: E402
from a2a.types import (  # noqa: E402
    DataPart, Message, MessageSendParams, Part, Role, SendMessageRequest, SendStreamingMessageRequest, TaskState, TextPart,
)

from app import auth  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

USERS = {
    "tok-consultant": auth.CallerIdentity("u-consultant", ["consultant", "agent_alpha"], {}, "tok-consultant"),
    "tok-sales": auth.CallerIdentity("u-sales", ["sales", "agent_beta"], {}, "tok-sales"),
}


def fake_validator(authorization):
    token = auth.bearer_token(authorization)
    if token not in USERS:
        raise auth.AuthError("Invalid or expired token.")
    return USERS[token]


def _agent(root: pathlib.Path, name: str, groups: List[str], status: str = "active", delegates: str = "") -> None:
    directory = root / name
    (directory / "tasks").mkdir(parents=True)
    (directory / "prompts").mkdir()
    zuno: Dict[str, Any] = {
        "name": name, "status": status, "primary_task": "ask", "tasks": ["ask"],
        "model": {"preferred_classification": "C1"}, "access": {"groups": groups},
    }
    if delegates:
        zuno["delegation"] = {"targets": [{"agent": delegates, "task": "ask"}]}
    frontmatter = {
        "okf_version": "v0.2", "type": "agent", "title": name.capitalize(),
        "description": f"Synthetic agent {name} for tests.", "zuno": zuno,
    }
    (directory / "agent.okf.md").write_text(f"---\n{yaml.safe_dump(frontmatter)}---\n# {name}\n")
    task = {"okf_version": "v0.2", "type": "task", "title": "Ask", "zuno": {"allowed_tools": ["search_confluence"]}}
    (directory / "tasks" / "ask.md").write_text(f"---\n{yaml.safe_dump(task)}---\n# Ask\n")
    (directory / "prompts" / "ask.md").write_text(f"You are {name}, a careful assistant.\n")


class Downstream:
    """Records what the ai-gateway and the mcp-gateway receive, and plays scripted answers."""

    def __init__(self) -> None:
        self.llm_calls: List[Dict[str, Any]] = []
        self.mcp_calls: List[Dict[str, Any]] = []
        self.llm_script: List[Any] = []   # message dicts, or an int status code
        self.tools: List[Dict[str, Any]] = []

    def llm(self, request: httpx.Request) -> httpx.Response:
        self.llm_calls.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        step = self.llm_script.pop(0) if self.llm_script else {"role": "assistant", "content": "default answer"}
        if isinstance(step, int):
            return httpx.Response(step, json={"error": "refused"})
        return httpx.Response(200, json={"choices": [{"message": step}]})

    def mcp(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.mcp_calls.append({"headers": dict(request.headers), "body": body})
        if body["method"] == "tools/list":
            result = {"tools": self.tools}
        else:
            result = {"content": [{"type": "text", "text": "tool result for " + body["params"]["name"]}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


class GatewayTestCase(unittest.IsolatedAsyncioTestCase):
    LIMITS = "max_delegation_depth: 2\n"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name) / "agents"
        _agent(root, "alpha", ["agent_alpha"], delegates="beta")
        _agent(root, "beta", ["agent_beta"])
        _agent(root, "idle", ["agent_alpha"], status="placeholder")
        limits = pathlib.Path(self._tmp.name) / "limits.yaml"
        limits.write_text(self.LIMITS)
        self.down = Downstream()
        self.settings = Settings(
            agents_dir=str(root), limits_policy_path=str(limits), public_base_url="http://a2a.test", tools_enabled=True,
        )
        self.app = create_app(
            self.settings,
            llm_transport=httpx.MockTransport(self.down.llm),
            tools_transport=httpx.MockTransport(self.down.mcp),
            token_validator=fake_validator,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def http(self, token: str = "", **headers: str) -> httpx.AsyncClient:
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://a2a.test", headers=headers)

    @staticmethod
    def request(text: str, **metadata: Any) -> SendMessageRequest:
        message = Message(
            role=Role.user, message_id=uuid.uuid4().hex, parts=[Part(root=TextPart(text=text))], metadata=metadata or None,
        )
        return SendMessageRequest(id=uuid.uuid4().hex, params=MessageSendParams(message=message))

    async def send(self, agent: str, token: str, text: str = "hello", **headers: str):
        async with self.http(token, **headers) as client:
            a2a = A2AClient(client, url=f"http://a2a.test/agents/{agent}/")
            return await a2a.send_message(self.request(text))


class CardTests(GatewayTestCase):
    async def test_card_is_public_minimal_and_resolvable_by_the_sdk(self) -> None:
        async with self.http() as client:
            card = await A2ACardResolver(client, "http://a2a.test/agents/alpha").get_agent_card()
        self.assertEqual(card.name, "Alpha")
        self.assertEqual(card.url, "http://a2a.test/agents/alpha/")
        self.assertTrue(card.capabilities.streaming)
        self.assertEqual([s.id for s in card.skills], ["ask"])
        self.assertNotIn("agent_alpha", card.model_dump_json())  # entitlement groups never leak

    async def test_inactive_or_unknown_agents_have_no_card(self) -> None:
        async with self.http() as client:
            for name in ("idle", "nobody"):
                r = await client.get(f"/agents/{name}/.well-known/agent-card.json")
                self.assertEqual(r.status_code, 404)


class AccessTests(GatewayTestCase):
    async def test_anonymous_and_forged_tokens_are_refused(self) -> None:
        for token in ("", "forged"):
            async with self.http(token) as client:
                r = await client.post("/agents/alpha/", json={"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {}})
            self.assertEqual(r.status_code, 401)
        self.assertEqual(self.down.llm_calls, [])

    async def test_a_user_without_the_entitlement_gets_the_answer_for_an_unknown_agent(self) -> None:
        async with self.http("tok-sales") as client:
            body = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {}}
            denied = await client.post("/agents/alpha/", json=body)
            unknown = await client.post("/agents/nobody/", json=body)
        self.assertEqual(denied.status_code, unknown.status_code, 404)
        self.assertEqual(denied.json(), unknown.json())
        self.assertEqual(self.down.llm_calls, [])

    async def test_a_name_no_agent_can_have_gets_the_same_answer_too(self) -> None:
        async with self.http("tok-sales") as client:
            body = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {}}
            denied = await client.post("/agents/alpha/", json=body)
            odd = await client.post("/agents/9f3c0d/", json=body)
        self.assertEqual(odd.status_code, 404)
        self.assertEqual(odd.json(), denied.json())


class TurnTests(GatewayTestCase):
    async def test_entitled_user_gets_an_answer_computed_with_their_own_token(self) -> None:
        self.down.llm_script = [{"role": "assistant", "content": "the answer"}]
        self.down.tools = []
        response = await self.send("alpha", "tok-consultant", "What is a Route?")
        task = response.root.result
        self.assertEqual(task.status.state, TaskState.completed)
        self.assertEqual(task.artifacts[0].parts[0].root.text, "the answer")
        call = self.down.llm_calls[0]
        self.assertEqual(call["headers"]["authorization"], "Bearer tok-consultant")
        self.assertEqual(call["headers"]["x-zuno-agent"], "alpha")
        self.assertEqual(call["headers"]["x-zuno-task"], "ask")
        self.assertEqual(call["headers"]["x-zuno-data-classification"], "C1")
        self.assertEqual(call["headers"]["x-zuno-run-id"], task.id)
        self.assertEqual(call["body"]["messages"][0]["content"], "You are alpha, a careful assistant.")
        self.assertEqual(call["body"]["messages"][1]["content"], "What is a Route?")

    async def test_classification_can_only_be_raised(self) -> None:
        await self.send("alpha", "tok-consultant", "hi", **{"X-Zuno-Data-Classification": "C3"})
        await self.send("alpha", "tok-consultant", "hi", **{"X-Zuno-Data-Classification": "C1"})
        self.assertEqual([c["headers"]["x-zuno-data-classification"] for c in self.down.llm_calls], ["C3", "C1"])

    async def test_the_task_returns_the_classification_the_turn_ran_at(self) -> None:
        first = await self.send("alpha", "tok-consultant", "hi")
        raised = await self.send("alpha", "tok-consultant", "hi", **{"X-Zuno-Data-Classification": "C3"})
        self.assertEqual(first.root.result.metadata["zuno.classification"], "C1")
        self.assertEqual(raised.root.result.metadata["zuno.classification"], "C3")

    async def test_tools_go_through_the_mcp_gateway_with_the_same_identity(self) -> None:
        self.down.tools = [{"name": "search_confluence", "description": "d", "inputSchema": {"type": "object"},
                            "annotations": {"readOnlyHint": True}}]
        self.down.llm_script = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "search_confluence", "arguments": '{"query": "route"}'}}]},
            {"role": "assistant", "content": "answer with citations"},
        ]
        response = await self.send("alpha", "tok-consultant", "question")
        self.assertEqual(response.root.result.artifacts[0].parts[0].root.text, "answer with citations")
        self.assertEqual([c["body"]["method"] for c in self.down.mcp_calls], ["tools/list", "tools/call"])
        for call in self.down.mcp_calls:
            self.assertEqual(call["headers"]["authorization"], "Bearer tok-consultant")
            self.assertEqual(call["headers"]["x-zuno-agent"], "alpha")
        self.assertEqual(self.down.mcp_calls[1]["body"]["params"]["arguments"], {"query": "route"})
        self.assertIn("tools", self.down.llm_calls[0]["body"])
        self.assertEqual(self.down.llm_calls[1]["body"]["messages"][-1]["role"], "tool")

    async def test_only_read_only_tools_are_offered_and_run(self) -> None:
        self.down.tools = [
            {"name": "search_confluence", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}},
            {"name": "aap.cluster.audit", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": False}},
            {"name": "no_hint_tool", "inputSchema": {"type": "object"}},
        ]
        self.down.llm_script = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "aap.cluster.audit", "arguments": "{}"}}]},
            {"role": "assistant", "content": "done without the write tool"},
        ]
        response = await self.send("alpha", "tok-consultant", "launch an audit")
        offered = [t["function"]["name"] for t in self.down.llm_calls[0]["body"]["tools"]]
        self.assertEqual(offered, ["search_confluence"])
        self.assertEqual([c["body"]["method"] for c in self.down.mcp_calls], ["tools/list"])  # never called
        self.assertEqual(response.root.result.artifacts[0].parts[0].root.text, "done without the write tool")

    async def test_tool_rounds_are_bounded(self) -> None:
        self.down.tools = [{"name": "search_confluence", "inputSchema": {"type": "object"},
                            "annotations": {"readOnlyHint": True}}]
        looping = {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "search_confluence", "arguments": "{}"}}]}
        self.down.llm_script = [looping] * 10
        await self.send("alpha", "tok-consultant", "question")
        # max_tool_rounds + 1 model calls with tools, then one last call without tools
        self.assertEqual(len(self.down.llm_calls), self.settings.max_tool_rounds + 2)
        self.assertNotIn("tools", self.down.llm_calls[-1]["body"])

    async def test_an_exhausted_quota_is_reported_to_the_caller_not_hidden(self) -> None:
        self.down.llm_script = [429]
        task = (await self.send("alpha", "tok-consultant")).root.result
        self.assertEqual(task.status.state, TaskState.failed)
        self.assertIn("budget", task.status.message.parts[0].root.text)

    async def test_an_unknown_task_is_refused(self) -> None:
        async with self.http("tok-consultant") as client:
            a2a = A2AClient(client, url="http://a2a.test/agents/alpha/")
            task = (await a2a.send_message(self.request("hi", task="write-code"))).root.result
        self.assertEqual(task.status.state, TaskState.failed)
        self.assertEqual(self.down.llm_calls, [])

    async def test_streaming_ends_with_a_completed_task(self) -> None:
        self.down.llm_script = [{"role": "assistant", "content": "streamed answer"}]
        states: List[TaskState] = []
        async with self.http("tok-consultant") as client:
            a2a = A2AClient(client, url="http://a2a.test/agents/alpha/")
            request = SendStreamingMessageRequest(id="1", params=self.request("hi").params)
            async for event in a2a.send_message_streaming(request):
                result = event.root.result
                status = getattr(result, "status", None)
                if status is not None:
                    states.append(status.state)
        self.assertEqual(states[-1], TaskState.completed)


class DelegationTests(GatewayTestCase):
    async def test_a_valid_chain_is_checked_and_passed_to_the_downstream_gateways(self) -> None:
        # alpha delegates to beta/ask; the caller holds both entitlements
        USERS["tok-both"] = auth.CallerIdentity("u-both", ["agent_alpha", "agent_beta"], {}, "tok-both")
        self.addCleanup(USERS.pop, "tok-both", None)
        headers = {"X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1"}
        task = (await self.send("beta", "tok-both", "delegated question", **headers)).root.result
        self.assertEqual(task.status.state, TaskState.completed)
        sent = self.down.llm_calls[0]["headers"]
        self.assertEqual(sent["x-zuno-delegated-by"], "alpha:ask")
        self.assertEqual(sent["x-zuno-delegation-depth"], "1")

    async def test_the_headers_the_unifai_operator_emits_are_accepted_and_traced(self) -> None:
        # Exactly what unifai-operator puts on its A2A node (fork delegation.go): run id, delegator, depth 1, target task.
        USERS["tok-both"] = auth.CallerIdentity("u-both", ["agent_alpha", "agent_beta"], {}, "tok-both")
        self.addCleanup(USERS.pop, "tok-both", None)
        headers = {
            "X-Zuno-Run-Id": "5b1c0d6e-session-1", "X-Zuno-Delegated-By": "alpha:ask",
            "X-Zuno-Delegation-Depth": "1", "X-Zuno-Task": "ask",
        }
        task = (await self.send("beta", "tok-both", "delegated question", **headers)).root.result
        self.assertEqual(task.status.state, TaskState.completed)
        sent = self.down.llm_calls[0]["headers"]
        self.assertEqual(sent["x-zuno-run-id"], "5b1c0d6e-session-1")
        self.assertEqual(sent["x-zuno-task"], "ask")
        self.assertEqual(sent["x-zuno-agent"], "beta")

    async def test_the_task_header_is_held_to_what_the_delegator_declares(self) -> None:
        USERS["tok-both"] = auth.CallerIdentity("u-both", ["agent_alpha", "agent_beta"], {}, "tok-both")
        self.addCleanup(USERS.pop, "tok-both", None)
        headers = {"X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1", "X-Zuno-Task": "not-a-task"}
        task = (await self.send("beta", "tok-both", "x", **headers)).root.result
        self.assertEqual(task.status.state, TaskState.failed)
        self.assertEqual(self.down.llm_calls, [])

    async def test_a_run_id_that_is_not_a_plain_token_is_ignored(self) -> None:
        USERS["tok-both"] = auth.CallerIdentity("u-both", ["agent_alpha", "agent_beta"], {}, "tok-both")
        self.addCleanup(USERS.pop, "tok-both", None)
        headers = {"X-Zuno-Run-Id": "bad id with spaces"}
        task = (await self.send("beta", "tok-both", "x", **headers)).root.result
        self.assertEqual(task.status.state, TaskState.completed)
        self.assertNotEqual(self.down.llm_calls[0]["headers"]["x-zuno-run-id"], "bad id with spaces")

    async def test_the_callers_reply_cap_crosses_the_hop_only_when_valid(self) -> None:
        for sent, expected in (("4096", "4096"), ("0", None), ("-5", None), ("many", None), ("99999999", None)):
            self.down.llm_calls.clear()
            task = (await self.send("alpha", "tok-consultant", "q", **{"X-Zuno-Max-Tokens": sent})).root.result
            self.assertEqual(task.status.state, TaskState.completed, sent)
            self.assertEqual(self.down.llm_calls[0]["headers"].get("x-zuno-max-tokens"), expected, sent)

    async def test_a_chain_beyond_the_declared_limit_is_refused(self) -> None:
        USERS["tok-both"] = auth.CallerIdentity("u-both", ["agent_alpha", "agent_beta"], {}, "tok-both")
        self.addCleanup(USERS.pop, "tok-both", None)
        headers = {"X-Zuno-Delegated-By": "alpha:ask,beta:ask", "X-Zuno-Delegation-Depth": "2"}
        task = (await self.send("beta", "tok-both", "x", **headers)).root.result
        self.assertEqual(task.status.state, TaskState.failed)
        self.assertEqual(self.down.llm_calls, [])

    async def test_a_malformed_chain_is_refused(self) -> None:
        task = (await self.send("alpha", "tok-consultant", "x", **{"X-Zuno-Delegated-By": "alpha:ask"})).root.result
        self.assertEqual(task.status.state, TaskState.failed)
        self.assertEqual(self.down.llm_calls, [])


class CancelLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_cancel_is_logged_with_the_agent_the_task_and_the_caller(self) -> None:
        from unittest import mock

        from app.auth import CallerIdentity
        from app.executor import ZunoAgentExecutor

        agent = mock.Mock()
        agent.name = "tekos"
        executor = ZunoAgentExecutor(agent, mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock())
        context = mock.Mock(task_id="task-42", context_id="ctx-1")
        context.call_context.state = {"caller": CallerIdentity(sub="user-7", groups=[], raw_claims={}, token="t")}
        queue = mock.Mock(enqueue_event=mock.AsyncMock())
        with self.assertLogs("a2a_gateway.executor", level="INFO") as logs:
            await executor.cancel(context, queue)
        self.assertEqual(
            logs.output, ["INFO:a2a_gateway.executor:tasks/cancel agent=tekos task_id=task-42 caller=user-7"]
        )
        queue.enqueue_event.assert_awaited()


if __name__ == "__main__":
    unittest.main()


class LoggingTests(unittest.TestCase):
    def test_the_gateway_logger_emits_info_lines_once_configured(self) -> None:
        import io
        import logging

        from app.main import configure_logging

        gateway = logging.getLogger("a2a_gateway")
        saved = (list(gateway.handlers), gateway.level, gateway.propagate)
        gateway.handlers.clear()
        try:
            configure_logging()
            configure_logging()  # idempotent: no second handler, no duplicated line
            self.assertEqual(len(gateway.handlers), 1)
            stream = io.StringIO()
            gateway.handlers[0].setStream(stream)
            logging.getLogger("a2a_gateway.executor").info("tasks/cancel agent=%s", "tekos")
            self.assertEqual(stream.getvalue().count("tasks/cancel agent=tekos"), 1)
        finally:
            gateway.handlers[:] = saved[0]
            gateway.setLevel(saved[1])
            gateway.propagate = saved[2]


class ApprovalTests(GatewayTestCase):
    """A delegated write waits for the initiating user's approval (ADR-0409, WP-173 step 5)."""

    LIMITS = "max_delegation_depth: 2\ndelegation:\n  write_allowed:\n    - {agent: beta, task: ask}\n"
    CHAIN = {"X-Zuno-Delegated-By": "alpha:ask", "X-Zuno-Delegation-Depth": "1"}
    WRITE_CALL = {"role": "assistant", "content": "I will write the draft.", "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": "search_confluence", "arguments": '{"page": "draft", "api_key": "sekret"}'}}]}

    def setUp(self) -> None:
        super().setUp()
        USERS["tok-both"] = auth.CallerIdentity("u-both", ["agent_alpha", "agent_beta"], {}, "tok-both")
        self.addCleanup(USERS.pop, "tok-both", None)
        self.down.tools = [{"name": "search_confluence", "description": "d", "inputSchema": {"type": "object"},
                            "annotations": {"readOnlyHint": False}}]

    async def answer(self, task, decision: str, request_id: str = ""):
        approval = task.status.message.metadata["zuno.approval"]
        message = Message(
            role=Role.user, message_id=uuid.uuid4().hex, task_id=task.id, context_id=task.context_id,
            parts=[Part(root=DataPart(data={"zuno.approval": {
                "request_id": request_id or approval["request_id"], "decision": decision, "feedback": "because"}}))],
        )
        async with self.http("tok-both", **self.CHAIN) as client:
            a2a = A2AClient(client, url="http://a2a.test/agents/beta/")
            return (await a2a.send_message(SendMessageRequest(id="2", params=MessageSendParams(message=message)))).root.result

    async def start(self):
        self.down.llm_script = [self.WRITE_CALL, {"role": "assistant", "content": "done"}]
        return (await self.send("beta", "tok-both", "write it", **self.CHAIN)).root.result

    def tool_calls(self):
        return [c for c in self.down.mcp_calls if c["body"]["method"] == "tools/call"]

    async def test_a_delegated_write_raises_an_approval_with_a_redacted_summary(self) -> None:
        task = await self.start()
        self.assertEqual(task.status.state, TaskState.input_required)
        approval = task.status.message.metadata["zuno.approval"]
        self.assertEqual(approval["operation"], "search_confluence")
        self.assertEqual(approval["args"], {"page": "draft", "api_key": "***"})
        self.assertEqual(approval["reasoning"], "I will write the draft.")
        self.assertTrue(approval["request_id"])
        self.assertEqual(self.tool_calls(), [])

    async def test_an_approval_lets_the_write_run_and_the_task_complete(self) -> None:
        task = await self.start()
        done = await self.answer(task, "approve")
        self.assertEqual(done.status.state, TaskState.completed)
        self.assertEqual(len(self.tool_calls()), 1)
        self.assertEqual(done.metadata["zuno.classification"], "C1")

    async def test_a_rejection_keeps_the_write_from_running(self) -> None:
        task = await self.start()
        done = await self.answer(task, "reject")
        self.assertEqual(done.status.state, TaskState.completed)
        self.assertEqual(self.tool_calls(), [])
        tool_message = self.down.llm_calls[1]["body"]["messages"][-1]
        self.assertIn("was not approved", tool_message["content"])
        self.assertIn("do not ask for it again", tool_message["content"])

    async def test_an_unsupported_decision_counts_as_a_refusal(self) -> None:
        task = await self.start()
        await self.answer(task, "modify")
        self.assertEqual(self.tool_calls(), [])

    async def test_silence_is_a_refusal(self) -> None:
        from app import approvals
        task = await self.start()
        import time as _time  # the 300 s bound is checked against the monotonic clock: move it forward
        real = _time.monotonic
        self.addCleanup(setattr, _time, "monotonic", real)
        _time.monotonic = lambda: real() + approvals.APPROVAL_TIMEOUT_SECONDS + 1
        late = await self.answer(task, "approve")
        self.assertEqual(late.status.state, TaskState.failed)
        self.assertEqual(self.tool_calls(), [])

    async def test_an_answer_with_the_wrong_request_id_is_refused(self) -> None:
        task = await self.start()
        refused = await self.answer(task, "approve", request_id="not-the-request")
        self.assertEqual(refused.status.state, TaskState.failed)
        self.assertEqual(self.tool_calls(), [])

    async def test_a_write_target_not_on_the_list_gets_no_write_tool(self) -> None:
        self.down.llm_script = [{"role": "assistant", "content": "no tools"}]
        task = (await self.send("alpha", "tok-both", "x")).root.result  # direct call: not delegated
        self.assertEqual(task.status.state, TaskState.completed)
        self.assertNotIn("tools", self.down.llm_calls[0]["body"])

    async def test_the_rest_of_the_calls_run_after_an_approval_even_in_the_last_round(self) -> None:
        object.__setattr__(self.settings, "max_tool_rounds", 0)  # one round only (the settings are frozen)
        self.down.tools.append({"name": "read_page", "description": "d", "inputSchema": {"type": "object"},
                                "annotations": {"readOnlyHint": True}})
        two_calls = dict(self.WRITE_CALL, tool_calls=self.WRITE_CALL["tool_calls"] + [
            {"id": "c2", "type": "function", "function": {"name": "read_page", "arguments": "{}"}}])
        self.down.llm_script = [two_calls, {"role": "assistant", "content": "done"}]
        task = (await self.send("beta", "tok-both", "write it", **self.CHAIN)).root.result
        done = await self.answer(task, "approve")
        self.assertEqual(done.status.state, TaskState.completed)
        sent = self.down.llm_calls[-1]["body"]["messages"]
        ids = [m["tool_call_id"] for m in sent if m["role"] == "tool"]
        self.assertEqual(ids, ["c1", "c2"])

    async def test_the_summary_masks_nested_secrets_and_says_what_it_cuts(self) -> None:
        from app.approvals import redact_arguments
        summary = redact_arguments({"auth": {"password": "p"}, "text": "x" * 500, **{f"k{i}": i for i in range(25)}})
        self.assertEqual(summary["auth"], {"password": "***"})
        self.assertIn("more characters not shown", summary["text"])
        self.assertIn("more keys not shown", summary["_truncated"])

    async def test_another_caller_cannot_consume_the_approval(self) -> None:
        USERS["tok-other"] = auth.CallerIdentity("u-other", ["agent_alpha", "agent_beta"], {}, "tok-other")
        self.addCleanup(USERS.pop, "tok-other", None)
        task = await self.start()
        approval = task.status.message.metadata["zuno.approval"]
        message = Message(
            role=Role.user, message_id=uuid.uuid4().hex, task_id=task.id, context_id=task.context_id,
            parts=[Part(root=DataPart(data={"zuno.approval": {"request_id": approval["request_id"], "decision": "approve"}}))],
        )
        async with self.http("tok-other", **self.CHAIN) as client:
            a2a = A2AClient(client, url="http://a2a.test/agents/beta/")
            refused = (await a2a.send_message(SendMessageRequest(id="3", params=MessageSendParams(message=message)))).root.result
        self.assertEqual(refused.status.state, TaskState.failed)
        self.assertEqual(self.tool_calls(), [])
