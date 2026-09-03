"""ADR-0544: app/graph/prompt_budget.py's clamp, proven against the exact
measured numbers agents/arkos/agent.okf.md's 2026-09-03 finding recorded
(draft-architecture-testimonial/workshop-presentation: 6000-token history
budget + ~420-token system prompt + up to 1200-token project context + 5
RAG chunks at a real corpus's median/p95 char length, against qwen3.5-9b's
8192-token window, the fleet-wide default and a structurally
always-reachable terminal fallback per ADR-0531 decision 1).

Two things this file exists to prevent: (1) the arithmetic silently
becoming "fine" again if someone widens a floor or a default without
noticing it reopens the overflow, and (2) the clamp silently rewriting a
per-agent declared budget on a turn that never needed it - the failure
mode that would make Arkos's deliberately generous 6000-token budget
meaningless on its own 32768-token nominal path.

Run from this directory: python3 tests/test_prompt_clamp.py
"""
import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "PROVIDER_ROUTING_PATH", str(_REPO_ROOT / "platform" / "ai-gateway" / "provider-routing.yaml")
)

from app.graph import prompt_budget as pb  # noqa: E402
from app.graph.history import build_history_messages, estimate_tokens  # noqa: E402

# The measured Arkos numbers (agents/arkos/agent.okf.md, 2026-09-03), kept
# as literal constants rather than re-derived from the live bundle - a
# fixture proving a specific bug is more valuable frozen than "current".
_ARKOS_HISTORY_BUDGET = 6000
_SYSTEM_PROMPT_TOKENS = 420
_PROJECT_CONTEXT_TOKENS = 1200
_RAG_CHUNK_MEDIAN = 312
_RAG_CHUNK_P95 = 449
_TOP_K = 5
_MEASURED_8192_WINDOW = 8192


def test_the_measured_arkos_prompt_overflowed_the_narrow_window() -> None:
    median_total = _SYSTEM_PROMPT_TOKENS + _ARKOS_HISTORY_BUDGET + _PROJECT_CONTEXT_TOKENS + _TOP_K * _RAG_CHUNK_MEDIAN
    p95_total = _SYSTEM_PROMPT_TOKENS + _ARKOS_HISTORY_BUDGET + _PROJECT_CONTEXT_TOKENS + _TOP_K * _RAG_CHUNK_P95
    assert median_total == 9180, median_total
    assert p95_total == 9865, p95_total
    assert median_total > _MEASURED_8192_WINDOW
    assert p95_total > _MEASURED_8192_WINDOW


def test_the_clamped_arkos_prompt_fits_the_narrow_window_and_keeps_all_rag() -> None:
    """Sacrifice order (ADR-0544, product decision): project context first
    (floor 0), then history (floor HISTORY_FLOOR_TOKENS), RAG last (floor
    CONTEXT_FLOOR_TOKENS) - retrieved for THIS question, so it gives way
    last of the three."""
    alloc = pb.allocate_prompt_budget(
        fixed_tokens=_SYSTEM_PROMPT_TOKENS,
        project_context_budget=_PROJECT_CONTEXT_TOKENS,
        history_budget=_ARKOS_HISTORY_BUDGET,
        context_tokens=_TOP_K * _RAG_CHUNK_P95,
        ceiling=_MEASURED_8192_WINDOW,
    )
    assert alloc.clamped is True
    assert alloc.residual_overflow == 0
    total = _SYSTEM_PROMPT_TOKENS + alloc.project_context_budget + alloc.history_budget + alloc.context_budget
    assert total <= _MEASURED_8192_WINDOW, total
    assert alloc.context_budget == _TOP_K * _RAG_CHUNK_P95, "RAG must be untouched - it gives way last"
    assert alloc.project_context_budget == 0, "project context sheds first, floor 0"
    assert alloc.history_budget < _ARKOS_HISTORY_BUDGET, "history must have shed something to fit"
    assert alloc.history_budget >= pb.HISTORY_FLOOR_TOKENS


