"""ADR-0521 (WP-076) closeout tests for app/main.py's adapter-vs-MaaS
candidate guard (`_adapter_skips_maas`).

A LoRA adapter id replaces the request body's `model` field, which MaaS's
whole auth chain keys on (ipp-pre derives X-Gateway-Model-Name from it; no
MaaSModelRef exists for adapter ids) - and app/providers.py's own guard
silently drops the adapter on any via_maas candidate. So once `local-maas`
is preferred ahead of `local` (provider-routing.yaml), an adapter-declared
(agent, task) would silently lose its adapter unless the candidate loop
skips via_maas candidates whenever an adapter declaration resolved. These
tests pin that skip down on the streaming path (agent-runtime, the only
real caller, always streams) plus the helper's own semantics, mocking the
LangChain layer the same way tests/test_stream_telemetry.py does.

Run from this directory:

    python3 tests/test_maas_adapter_guard.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessageChunk  # noqa: E402

from app import main as app_main  # noqa: E402
from app.model_routing_policy import AdapterDeclaration  # noqa: E402
from app.routing import ProviderCandidate  # noqa: E402

_DECL = AdapterDeclaration(adapter="comage-lora", classification="C2")

_CFGS = {
    "local-maas": {
        "model": "qwen3.6-27b-instruct",
        "via_maas": True,
        "maas_model_ref": "zuno-ai-run/qwen36-27b-instruct-maas",
    },
    "local": {"model": "qwen3.6-27b-instruct", "serves_adapters": True},
}


def test_helper_semantics() -> None:
    assert app_main._adapter_skips_maas(_CFGS["local-maas"], _DECL) is True
    assert app_main._adapter_skips_maas(_CFGS["local-maas"], None) is False
    assert app_main._adapter_skips_maas(_CFGS["local"], _DECL) is False
    assert app_main._adapter_skips_maas(_CFGS["local"], None) is False


class _FakeStreamingModel:
    """One content chunk then a terminal usage chunk - the minimal healthy
    stream shape (see test_stream_telemetry.py)."""

    async def astream(self, _messages):
        yield AIMessageChunk(content="ok")
        yield AIMessageChunk(content="", usage_metadata={"input_tokens": 1, "output_tokens": 1})


def _run_stream(candidates, adapter_decl):
    """Drains `_stream_completion`, returning the (candidate, adapter)
    pairs chat_model_for was actually called with."""
    calls = []

    def _spy_chat_model_for(candidate, cfg, request_id=None, adapter=None, caller_bearer_token=None):
        calls.append((candidate.name, adapter))
        return _FakeStreamingModel()

    async def _drain():
        async for _ in app_main._stream_completion(
            candidates, "C3", [], "req-guard", adapter_decl=adapter_decl
        ):
            pass

    with mock.patch.object(app_main, "chat_model_for", _spy_chat_model_for), \
         mock.patch.object(app_main.routing_table, "provider_config", side_effect=lambda n: _CFGS[n]):
        asyncio.run(_drain())
    return calls


def test_adapter_declared_skips_maas_candidate() -> None:
    """With an adapter declaration resolved, the preferred via_maas
    candidate is skipped entirely - the direct sibling serves, and it
    serves the ADAPTER's model name, not the base model."""
    candidates = [
        ProviderCandidate(name="local-maas", kind="local"),
        ProviderCandidate(name="local", kind="local"),
    ]
    calls = _run_stream(candidates, _DECL)
    assert calls == [("local", "comage-lora")], (
        f"expected the direct candidate to serve the adapter, got {calls}"
    )


def test_no_adapter_keeps_maas_candidate_first() -> None:
    """Without a declaration the guard is inert: the via_maas candidate
    stays first and serves (the whole point of WP-076)."""
    candidates = [
        ProviderCandidate(name="local-maas", kind="local"),
        ProviderCandidate(name="local", kind="local"),
    ]
    calls = _run_stream(candidates, None)
    assert calls == [("local-maas", None)], (
        f"expected the via_maas candidate to serve, got {calls}"
    )


TESTS = [
    test_helper_semantics,
    test_adapter_declared_skips_maas_candidate,
    test_no_adapter_keeps_maas_candidate_first,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
