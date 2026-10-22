"""ADR-0567 (WP-153) coverage for app/guardrails.py and its wiring in
POST /v1/chat/completions: observe never alters a response and survives a
hung or failing detector; block refuses on a prompt or reply detection with a
typed 400 and records the decision; the mode follows the declared
classification; only the last user message and the reply reach the detector.
No network: the detector backends are replaced, the provider is a fake model.

Run from this directory:

    python3 tests/test_guardrails.py
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessageChunk  # noqa: E402

from app import guardrails  # noqa: E402
from app import main as app_main  # noqa: E402
from app.auth import CallerIdentity, validate_token  # noqa: E402

_IDENTITY = CallerIdentity(sub="alice", groups=["consultant"], raw_claims={}, token="secret-bearer")
_HIT = [{"content_index": 0, "detection": "credit-card", "detection_type": "pii", "score": 1.0}]
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class _FakeModel:
    def __init__(self, reply="an answer"):
        self.reply = reply

    async def ainvoke(self, _messages):
        class _R:
            content = self.reply
            usage_metadata = {"input_tokens": 3, "output_tokens": 5}
        return _R()

    async def astream(self, _messages):
        for tok in ("an ", "answer"):
            yield AIMessageChunk(content=tok)


class _Env:
    """Patches the gateway into a known guardrails + provider state."""

    def __init__(self, modes, detector, reply="an answer"):
        self.calls = []

        async def fake_detect(contents):
            self.calls.append(list(contents))
            return await detector(contents)

        self.patches = [
            mock.patch.object(guardrails, "GUARDRAILS_DETECTOR_URL", "http://detector"),
            mock.patch.object(guardrails, "GUARDRAILS_BACKEND", "builtin"),
            mock.patch.object(guardrails, "MODE_BY_CLASSIFICATION", modes),
            mock.patch.object(guardrails, "_detect_builtin", fake_detect),
            mock.patch.object(app_main, "chat_model_for", return_value=_FakeModel(reply)),
            mock.patch.object(app_main.routing_table, "provider_config", return_value={"model": "m"}),
            mock.patch.object(app_main.routing_decisions, "set_routing_decision", self._publish),
        ]
        self.published = []

    async def _publish(self, request_id, decision):
        self.published.append((request_id, decision))

    def __enter__(self):
        for p in self.patches:
            p.start()
        app_main.app.dependency_overrides[validate_token] = lambda: _IDENTITY
        return self

    def __exit__(self, *exc):
        app_main.app.dependency_overrides.pop(validate_token, None)
        for p in reversed(self.patches):
            p.stop()


def _post(*a, **kw):
    return TestClient(app_main.app).post(*a, **kw)


async def _clean(_contents):
    return []


async def _hit(_contents):
    return list(_HIT)


async def _boom(_contents):
    raise RuntimeError("detector down")


def _drain_pending():
    # observe_exchange spawns tasks on TestClient's loop, which is gone by
    # now; the detector fake has already recorded the call by then or never will.
    pass


_BODY = {"model": "x", "messages": [
    {"role": "system", "content": "SYSTEM-SECRET-CONTEXT"},
    {"role": "user", "content": "first question"},
    {"role": "assistant", "content": "first answer"},
    {"role": "user", "content": "my card is 4111111111111111"},
]}
_HDR = {"X-Zuno-Data-Classification": "C2", "X-Zuno-Agent": "tekos"}


def test_mode_defaults_to_observe_and_off_without_a_url() -> None:
    with mock.patch.object(guardrails, "MODE_BY_CLASSIFICATION", {"C3": "block"}), \
         mock.patch.object(guardrails, "GUARDRAILS_DETECTOR_URL", "http://d"), \
         mock.patch.object(guardrails, "GUARDRAILS_BACKEND", "builtin"):
        assert guardrails.mode_for("C1") == "observe"
        assert guardrails.mode_for("c3") == "block"
    with mock.patch.object(guardrails, "GUARDRAILS_DETECTOR_URL", ""), \
         mock.patch.object(guardrails, "GUARDRAILS_BACKEND", "builtin"):
        assert guardrails.mode_for("C3") == "off"


def test_malformed_mode_config_never_becomes_off_or_block() -> None:
    assert guardrails._load_modes("not json") == {}
    assert guardrails._load_modes('{"C1":"BLOCK","C2":"nonsense"}') == {"C1": "block", "C2": "observe"}


def test_block_refuses_a_prompt_detection_without_calling_the_provider() -> None:
    with _Env({"C2": "block"}, _hit) as env:
        with mock.patch.object(app_main, "chat_model_for") as model:
            r = _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["type"] == "guardrails_blocked" and err["stage"] == "prompt"
    assert err["detections"] == ["credit-card"]
    assert "4111" not in r.text  # names, never matched text
    model.assert_not_called()
    assert env.published and env.published[0][1]["blocked_by"] == "guardrails"


def test_block_refuses_a_reply_detection() -> None:
    calls = []

    async def det(contents):
        calls.append(contents)
        return [] if len(calls) == 1 else list(_HIT)  # prompt clean, reply dirty

    with _Env({"C2": "block"}, det) as env:
        r = _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    assert r.status_code == 400 and r.json()["error"]["stage"] == "reply"
    assert env.calls[1] == ["an answer"]


def test_block_lets_a_clean_exchange_through_unchanged() -> None:
    with _Env({"C2": "block"}, _clean) as env:
        r = _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "an answer"


def test_only_the_last_user_message_and_reply_reach_the_detector() -> None:
    with _Env({"C2": "block"}, _clean) as env:
        _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    sent = json.dumps(env.calls)
    assert env.calls[0] == ["my card is 4111111111111111"]
    assert "SYSTEM-SECRET-CONTEXT" not in sent and "secret-bearer" not in sent
    assert "first question" not in sent


def test_observe_never_alters_the_response_even_on_a_detection() -> None:
    with _Env({"C2": "observe"}, _hit) as env:
        r = _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "an answer"


def test_observe_survives_a_failing_detector() -> None:
    with _Env({"C2": "observe"}, _boom):
        r = _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    assert r.status_code == 200


def test_block_fails_open_when_the_detector_is_unavailable() -> None:
    with _Env({"C2": "block"}, _boom):
        r = _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    assert r.status_code == 200


def test_observe_does_not_wait_for_a_hung_detector() -> None:
    async def hang(_contents):
        await asyncio.sleep(3600)

    async def go():
        with _Env({"C2": "observe"}, hang) as _:
            pass
        with mock.patch.object(guardrails, "GUARDRAILS_DETECTOR_URL", "http://d"), \
             mock.patch.object(guardrails, "_detect_builtin", hang):
            guardrails.observe_exchange(message="a", reply="b", agent="x")
            # returns immediately; the task is still pending in the background
            assert guardrails._pending
            for t in list(guardrails._pending):
                t.cancel()
            await asyncio.sleep(0)

    asyncio.run(go())


def test_stream_in_block_mode_checks_the_prompt_and_serves_the_stream() -> None:
    with _Env({"C2": "block"}, _clean) as env:
        r = _post("/v1/chat/completions", json={**_BODY, "stream": True}, headers=_HDR)
    assert r.status_code == 200 and "an " in r.text and "[DONE]" in r.text
    assert env.calls[0] == ["my card is 4111111111111111"]


def test_stream_in_block_mode_refuses_a_dirty_prompt() -> None:
    with _Env({"C2": "block"}, _hit):
        r = _post("/v1/chat/completions", json={**_BODY, "stream": True}, headers=_HDR)
    assert r.status_code == 400


def test_stream_reply_is_observed_with_the_accumulated_text() -> None:
    seen = {}

    def fake_observe(**kw):
        seen.update(kw)

    with _Env({"C2": "observe"}, _clean):
        with mock.patch.object(guardrails, "observe_exchange", fake_observe):
            r = _post("/v1/chat/completions", json={**_BODY, "stream": True}, headers=_HDR)
    assert r.status_code == 200
    assert seen["reply"] == "an answer" and seen["message"] == "my card is 4111111111111111"


def test_off_mode_never_calls_the_detector() -> None:
    with _Env({"C2": "off"}, _hit) as env:
        r = _post("/v1/chat/completions", json=_BODY, headers=_HDR)
    assert r.status_code == 200 and env.calls == []


def test_nemo_detection_names_are_extracted() -> None:
    payload = {"guardrails": {"log": {"activated_rails": [
        {"executed_actions": [{"action_name": "zuno_scan", "return_value": ["credit-card"]}]}]}}}
    assert guardrails._detection_names(payload) == ["credit-card"]
    assert guardrails._detection_names({"unexpected": 1}) == []


def test_builtin_policy_has_a_named_rails_pattern_for_every_regex() -> None:
    """Parity guard (was PolicyParityWithRails in agent-runtime)."""
    rails = (_REPO_ROOT / "gitops/charts/trustyai-config/files/nemo-rails/observe/config.yaml").read_text()
    patterns = re.findall(r'^\s+pattern:\s+"(.*)"$', rails, re.M)
    builtin = guardrails.DETECTOR_PARAMS["regex"]
    for regex in (p for p in builtin if p.startswith("(?i)")):
        assert regex.replace("\\", "\\\\") in patterns, regex


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc!r}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