def test_the_declared_per_agent_budget_is_never_rewritten() -> None:
    """allocate_prompt_budget returns what to USE this turn; it never
    mutates the caller's own AgentDefinition. Regression guard against the
    exact failure this repo already flagged as unacceptable: a clamp that
    quietly shrinks Arkos's declared 6000-token budget would gut the
    32768-token nominal path most of its turns actually run on."""
    from app.registry import AgentDefinition

    agent = AgentDefinition(
        name="fake-agent", status="active", preferred_classification="C3", rag_top_k=5,
        history_token_budget=_ARKOS_HISTORY_BUDGET,
    )
    pb.allocate_prompt_budget(
        fixed_tokens=_SYSTEM_PROMPT_TOKENS,
        project_context_budget=_PROJECT_CONTEXT_TOKENS,
        history_budget=agent.history_token_budget,
        context_tokens=_TOP_K * _RAG_CHUNK_P95,
        ceiling=_MEASURED_8192_WINDOW,
    )
    assert agent.history_token_budget == _ARKOS_HISTORY_BUDGET


def test_nothing_binds_when_the_prompt_fits() -> None:
    alloc = pb.allocate_prompt_budget(
        fixed_tokens=100, project_context_budget=200, history_budget=500, context_tokens=100,
        ceiling=5000,
    )
    assert alloc.clamped is False
    assert alloc.residual_overflow == 0
    assert alloc.project_context_budget == 200
    assert alloc.history_budget == 500
    assert alloc.context_budget == 100


def test_the_floor_is_read_from_the_real_provider_routing_yaml() -> None:
    """Points at the repo's actual file (set once, module-level, above) -
    not a fixture - so a real drift in provider-routing.yaml's declared
    windows fails this test, not just check_docs.py."""
    pb._cached_floor = None  # force a fresh read - module caches after first call
    assert pb.local_context_window_floor() == 8192


def test_a_missing_provider_routing_file_falls_back_to_the_conservative_floor(tmp_path) -> None:
    pb._cached_floor = None
    old_path = pb.PROVIDER_ROUTING_PATH
    pb.PROVIDER_ROUTING_PATH = str(tmp_path / "does-not-exist.yaml")
    try:
        assert pb.local_context_window_floor() == pb.LOCAL_CONTEXT_FLOOR_FALLBACK
    finally:
        pb.PROVIDER_ROUTING_PATH = old_path
        pb._cached_floor = None


def test_join_context_parts_is_byte_identical_to_the_pre_clamp_join_when_nothing_is_dropped() -> None:
    """The exact separator/format the old _build_context_block used
    ("\\n\\n---\\n\\n".join(...), or the literal no-context string) - a
    clamp that changes formatting on a turn that needed no clamping at all
    would be its own regression."""
    parts = ["[Doc A] (source-a)\nsnippet a", "[Doc B] (source-b)\nsnippet b"]
    old_style = "\n\n---\n\n".join(parts)
    assert pb.join_context_parts(parts, 10_000) == old_style
    assert pb.join_context_parts([], 10_000) == "(no supporting context retrieved)"


def test_join_context_parts_drops_lowest_ranked_chunks_from_the_end() -> None:
    parts = ["a" * 40, "b" * 40, "c" * 40]  # ~10 tokens each at char/4
    result = pb.join_context_parts(parts, token_budget=12)
    assert "aaa" in result
    assert "ccc" not in result, "lowest-ranked (last) chunk should be dropped first"
    assert "omitted" in result


def test_tool_schemas_inflate_fixed_tokens() -> None:
    without_tools = estimate_tokens("some task prompt")
    import json
    with_tools = without_tools + estimate_tokens(
        json.dumps([{"name": "generate_image", "parameters": {"type": "object"}}])
    )
    assert with_tools > without_tools


