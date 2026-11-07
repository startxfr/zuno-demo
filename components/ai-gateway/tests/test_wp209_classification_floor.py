"""ADR-0565 clause 5 (WP-209): the ai-gateway routes and counts a call at
max(header, floor(agent, task)), the floors generated from the admitted agents
release; an absent header takes the configured default (C1 shipped, C3 ready).

Run from this directory:

    python3 tests/test_wp209_classification_floor.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from app import classification_floor, telemetry  # noqa: E402
from app import main as app_main  # noqa: E402
from app.auth import CallerIdentity, validate_token  # noqa: E402
from app.model_routing_policy import ModelRoutingPolicy  # noqa: E402
from app.routing import RoutingTable  # noqa: E402

_FLOORS = {"agents": {
    "cognos": {"floor": "C3", "tasks": {"coming-soon": "C3"}},
    "comage": {"floor": "C2", "tasks": {"check-deal-status": "C2"}},
    "tekos": {"floor": "C1", "tasks": {"answer-technical-question": "C1"}},
}}
_USAGE = {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}
_PROVIDERS = {"providers": [
    {"name": "openai", "kind": "saas", "model": "gpt-4o-mini", "eligible_for": ["C1", "C2"]},
    {"name": "local", "kind": "local", "model": "qwen", "eligible_for": ["C1", "C2", "C3"]},
]}


def _floors(doc=None) -> classification_floor.ClassificationFloors:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(_FLOORS if doc is None else doc, fh)
    try:
        return classification_floor.ClassificationFloors(fh.name)
    finally:
        os.unlink(fh.name)


# --- the floor module ---------------------------------------------------------

def test_a_header_lower_than_the_floor_is_raised_to_the_floor() -> None:
    d = _floors().effective("C1", "cognos", "coming-soon")
    assert (d.declared, d.floor, d.effective, d.raised) == ("C1", "C3", "C3", True)


def test_a_header_above_the_floor_is_kept() -> None:
    d = _floors().effective("C3", "tekos", "answer-technical-question")
    assert (d.effective, d.raised) == ("C3", False)


def test_a_known_agent_with_an_unknown_or_missing_task_gets_the_agent_floor() -> None:
    f = _floors()
    assert f.effective("C1", "comage", "not-a-task").effective == "C2"
    assert f.effective("C1", "comage", "").effective == "C2"


def test_an_unknown_agent_or_no_agent_has_no_floor() -> None:
    f = _floors()
    for agent in ("open-webui", "", "someone-else"):
        d = f.effective("C1", agent, "chat")
        assert (d.floor, d.effective, d.raised) == (None, "C1", False)


def test_an_unknown_header_is_left_for_routing_to_refuse() -> None:
    assert _floors().effective("C9", "cognos", "coming-soon").effective == "C9"


def test_no_file_means_no_floor() -> None:
    f = classification_floor.ClassificationFloors("")
    assert f.effective("C1", "cognos", "coming-soon").effective == "C1"
    missing = classification_floor.ClassificationFloors("/nonexistent/floors.yaml")
    assert missing.floor_for("cognos", "coming-soon") is None


def test_an_unknown_level_in_the_file_is_ignored_not_a_crash() -> None:
    f = _floors({"agents": {"x": {"floor": "C7", "tasks": {"t": "nope", "u": "c2"}}, "y": "not-a-map"}})
    assert f.floor_for("x", "t") is None
    assert f.floor_for("x", "u") == "C2"
    assert f.floor_for("y", "t") is None


def test_a_broken_reload_keeps_the_floors_already_loaded() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(_FLOORS, fh)
    try:
        f = classification_floor.ClassificationFloors(fh.name)
        with open(fh.name, "w", encoding="utf-8") as out:
            out.write("agents: [unclosed")
        f.reload()
        assert f.floor_for("cognos", "coming-soon") == "C3"
    finally:
        os.unlink(fh.name)


def test_a_client_floor_applies_only_when_no_known_agent_is_named() -> None:
    f = _floors()
    with mock.patch.dict(os.environ, {"CLASSIFICATION_CLIENT_FLOORS": "unifai=c2, bad=C9,=C3"}):
        assert classification_floor.client_floors() == {"unifai": "C2"}
        assert f.effective("C1", "", "", "unifai").effective == "C2"
        assert f.effective("C1", "hand-built", "x", "unifai").effective == "C2"
        # a known agent keeps its own floor, even a lower one (closed by WP-225 lot C)
        assert f.effective("C1", "tekos", "answer-technical-question", "unifai").effective == "C1"
        assert f.effective("C1", "cognos", "coming-soon", "unifai").effective == "C3"
        assert f.effective("C1", "", "", "open-webui").effective == "C1"
    assert f.effective("C1", "", "", "unifai").effective == "C1"


def test_agent_and_task_match_case_insensitively() -> None:
    f = _floors()
    assert f.effective("C1", "Cognos", "Coming-Soon").effective == "C3"
    assert f.effective("C1", " COMAGE ", "").effective == "C2"


def test_a_file_that_is_not_a_mapping_does_not_crash_and_keeps_the_floors() -> None:
    for bad in (["cognos"], "just a string", 42):
        assert classification_floor.ClassificationFloors(_write_raw(bad)).agents == {}
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(_FLOORS, fh)
    try:
        f = classification_floor.ClassificationFloors(fh.name)
        with open(fh.name, "w", encoding="utf-8") as out:
            yaml.safe_dump(["not", "a", "mapping"], out)
        f.reload()
        assert f.floor_for("cognos", "coming-soon") == "C3"
    finally:
        os.unlink(fh.name)


def _write_raw(doc) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(doc, fh)
    return fh.name


def test_admin_reload_routing_also_reloads_the_floors() -> None:
    with mock.patch.object(classification_floor.floors, "reload") as reload_floors:
        asyncio.run(app_main.reload_routing())
    reload_floors.assert_called_once()


def test_the_default_when_absent_is_c1_and_c3_is_supported() -> None:
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CLASSIFICATION_DEFAULT_WHEN_ABSENT", None)
        assert classification_floor.declared_level(None) == "C1"
        assert classification_floor.declared_level("  ") == "C1"
        assert classification_floor.declared_level("c2") == "C2"
    with mock.patch.dict(os.environ, {"CLASSIFICATION_DEFAULT_WHEN_ABSENT": "C3"}):
        assert classification_floor.declared_level("") == "C3"
        assert classification_floor.declared_level("C1") == "C1", "a header that is sent is never replaced"
    with mock.patch.dict(os.environ, {"CLASSIFICATION_DEFAULT_WHEN_ABSENT": "C9"}):
        assert classification_floor.declared_level("") == "C1"


# --- through the gateway ------------------------------------------------------

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
        return AIMessage(content=f"from {self.name}", usage_metadata=_USAGE)


def _chat(headers, env=None, policy=None):
    """(response, served providers, routing decisions, model_call spans) of one non-streamed call."""
    served, decisions = [], []
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    async def _decision(_request_id, decision):
        decisions.append(decision)

    patches = [
        mock.patch.dict(os.environ, {"MARKER_FAIL_CLOSED_CLIENTS": "open-webui,openclaw-*", **(env or {})}),
        mock.patch.object(app_main, "routing_table", _Table(_PROVIDERS)),
        mock.patch.object(app_main, "model_routing_policy", _policy(policy or {"adapters": [], "preferences": []})),
        mock.patch.object(app_main.classification_floor, "floors", _floors()),
        mock.patch.object(app_main, "chat_model_for", side_effect=lambda c, *a, **k: _Model(c.name, served)),
        mock.patch.object(app_main.routing_decisions, "set_routing_decision", _decision),
        mock.patch.object(telemetry, "_tracer", provider.get_tracer("test")),
    ]
    for p in patches:
        p.start()
    app_main.app.dependency_overrides[validate_token] = lambda: CallerIdentity(
        sub="u-1", groups=["consultant"], raw_claims={"azp": "unifai"}, token="t")
    try:
        body = {"model": "auto", "stream": False, "messages": [{"role": "user", "content": "hello"}]}
        resp = TestClient(app_main.app).post("/v1/chat/completions", json=body, headers=headers)
    finally:
        app_main.app.dependency_overrides.pop(validate_token, None)
        for p in reversed(patches):
            p.stop()
    spans = [s for s in exporter.get_finished_spans() if s.name == "model_call"]
    return resp, served, decisions, spans


def test_a_c1_header_from_a_c3_agent_is_routed_and_counted_at_c3() -> None:
    with mock.patch.object(app_main.logger, "info") as info:
        resp, served, decisions, spans = _chat(
            {"X-Zuno-Data-Classification": "C1", "X-Zuno-Agent": "cognos", "X-Zuno-Task": "coming-soon"})
    logged = [c.args[0] % c.args[1:] for c in info.call_args_list if c.args]
    assert resp.status_code == 200, resp.text
    assert served == ["local"], "C3 never reaches the SaaS provider listed first"
    assert decisions[-1]["classification"] == "C3"
    assert [s.attributes.get("zuno.classification") for s in spans] == ["C3"]
    assert any("classification raised by floor: C1 -> C3 agent=cognos task=coming-soon" in m
               for m in logged)


def test_the_floor_feeds_local_only_for_at_the_raised_level() -> None:
    """comage is C2 by floor; a C2-only local_only_for entry must fire on a C1 header."""
    policy = {"adapters": [], "preferences": [
        {"agent": "comage", "task": "check-deal-status", "prefer": ["openai", "local"], "local_only_for": ["C2"]}]}
    resp, served, decisions, _ = _chat(
        {"X-Zuno-Data-Classification": "C1", "X-Zuno-Agent": "comage", "X-Zuno-Task": "check-deal-status"},
        policy=policy)
    assert resp.status_code == 200, resp.text
    assert served == ["local"]
    assert decisions[-1]["classification"] == "C2"


def test_a_header_at_or_above_the_floor_is_unchanged() -> None:
    resp, served, decisions, _ = _chat(
        {"X-Zuno-Data-Classification": "C2", "X-Zuno-Agent": "tekos", "X-Zuno-Task": "answer-technical-question"})
    assert resp.status_code == 200, resp.text
    assert served == ["openai"]
    assert decisions[-1]["classification"] == "C2"


def test_no_header_keeps_c1_by_default() -> None:
    resp, served, decisions, _ = _chat({})
    assert resp.status_code == 200, resp.text
    assert served == ["openai"]
    assert decisions[-1]["classification"] == "C1"


def test_no_header_is_local_only_when_the_default_is_c3() -> None:
    resp, served, decisions, _ = _chat({}, env={"CLASSIFICATION_DEFAULT_WHEN_ABSENT": "C3"})
    assert resp.status_code == 200, resp.text
    assert served == ["local"]
    assert decisions[-1]["classification"] == "C3"


def test_an_explicit_header_wins_over_a_c3_default() -> None:
    resp, served, _, _ = _chat({"X-Zuno-Data-Classification": "C1"}, env={"CLASSIFICATION_DEFAULT_WHEN_ABSENT": "C3"})
    assert resp.status_code == 200, resp.text
    assert served == ["openai"]


def test_an_unknown_header_is_still_refused() -> None:
    resp, served, _, _ = _chat({"X-Zuno-Data-Classification": "C9", "X-Zuno-Agent": "cognos"})
    assert resp.status_code == 422
    assert served == []


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failures else 0)
