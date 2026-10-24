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
    Message, MessageSendParams, Part, Role, SendMessageRequest, SendStreamingMessageRequest, TaskState, TextPart,
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
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name) / "agents"
        _agent(root, "alpha", ["agent_alpha"], delegates="beta")
        _agent(root, "beta", ["agent_beta"])
        _agent(root, "idle", ["agent_alpha"], status="placeholder")
        limits = pathlib.Path(self._tmp.name) / "limits.yaml"
        limits.write_text("max_delegation_depth: 2\n")
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

    async def test_tools_go_through_the_mcp_gateway_with_the_same_identity(self) -> None:
        self.down.tools = [{"name": "search_confluence", "description": "d", "inputSchema": {"type": "object"}}]
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

    async def test_tool_rounds_are_bounded(self) -> None:
        self.down.tools = [{"name": "search_confluence", "inputSchema": {"type": "object"}}]
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


if __name__ == "__main__":
    unittest.main()
