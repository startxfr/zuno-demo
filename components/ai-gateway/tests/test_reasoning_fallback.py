"""vLLM --reasoning-parser fallback (app/reasoning.py) and GET /v1/models.

Blank `content` + no tool_calls + reasoning text -> the reasoning is served
as `content` with `zuno_reasoning_fallback: true`; in every other case the
reasoning is never exposed. Streaming: reasoning deltas are held back and
emitted as the content only if the stream ends with no content/tool call.

Run from this directory:

    PYTHONPATH=. .venv/bin/python -m pytest tests -q -p no:cacheprovider
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage, AIMessageChunk  # noqa: E402

from app import main as app_main  # noqa: E402
from app import reasoning, telemetry  # noqa: E402
from app.auth import CallerIdentity, validate_token  # noqa: E402
from app.routing import RoutingTable  # noqa: E402

_IDENTITY = CallerIdentity(sub="alice", groups=["consultant"], raw_claims={}, token="t")
_BODY = {"model": "auto", "messages": [{"role": "user", "content": "hi"}]}
_HDR = {"X-Zuno-Data-Classification": "C1"}
_USAGE = {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}


class _Model:
    def __init__(self, message=None, chunks=()):
        self.message, self.chunks = message, chunks

    def bind_tools(self, _t):
        return self

    async def ainvoke(self, _m):
        return self.message

    async def astream(self, _m):
        for c in self.chunks:
            yield c


class _Env:
    def __init__(self, model):
        self.patches = [
            mock.patch.object(app_main, "chat_model_for", return_value=model),
            mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "m"}),
            mock.patch.object(app_main.routing_decisions, "set_routing_decision", self._noop),
            mock.patch.object(app_main, "record_empty_response"),
        ]

    async def _noop(self, *a, **k):
        pass

    def __enter__(self):
        for p in self.patches:
            started = p.start()
        self.metric = started  # the last patch: record_empty_response
        app_main.app.dependency_overrides[validate_token] = lambda: _IDENTITY
        return self

    def __exit__(self, *exc):
        app_main.app.dependency_overrides.pop(validate_token, None)
        for p in reversed(self.patches):
            p.stop()


def _msg(content, reasoning=None, tool_calls=None):
    kw = {"zuno_reasoning": reasoning} if reasoning else {}
    return AIMessage(content=content, additional_kwargs=kw, tool_calls=tool_calls or [], usage_metadata=_USAGE)


def _post(body=None, stream=False):
    b = dict(body or _BODY, stream=stream)
    return TestClient(app_main.app).post("/v1/chat/completions", json=b, headers=_HDR)


# --- non-streaming --------------------------------------------------------


def test_blank_content_with_reasoning_is_folded_and_flagged() -> None:
    for blank in ("", "  \n", None):
        with _Env(_Model(_msg(blank or "", "the real answer"))) as env:
            body = _post().json()
        msg = body["choices"][0]["message"]
        assert msg["content"] == "the real answer"
        assert body["zuno_reasoning_fallback"] is True
        assert "reasoning" not in json.dumps(body["choices"]).lower()
        env.metric.assert_called_once()
        assert env.metric.call_args.kwargs["recovered"] is True


def test_non_empty_content_untouched_and_reasoning_not_exposed() -> None:
    with _Env(_Model(_msg("final", "secret chain of thought"))) as env:
        resp = _post()
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "final"
    assert body["zuno_reasoning_fallback"] is False
    assert "secret chain of thought" not in resp.text
    env.metric.assert_not_called()


def test_tool_calls_untouched() -> None:
    tc = [{"name": "t", "args": {"a": 1}, "id": "c1"}]
    with _Env(_Model(_msg("", "thinking about the tool", tc))) as env:
        resp = _post()
    msg = resp.json()["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "t"
    assert not msg["content"]
    assert resp.json()["zuno_reasoning_fallback"] is False
    assert "thinking about the tool" not in resp.text
    env.metric.assert_not_called()


def test_blank_without_reasoning_counts_unrecovered() -> None:
    with _Env(_Model(_msg(""))) as env:
        body = _post().json()
    assert body["choices"][0]["message"]["content"] == ""
    assert body["zuno_reasoning_fallback"] is False
    assert env.metric.call_args.kwargs["recovered"] is False


# --- streaming ------------------------------------------------------------


def _sse(resp):
    return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: {")]


def _contents(events):
    return [e["choices"][0]["delta"].get("content") for e in events if e["choices"][0]["delta"].get("content")]


def test_stream_with_only_reasoning_emits_it_as_content() -> None:
    chunks = [AIMessageChunk(content="", additional_kwargs={"zuno_reasoning": r}) for r in ("part one ", "part two")]
    with _Env(_Model(chunks=chunks)) as env:
        events = _sse(_post(stream=True))
    assert _contents(events) == ["part one part two"]
    assert any(e["choices"][0]["delta"].get("zuno_reasoning_fallback") for e in events)
    assert env.metric.call_args.kwargs["recovered"] is True


def test_stream_with_content_never_leaks_reasoning() -> None:
    chunks = [
        AIMessageChunk(content="", additional_kwargs={"zuno_reasoning": "hidden thoughts"}),
        AIMessageChunk(content="visible"),
    ]
    with _Env(_Model(chunks=chunks)) as env:
        resp = _post(stream=True)
    assert _contents(_sse(resp)) == ["visible"]
    assert "hidden thoughts" not in resp.text
    env.metric.assert_not_called()


# --- ChatOpenAI subclass keeps the raw reasoning field --------------------


def test_subclass_keeps_reasoning_and_reasoning_content() -> None:
    from langchain_openai import ChatOpenAI

    llm = reasoning.with_reasoning(ChatOpenAI)(base_url="http://x/v1", api_key="k", model="m")
    for field in ("reasoning", "reasoning_content"):
        raw = {"model": "m", "choices": [{"index": 0, "finish_reason": "stop",
               "message": {"role": "assistant", "content": None, field: "answer in reasoning"}}]}
        gen = llm._create_chat_result(raw).generations[0].message
        assert reasoning.reasoning_of(gen) == "answer in reasoning"
    plain = {"model": "m", "choices": [{"index": 0, "finish_reason": "stop",
             "message": {"role": "assistant", "content": "x"}}]}
    assert reasoning.reasoning_of(llm._create_chat_result(plain).generations[0].message) == ""


def test_with_reasoning_leaves_a_mock_class_alone() -> None:
    sentinel = mock.MagicMock()
    assert reasoning.with_reasoning(sentinel) is sentinel


def test_empty_response_metric_is_noop_without_telemetry() -> None:
    telemetry.record_empty_response("p", "m", recovered=True)


# --- GET /v1/models -------------------------------------------------------

_ROUTING = """
providers:
  - {name: local-a, kind: local, model: model-a, eligible_for: [C1, C2, C3]}
  - {name: local-a-maas, kind: local, model: model-a, eligible_for: [C1, C2, C3]}
  - {name: saas-b, kind: saas, model: model-b, eligible_for: [C1]}
