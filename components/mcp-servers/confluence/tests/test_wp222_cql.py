#!/usr/bin/env python3
"""WP-222 / ADR-0603: the model-chosen `space` and `query` cannot break out of the CQL string literal.

Run from this directory:  python3 tests/test_wp222_cql.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402


def test_escape() -> None:
    assert server._cql_escape('a" or space="HR') == 'a\\" or space=\\"HR'
    assert server._cql_escape("a\\b") == "a\\\\b"


def test_space_key_must_be_a_key() -> None:
    for bad in ('x" or space="HR', "A B", "", "A;B"):
        if bad == "":
            continue
        try:
            asyncio.run(server.search_pages("q", space=bad))
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_limit_is_capped() -> None:
    seen = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"results": []}

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            seen.update(params); return _Resp()

    with mock.patch.object(server, "_client", lambda: _Client()):
        asyncio.run(server.search_pages('say "hi"', space="ARCHI", limit=100000))
    assert seen["limit"] == 50
    assert seen["cql"] == 'space="ARCHI" and type=page and text~"say \\"hi\\""'


def test_personal_space_keys_are_accepted() -> None:
    for good in ("ARCHI", "~john.doe", "~557058:3f1c2d4e-aaaa"):
        assert server._SPACE_KEY_RE.fullmatch(good), good
    for bad in ('~x" or space="HR', "~", "A B"):
        assert not server._SPACE_KEY_RE.fullmatch(bad), bad


def test_page_id_must_be_numeric() -> None:
    for bad in ("../../admin", "123?expand=x", "12 3", ""):
        try:
            asyncio.run(server.read_page(bad))
        except ValueError:
            continue
        raise AssertionError(f"read_page accepted {bad!r}")
    try:
        asyncio.run(server.update_page("../1", "<p>x</p>"))
    except ValueError:
        pass
    else:
        raise AssertionError("update_page accepted a path")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("ok", n)
