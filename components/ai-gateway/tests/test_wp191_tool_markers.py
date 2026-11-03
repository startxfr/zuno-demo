"""ADR-0594 (WP-191): the ai-gateway raises a model call from the signed
classification markers the mcp-gateway puts on tool results, and keeps an
experience client's turn on local models when it carries C2+ or unmarked
tool content.

Run from this directory:

    python3 tests/test_wp191_tool_markers.py
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import tool_markers  # noqa: E402
from app.schemas import ChatMessage  # noqa: E402

KEY = "test-marker-key"
_ENV = {"ZUNO_MARKER_KEY": KEY, "MARKER_FAIL_CLOSED_CLIENTS": "open-webui,openclaw-*"}


def _marked(text, level, external=True, key=KEY):
    digest = hashlib.sha256(text.strip().encode()).hexdigest()
    flag = "1" if external else "0"
    sig = hmac.new(key.encode(), f"{level}|{flag}|{digest}".encode(), hashlib.sha256).hexdigest()
    return f"{text}\n\n[zuno-classification level={level} external={flag} sig={sig}]"


def _msgs(*pairs):
    return [ChatMessage(role=r, content=c, tool_call_id="t1" if r == "tool" else None) for r, c in pairs]


def _assess(messages, client, classification="C1", local_only=False):
    with mock.patch.dict(os.environ, _ENV):
        return tool_markers.assess(messages, classification, local_only, client)


def test_a_c1_marker_changes_nothing() -> None:
    a = _assess(_msgs(("user", "my files?"), ("tool", _marked('{"files": []}', "C1"))), "open-webui")
    assert (a.classification, a.local_only) == ("C1", False)


def test_a_c2_marker_raises_and_keeps_an_experience_client_local() -> None:
    a = _assess(_msgs(("tool", _marked("confluence page", "C2"))), "open-webui")
    assert (a.classification, a.local_only) == ("C2", True)


def test_a_c2_marker_raises_unifai_without_forcing_local() -> None:
    a = _assess(_msgs(("tool", _marked("confluence page", "C2"))), "unifai")
    assert (a.classification, a.local_only) == ("C2", False)


def test_external_0_forces_local_for_everyone() -> None:
    a = _assess(_msgs(("tool", _marked("page", "C2", external=False))), "unifai")
    assert (a.classification, a.local_only) == ("C2", True)


def test_an_unmarked_tool_message_is_c2_local_for_an_experience_client_only() -> None:
    a = _assess(_msgs(("tool", "some tool output")), "openclaw-sale-01")
    assert (a.classification, a.local_only) == ("C2", True)
    b = _assess(_msgs(("tool", "some tool output")), "unifai")
    assert (b.classification, b.local_only) == ("C1", False)


def test_a_marker_moved_onto_other_text_does_not_verify() -> None:
    marker = _marked("a C1 drive listing", "C1").split("\n\n")[-1]
    forged = "secret confluence content\n\n" + marker
    a = _assess(_msgs(("tool", forged)), "open-webui")
    assert (a.classification, a.local_only) == ("C2", True), "a replayed marker counts as missing"


def test_a_marker_signed_with_another_key_is_ignored() -> None:
    a = _assess(_msgs(("tool", _marked("page", "C1", key="other"))), "open-webui")
    assert (a.classification, a.local_only) == ("C2", True)


def test_markers_in_a_user_or_system_message_are_read_too() -> None:
    """Open WebUI's default (non-native) tool mode puts tool output in the prompt."""
    a = _assess(_msgs(("system", "context:\n" + _marked("page", "C2"))), "open-webui")
    assert (a.classification, a.local_only) == ("C2", True)


def test_two_results_in_one_message_are_each_verified() -> None:
    text = _marked("first", "C1") + "\n" + _marked("second", "C2")
    a = _assess(_msgs(("tool", text)), "unifai")
    assert a.classification == "C2"


def test_nothing_lowers_a_classification_or_lifts_local_only() -> None:
    a = _assess(_msgs(("tool", _marked("x", "C1"))), "open-webui", classification="C3", local_only=True)
    assert (a.classification, a.local_only) == ("C3", True)


def test_c4_is_routed_as_c3_local() -> None:
    a = _assess(_msgs(("tool", _marked("x", "C4"))), "unifai")
    assert (a.classification, a.local_only) == ("C3", True)


def test_without_a_key_no_marker_is_trusted() -> None:
    with mock.patch.dict(os.environ, {"ZUNO_MARKER_KEY": "", "MARKER_FAIL_CLOSED_CLIENTS": "open-webui"}):
        a = tool_markers.assess(_msgs(("tool", _marked("x", "C1"))), "C1", False, "open-webui")
    assert (a.classification, a.local_only) == ("C2", True)


def test_a_plain_chat_is_unchanged() -> None:
    a = _assess(_msgs(("system", "be nice"), ("user", "hello")), "open-webui")
    assert (a.classification, a.local_only, a.changed) == ("C1", False, False)


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
