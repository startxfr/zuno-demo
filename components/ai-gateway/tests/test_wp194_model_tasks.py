"""ADR-0596 (WP-194): an experience client's declared model selects one of its
tasks; the routing policy entry of that task, never the name, picks the
provider, and ADR-0594 still keeps a tool turn local.

Run from this directory:

    python3 -m pytest tests/test_wp194_model_tasks.py -q -p no:cacheprovider
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app import main as app_main  # noqa: E402
from app import model_tasks  # noqa: E402
from app.auth import CallerIdentity, validate_token  # noqa: E402
from app.model_routing_policy import ModelRoutingPolicy  # noqa: E402
from app.routing import RoutingTable  # noqa: E402

_USAGE = {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}
_PROVIDERS = {"providers": [
    {"name": "local-maas", "kind": "local", "model": "qwen", "eligible_for": ["C1", "C2", "C3"]},
    {"name": "local", "kind": "local", "model": "qwen", "eligible_for": ["C1", "C2", "C3"]},
    {"name": "mistral-codestral", "kind": "saas", "model": "codestral-latest", "eligible_for": ["C1", "C2"]},
]}
_POLICY = {"adapters": [], "preferences": [
    {"agent": "open-webui", "task": "code", "prefer": ["mistral-codestral"]},
    {"agent": "openclaw", "task": "code", "prefer": ["mistral-codestral"]},
]}


class _Table(RoutingTable):
    def __init__(self, config):
        self._routing_path = "<stub>"
        self._config = config


def _policy(doc):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(doc, fh)
    try:
        return ModelRoutingPolicy(fh.name)
    finally:
        os.unlink(fh.name)


class _Model:
    def __init__(self, name, served):
        self.name, self.served = name, served

    def bind_tools(self, _t):
        return self

    async def ainvoke(self, _m):
        self.served.append(self.name)
        if self.name == "mistral-codestral" and os.environ.get("_CODESTRAL_DOWN"):
            raise RuntimeError("401 invalid api key")
        return AIMessage(content=f"from {self.name}", usage_metadata=_USAGE)


def _identity(azp):
    return CallerIdentity(sub="u-1", groups=["consultant"], raw_claims={"azp": azp}, token="t")


def _chat(azp, model, agent, task="chat", messages=None, codestral_down=False):
    """Served providers, in order, for one non-streamed call."""
    served = []
    body = {"model": model, "stream": False,
            "messages": messages or [{"role": "user", "content": "write python that checks an email"}]}
    headers = {"X-Zuno-Data-Classification": "C1", "X-Zuno-Agent": agent, "X-Zuno-Task": task}
    env = {"MARKER_FAIL_CLOSED_CLIENTS": "open-webui,openclaw-*"}
    if codestral_down:
        env["_CODESTRAL_DOWN"] = "1"

    async def _noop(*_a, **_k):
        return None

    patches = [
        mock.patch.dict(os.environ, env),
        mock.patch.object(app_main, "routing_table", _Table(_PROVIDERS)),
        mock.patch.object(app_main, "model_routing_policy", _policy(_POLICY)),
        mock.patch.object(app_main, "chat_model_for", side_effect=lambda c, *a, **k: _Model(c.name, served)),
        mock.patch.object(app_main.routing_decisions, "set_routing_decision", _noop),
    ]
    for p in patches:
        p.start()
    app_main.app.dependency_overrides[validate_token] = lambda: _identity(azp)
    try:
        resp = TestClient(app_main.app).post("/v1/chat/completions", json=body, headers=headers)
    finally:
        app_main.app.dependency_overrides.pop(validate_token, None)
        for p in reversed(patches):
            p.stop()
    return resp, served


def test_aliases_default_and_parsing() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MODEL_TASK_ALIASES", None)
        assert model_tasks.aliases() == {"zuno-code": ("code", "Zuno Code")}
    with mock.patch.dict(os.environ, {"MODEL_TASK_ALIASES": "a=t1, b=t2:Bee, broken, =x, auto=chat, c="}):
        assert model_tasks.aliases() == {"a": ("t1", "a"), "b": ("t2", "Bee")}
    with mock.patch.dict(os.environ, {"MODEL_TASK_ALIASES": ""}):
        assert model_tasks.aliases() == {} and model_tasks.listed_models() == []


def test_task_for_only_maps_experience_clients_and_declared_models() -> None:
    with mock.patch.dict(os.environ, {"MARKER_FAIL_CLOSED_CLIENTS": "open-webui,openclaw-*"}):
        assert model_tasks.task_for("open-webui", "zuno-code", "chat") == "code"
        assert model_tasks.task_for("openclaw-consultant-02", "zuno-code", "") == "code"
        assert model_tasks.task_for("open-webui", "auto", "chat") == "chat"
        assert model_tasks.task_for("open-webui", "codestral-latest", "chat") == "chat"
        assert model_tasks.task_for("unifai", "zuno-code", "write-code") == "write-code"
        assert model_tasks.task_for("", "zuno-code", "") == ""


def test_zuno_code_without_tools_is_served_by_codestral() -> None:
    resp, served = _chat("open-webui", "zuno-code", "open-webui")
    assert resp.status_code == 200, resp.text
    assert served == ["mistral-codestral"]


def test_auto_keeps_the_local_first_order() -> None:
    resp, served = _chat("open-webui", "auto", "open-webui")
    assert resp.status_code == 200, resp.text
    assert served == ["local-maas"]


def test_codestral_failing_falls_back_to_the_local_model_in_the_same_turn() -> None:
    resp, served = _chat("openclaw-consultant-02", "zuno-code", "openclaw", task="", codestral_down=True)
    assert resp.status_code == 200, resp.text
    assert served == ["mistral-codestral", "local-maas"]
    assert "from local-maas" in resp.text


def test_an_unmarked_tool_result_keeps_zuno_code_local() -> None:
    """ADR-0594 is unchanged: an experience client's unmarked tool result is C2 and local-only."""
    messages = [
        {"role": "user", "content": "run it"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "exec", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "Traceback: no module named dns"},
    ]
    resp, served = _chat("openclaw-consultant-02", "zuno-code", "openclaw", task="", messages=messages)
    assert resp.status_code == 200, resp.text
    assert served == ["local-maas"]


def test_another_client_sending_zuno_code_keeps_its_header_task() -> None:
    resp, served = _chat("unifai", "zuno-code", "open-webui", task="chat")
    assert resp.status_code == 200, resp.text
    assert served == ["local-maas"]


def test_the_task_reaches_the_model_call_span_and_not_the_counters() -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from app import telemetry

    class _Rec:
        def __init__(self):
            self.points = []

        def add(self, _v, attrs):
            self.points.append(dict(attrs))

        record = add

    exporter, calls = InMemorySpanExporter(), _Rec()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    token = telemetry._caller_task.set("")
    try:
        with mock.patch.object(telemetry, "_tracer", provider.get_tracer("test")), \
             mock.patch.object(telemetry, "_model_call_counter", calls):
            telemetry.set_caller_task("code")
            with telemetry.model_call_span("mistral-codestral", "codestral-latest", "C1", agent="open-webui"):
                pass
    finally:
        telemetry._caller_task.reset(token)
    (span,) = exporter.get_finished_spans()
    assert span.attributes.get("zuno.task") == "code"
    assert "task" not in calls.points[0]