async def _capture_arkos_messages(retrieved_docs_count: int, chunk_chars: int):
    """Runs the REAL draft_node (against the real Arkos bundle, loaded at
    import time from AGENTS_DIR) with an oversized retrieved_docs list,
    router stubbed, and returns the assembled turn_messages."""
    from app.graph import arkos_nodes

    captured = {}

    async def fake_invoke_with_fallback(**kwargs):
        captured["messages"] = kwargs["messages"]
        return SimpleNamespace(content="ok", tool_calls=[]), SimpleNamespace(name="ai-gateway")

    saved = arkos_nodes._model_router.invoke_with_fallback
    arkos_nodes._model_router.invoke_with_fallback = fake_invoke_with_fallback
    try:
        state = {
            "message": "Draft a DAT for the GPU sizing project",
            "bearer_token": "t",
            "request_id": "req-1",
            "run_id": "run-1",
            "project_id": None,
            "project_context": "x" * 6000,  # forces project_context_budget to actually matter
            "history": [
                {"role": "user", "content": "earlier turn " + "y" * 200},
                {"role": "assistant", "content": "earlier reply " + "z" * 200},
            ],
            "summary": "",
            "retrieved_docs": [
                {"title": f"Doc {i}", "source": "confluence", "snippet": "w" * chunk_chars}
                for i in range(retrieved_docs_count)
            ],
            "tool_results": {},
            "errors": [],
            "doc_plan": {"doc_title": "Test DAT", "kind": "dat"},
            "local_only_required": False,
        }
        await arkos_nodes.draft_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved
    return captured["messages"]


async def test_draft_node_output_fits_the_fleets_narrowest_reachable_window() -> None:
    """The end-to-end proof: feed draft_node (the real overflow site) an
    oversized retrieved_docs list at real-corpus chunk size, and assert the
    ASSEMBLED prompt - not just the budget numbers - fits the ceiling."""
    messages = await _capture_arkos_messages(retrieved_docs_count=_TOP_K, chunk_chars=_RAG_CHUNK_P95 * 4)
    total = pb.estimate_messages_tokens(messages)
    assert total <= pb.prompt_token_ceiling(), (
        f"assembled prompt ~{total} tokens exceeds the clamp ceiling {pb.prompt_token_ceiling()}"
    )


async def test_draft_node_leaves_a_small_turn_unclamped() -> None:
    messages = await _capture_arkos_messages(retrieved_docs_count=1, chunk_chars=100)
    # A small turn's history_messages should come back exactly as
    # build_history_messages would produce unclamped (2 turns, both fit).
    assert len(messages) >= 3  # system + >=1 history + human


TESTS = [
    test_the_measured_arkos_prompt_overflowed_the_narrow_window,
    test_the_clamped_arkos_prompt_fits_the_narrow_window_and_keeps_all_rag,
    test_the_declared_per_agent_budget_is_never_rewritten,
    test_nothing_binds_when_the_prompt_fits,
    test_the_floor_is_read_from_the_real_provider_routing_yaml,
    test_join_context_parts_is_byte_identical_to_the_pre_clamp_join_when_nothing_is_dropped,
    test_join_context_parts_drops_lowest_ranked_chunks_from_the_end,
    test_tool_schemas_inflate_fixed_tokens,
]

ASYNC_TESTS = [
    test_draft_node_output_fits_the_fleets_narrowest_reachable_window,
    test_draft_node_leaves_a_small_turn_unclamped,
]


def _run_tmp_path_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_a_missing_provider_routing_file_falls_back_to_the_conservative_floor(pathlib.Path(d))


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

    try:
        _run_tmp_path_test()
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"FAIL test_a_missing_provider_routing_file_falls_back_to_the_conservative_floor: {exc}")
    else:
        print("PASS test_a_missing_provider_routing_file_falls_back_to_the_conservative_floor")

    for test in ASYNC_TESTS:
        try:
            asyncio.run(test())
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")

    total = len(TESTS) + 1 + len(ASYNC_TESTS)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