"""


def _models(headers=None, auth=True):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(_ROUTING)
    try:
        table = RoutingTable(fh.name)
    finally:
        os.unlink(fh.name)
    with mock.patch.object(app_main, "routing_table", table):
        if auth:
            app_main.app.dependency_overrides[validate_token] = lambda: _IDENTITY
        try:
            return TestClient(app_main.app).get("/v1/models", headers=headers or {})
        finally:
            app_main.app.dependency_overrides.pop(validate_token, None)


def test_models_requires_auth() -> None:
    assert _models(auth=False).status_code == 401


def test_models_default_c1_lists_auto_and_deduped_models() -> None:
    resp = _models()
    body = resp.json()
    assert resp.status_code == 200 and body["object"] == "list"
    assert [m["id"] for m in body["data"]] == ["auto", "model-a", "model-b"]
    assert all(m["object"] == "model" and "created" in m and "owned_by" in m for m in body["data"])
    assert "max-age" in resp.headers["cache-control"]


def test_models_filtered_by_classification_and_local_only() -> None:
    assert [m["id"] for m in _models({"X-Zuno-Data-Classification": "C3"}).json()["data"]] == ["auto", "model-a"]
    assert [m["id"] for m in _models({"X-Zuno-Local-Only": "true"}).json()["data"]] == ["auto", "model-a"]
    assert _models({"X-Zuno-Data-Classification": "C9"}).status_code == 422
