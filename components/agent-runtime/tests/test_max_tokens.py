"""ADR-0544: the declarative per-task max_tokens mechanism, end to end on
this side of the boundary - schema parse -> TaskDefinition -> forwarded as
X-Zuno-Max-Tokens by the real header-building code in
app/clients/model_router.py. The ai-gateway half (header parse -> per-
vendor factory kwarg, including the via_maas branch that structure-demo's
own preferred candidate actually uses) is tested in
components/ai-gateway/tests/test_max_tokens_passthrough.py.

Run from this directory: python3 tests/test_max_tokens.py
"""
import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from app.registry import AgentRegistry, TaskDefinition  # noqa: E402


def test_structure_demo_declares_its_real_max_tokens() -> None:
    """The bundle's first real usage - proves the schema/frontmatter/
    registry parse chain actually works against the checked-in file, not
    just a synthetic fixture."""
    registry = AgentRegistry()
    arkos = registry.get("arkos")
    task = arkos.tasks["structure-demo"]
    assert task.max_tokens == 1536, task.max_tokens


def test_a_task_with_no_declared_max_tokens_stays_none() -> None:
    """Absent means uncapped, today's exact pre-ADR-0544 behavior - the
    default this mechanism must not silently change for every OTHER task."""
    registry = AgentRegistry()
    arkos = registry.get("arkos")
    task = arkos.tasks["write-code"]
    assert task.max_tokens is None


async def _capture_demo_node_call():
    from app.graph import arkos_nodes

    captured = {}

    async def fake_invoke_with_fallback(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content="ok", tool_calls=[]), SimpleNamespace(name="ai-gateway")

    saved = arkos_nodes._model_router.invoke_with_fallback
    arkos_nodes._model_router.invoke_with_fallback = fake_invoke_with_fallback
    try:
        state = {
            "message": "Structure a demo for the GPU sizing project",
            "bearer_token": "t", "request_id": "req-1", "run_id": "run-1",
            "local_only_required": False,
        }
        await arkos_nodes.demo_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved
    return captured


async def test_demo_node_forwards_the_real_bundles_max_tokens() -> None:
    captured = await _capture_demo_node_call()
    assert captured.get("max_tokens") == 1536


async def test_write_code_forwards_none_for_max_tokens() -> None:
    from app.graph import arkos_nodes

    captured = {}

    async def fake_invoke_with_fallback(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content="ok", tool_calls=[]), SimpleNamespace(name="ai-gateway")

    saved = arkos_nodes._model_router.invoke_with_fallback
    arkos_nodes._model_router.invoke_with_fallback = fake_invoke_with_fallback
    try:
        state = {
            "message": "write a script", "bearer_token": "t", "request_id": "req-1",
            "run_id": "run-1", "local_only_required": False,
        }
        await arkos_nodes.code_node(state)
    finally:
        arkos_nodes._model_router.invoke_with_fallback = saved
    assert captured.get("max_tokens") is None


def test_chat_model_for_emits_the_header_when_max_tokens_is_set() -> None:
    """Against the REAL header-building code (model_router.chat_model_for),
    not a stub - mirrors test_quota_headers.py's
    test_no_salesforce_identifier_ever_reaches_the_outgoing_headers
    pattern exactly."""
    from app.clients import model_router

    built = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            built.update(kwargs)

    saved = model_router.ChatOpenAI
    model_router.ChatOpenAI = _FakeChatOpenAI
    try:
        model_router.ModelRouter().chat_model_for(
            classification="C3", bearer_token="token", agent_name="arkos",
            task_name="structure-demo", max_tokens=1536,
        )
    finally:
        model_router.ChatOpenAI = saved

    assert built["default_headers"]["X-Zuno-Max-Tokens"] == "1536"


def test_chat_model_for_emits_no_header_when_max_tokens_is_none() -> None:
    from app.clients import model_router

    built = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            built.update(kwargs)

    saved = model_router.ChatOpenAI
    model_router.ChatOpenAI = _FakeChatOpenAI
    try:
        model_router.ModelRouter().chat_model_for(
            classification="C3", bearer_token="token", agent_name="arkos",
            task_name="write-code",
        )
    finally:
        model_router.ChatOpenAI = saved

    assert "X-Zuno-Max-Tokens" not in built["default_headers"]


TESTS = [
    test_structure_demo_declares_its_real_max_tokens,
    test_a_task_with_no_declared_max_tokens_stays_none,
    test_chat_model_for_emits_the_header_when_max_tokens_is_set,
    test_chat_model_for_emits_no_header_when_max_tokens_is_none,
]

ASYNC_TESTS = [
    test_demo_node_forwards_the_real_bundles_max_tokens,
    test_write_code_forwards_none_for_max_tokens,
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

    for test in ASYNC_TESTS:
        try:
            asyncio.run(test())
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")

    total = len(TESTS) + len(ASYNC_TESTS)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
