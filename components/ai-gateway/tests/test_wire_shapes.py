"""ADR-0587 (experience clients): the OpenAI wire shapes OpenClaw sends - and
Open WebUI may - are accepted: `content` as a list of text parts and the
`developer` role. Until 2026-11-02 both were a 422 on every OpenClaw turn.

Run from this directory:

    python3 tests/test_wire_shapes.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import main as app_main  # noqa: E402
from app.schemas import ChatCompletionRequest  # noqa: E402

# The shape of an OpenClaw turn (text redacted), as its provider sends it.
_OPENCLAW_TURN = {
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "developer", "content": [{"type": "text", "text": "You are the assistant."}]},
        {"role": "user", "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": "again"}]},
    ],
}


def test_an_openclaw_turn_validates() -> None:
    req = ChatCompletionRequest.model_validate(_OPENCLAW_TURN)
    assert [m.role for m in req.messages] == ["system", "user"]
    assert req.messages[0].content == "You are the assistant."
    assert req.messages[1].content == "Hello\n\nagain"


def test_it_reaches_langchain_as_plain_messages() -> None:
    req = ChatCompletionRequest.model_validate(_OPENCLAW_TURN)
    converted = app_main._to_langchain_messages(req.messages)
    assert isinstance(converted[0], SystemMessage) and converted[0].content == "You are the assistant."
    assert isinstance(converted[1], HumanMessage) and converted[1].content == "Hello\n\nagain"
    assert app_main._last_user_text(req.messages) == "Hello\n\nagain"


def test_openclaw_gateway_path_conversation_validates() -> None:
    """The shape captured from OpenClaw's Control UI path (zuno-demo-13,
    2026-11-02): parts on the user and assistant turns, a string again on a
    follow-up, no image part."""
    req = ChatCompletionRequest.model_validate({
        "model": "auto", "stream": True, "stream_options": {"include_usage": True},
        "tool_choice": "auto", "max_completion_tokens": 8192,
        "messages": [
            {"role": "system", "content": "You are a personal assistant running inside OpenClaw."},
            {"role": "user", "content": [{"type": "text", "text": "<bootstrap>"}, {"type": "text", "text": "<context>"},
                                         {"type": "text", "text": "what is Kubernetes?"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "A container orchestrator."}]},
            {"role": "user", "content": "and OpenShift?"},
        ],
    })
    assert req.messages[1].content == "<bootstrap>\n\n<context>\n\nwhat is Kubernetes?"
    assert req.messages[2].content == "A container orchestrator."
    assert app_main._last_user_text(req.messages) == "and OpenShift?"


def test_string_content_and_the_four_roles_are_unchanged() -> None:
    req = ChatCompletionRequest.model_validate({"messages": [
        {"role": "system", "content": "s"}, {"role": "user", "content": "u"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
                                                              "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "content": "r", "tool_call_id": "c1"},
    ]})
    assert [m.role for m in req.messages] == ["system", "user", "assistant", "tool"]
    assert req.messages[2].content is None


def test_a_non_text_part_is_refused_by_name() -> None:
    try:
        ChatCompletionRequest.model_validate({"messages": [
            {"role": "user", "content": [{"type": "text", "text": "look"},
                                         {"type": "image_url", "image_url": {"url": "data:..."}}]},
        ]})
    except ValidationError as exc:
        assert "image_url" in str(exc) and "only text parts" in str(exc)
    else:
        raise AssertionError("an image part must be refused")


def test_an_unknown_role_is_still_refused() -> None:
    try:
        ChatCompletionRequest.model_validate({"messages": [{"role": "function", "content": "x"}]})
    except ValidationError:
        return
    raise AssertionError("an unknown role must be refused")


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


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
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
