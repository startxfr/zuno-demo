#!/usr/bin/env python3
"""ADR-0209 (WP-28) acceptance tests for the memory-extraction step
(app/memory.py) - fact/decision identification and the ADR-0035
local-only rule for C2/C3 conversations. Model calls are mocked (no live
AI Gateway); same no-pytest style as tests/test_retrieve_metadata.py.

Run directly:

    cd components/agent-runtime && python3 tests/test_memory_extraction.py
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
from unittest import mock

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.clients.model_router import ModelRouter, ModelRouterError  # noqa: E402
from app.memory import MemoryExtractionError, extract_memory  # noqa: E402


class _FakeResult:
    def __init__(self, content: str):
        self.content = content


def _fake_router(response_json: dict):
    router = ModelRouter()

    async def fake_invoke(**kwargs):
        return _FakeResult(json.dumps(response_json)), None

    router.invoke_with_fallback = mock.AsyncMock(side_effect=fake_invoke)
    return router


def test_extracts_facts_and_memories_from_a_valid_model_response() -> None:
    router = _fake_router({
        "facts": [{"key": "openshift_version", "value": "4.22"}, {"key": "cloud", "value": "AWS"}],
        "memories": [{"kind": "fact", "text": "The project runs OpenShift 4.22 on AWS across three clusters."}],
    })

    facts, memories = asyncio.run(
        extract_memory(router, "User: we run OpenShift 4.22 on AWS, three clusters.", "C1", "token")
    )
    assert facts == [{"key": "openshift_version", "value": "4.22"}, {"key": "cloud", "value": "AWS"}]
    assert len(memories) == 1
    assert memories[0]["kind"] == "fact"


def test_identifies_a_decision_distinct_from_a_fact() -> None:
    router = _fake_router({
        "facts": [],
        "memories": [{"kind": "decision", "text": "The team decided to keep C2 data local-only."}],
    })

    facts, memories = asyncio.run(
        extract_memory(router, "User: let's keep that local-only, never send it externally.", "C2", "token")
    )
    assert facts == []
    assert memories[0]["kind"] == "decision"


def test_empty_extraction_is_a_valid_non_error_result() -> None:
    router = _fake_router({"facts": [], "memories": []})
    facts, memories = asyncio.run(extract_memory(router, "User: hello, how are you?", "C1", "token"))
    assert facts == []
    assert memories == []


def test_c2_conversation_forces_local_only_extraction() -> None:
    """ADR-0035: a C2/C3 conversation must never be summarized by an
    external model - forced local_only, same rule reason_node applies to
    its own reply."""
    router = _fake_router({"facts": [], "memories": []})
    asyncio.run(extract_memory(router, "sensitive transcript", "C2", "token"))
    call_kwargs = router.invoke_with_fallback.call_args.kwargs
    assert call_kwargs["local_only"] is True


def test_c3_conversation_also_forces_local_only_extraction() -> None:
    router = _fake_router({"facts": [], "memories": []})
    asyncio.run(extract_memory(router, "sensitive transcript", "C3", "token"))
    call_kwargs = router.invoke_with_fallback.call_args.kwargs
    assert call_kwargs["local_only"] is True


def test_c1_conversation_does_not_force_local_only() -> None:
    router = _fake_router({"facts": [], "memories": []})
    asyncio.run(extract_memory(router, "public transcript", "C1", "token"))
    call_kwargs = router.invoke_with_fallback.call_args.kwargs
    assert call_kwargs["local_only"] is False


def test_agent_local_only_forces_local_even_at_c1() -> None:
    """ADR-0416: an agent-level restriction (e.g. Finage) must force local
    regardless of classification - distinct from the C2/C3 rule above,
    which a C1 conversation would otherwise skip."""
    router = _fake_router({"facts": [], "memories": []})
    asyncio.run(extract_memory(router, "public transcript", "C1", "token", agent_local_only=True))
    call_kwargs = router.invoke_with_fallback.call_args.kwargs
    assert call_kwargs["local_only"] is True


def test_malformed_json_output_raises_rather_than_guessing() -> None:
    router = ModelRouter()

    async def fake_invoke(**kwargs):
        return _FakeResult("this is not JSON"), None

    router.invoke_with_fallback = mock.AsyncMock(side_effect=fake_invoke)

    try:
        asyncio.run(extract_memory(router, "transcript", "C1", "token"))
        raise AssertionError("expected MemoryExtractionError")
    except MemoryExtractionError as exc:
        assert "JSON" in str(exc)


def test_model_call_failure_raises_rather_than_silently_dropping_context() -> None:
    """ADR-0209 Operational considerations: "extraction failures must not
    silently drop a session's context ... logged and retried/flagged"."""
    router = ModelRouter()
    router.invoke_with_fallback = mock.AsyncMock(side_effect=ModelRouterError("all providers failed"))

    try:
        asyncio.run(extract_memory(router, "transcript", "C1", "token"))
        raise AssertionError("expected MemoryExtractionError")
    except MemoryExtractionError as exc:
        assert "extraction model call failed" in str(exc)


TESTS = [
    test_extracts_facts_and_memories_from_a_valid_model_response,
    test_identifies_a_decision_distinct_from_a_fact,
    test_empty_extraction_is_a_valid_non_error_result,
    test_c2_conversation_forces_local_only_extraction,
    test_c3_conversation_also_forces_local_only_extraction,
    test_c1_conversation_does_not_force_local_only,
    test_agent_local_only_forces_local_even_at_c1,
    test_malformed_json_output_raises_rather_than_guessing,
    test_model_call_failure_raises_rather_than_silently_dropping_context,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
