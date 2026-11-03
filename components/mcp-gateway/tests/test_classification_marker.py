"""ADR-0594 (WP-191): every successful tools/call result on /mcp carries a signed
classification marker the ai-gateway can verify.

Run from the component directory:

    cd components/mcp-gateway && python3 -m pytest -q tests/test_classification_marker.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import sys
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import classification_marker, mcp_frontdoor  # noqa: E402

KEY = "test-marker-key"
_LINE = re.compile(r"\n\n\[zuno-classification level=(C[1-4]) external=([01]) sig=([0-9a-f]{64})\]$")


class _Binding:
    def __init__(self, names):
        self._names = names

    def all_names(self):
        return self._names


class _Registry:
    def resolve(self, name):
        return _Binding([name])


class _Policy:
    def __init__(self, entries):
        self._entries = entries

    def get_tool(self, name):
        return self._entries.get(name)


def _entry(level, external=True):
    return SimpleNamespace(min_classification=level, allow_external_context=external)


def _call(name, payload, policy):
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": {"query": "x"}}}
    surface = SimpleNamespace(capabilities=[name])

    async def invoke(tool_name, arguments):
        return payload

    out = asyncio.run(mcp_frontdoor.dispatch(
        message, policy_store=policy, binding_registry=_Registry(), identity=SimpleNamespace(sub="u"),
        classification="C2", invoke_tool=invoke, surface=surface,
    ))
    return out["result"]


def _verify(text):
    m = _LINE.search(text)
    assert m, text[-200:]
    level, external, sig = m.groups()
    body = text[: m.start()]
    digest = hashlib.sha256(body.strip().encode()).hexdigest()
    expected = hmac.new(KEY.encode(), f"{level}|{external}|{digest}".encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig, expected)
    return level, external == "1"


def test_a_c1_tool_result_is_marked_c1_external() -> None:
    with mock.patch.dict(os.environ, {"ZUNO_MARKER_KEY": KEY}):
        result = _call("list_drive_files", {"files": [{"name": "a"}]}, _Policy({"list_drive_files": _entry("C1")}))
    assert _verify(result["content"][0]["text"]) == ("C1", True)
    assert result["structuredContent"] == {"files": [{"name": "a"}]}  # unchanged


def test_a_no_external_context_tool_is_marked_external_0() -> None:
    with mock.patch.dict(os.environ, {"ZUNO_MARKER_KEY": KEY}):
        result = _call("confluence.page.search", {"results": []}, _Policy({"confluence.page.search": _entry("C2", False)}))
    assert _verify(result["content"][0]["text"]) == ("C2", False)


def test_levels_inside_the_result_raise_the_marker() -> None:
    payload = {"results": [{"id": "c1", "classification": "C1"}, {"id": "c2", "classification": "C3"}]}
    with mock.patch.dict(os.environ, {"ZUNO_MARKER_KEY": KEY}):
        result = _call("search_technical_docs", payload, _Policy({"search_technical_docs": _entry("C1")}))
    assert _verify(result["content"][0]["text"]) == ("C3", True)


def test_a_tool_unknown_to_the_policy_is_c2_without_external_context() -> None:
    with mock.patch.dict(os.environ, {"ZUNO_MARKER_KEY": KEY}):
        result = _call("mystery", {"x": 1}, _Policy({}))
    assert _verify(result["content"][0]["text"]) == ("C2", False)


def test_without_a_key_no_marker_is_added() -> None:
    with mock.patch.dict(os.environ, {"ZUNO_MARKER_KEY": ""}):
        result = _call("list_drive_files", {"files": []}, _Policy({"list_drive_files": _entry("C1")}))
    assert "zuno-classification" not in result["content"][0]["text"]


def test_the_signature_binds_the_text() -> None:
    with mock.patch.dict(os.environ, {"ZUNO_MARKER_KEY": KEY}):
        a = classification_marker.signature("C1", True, "one result")
        assert a != classification_marker.signature("C1", True, "another result")
        assert a != classification_marker.signature("C2", True, "one result")
        assert a != classification_marker.signature("C1", False, "one result")
        assert a == classification_marker.signature("C1", True, "  one result\n")  # surrounding whitespace only


def test_highest_and_levels_in() -> None:
    assert classification_marker.highest(["C1", "c2", None, "bogus"]) == "C2"
    assert classification_marker.highest([]) == "C1"
    assert sorted(classification_marker.levels_in({"a": [{"classification": "C2"}], "classification": "C1"})) == ["C1", "C2"]
