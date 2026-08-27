"""ADR-0528 (WP-090): X-Zuno-Project-Id carries the ZUNO project id, for
every project, and never a Salesforce identifier.

This suite replaces test_project_binding.py's
test_reason_node_forwards_project_id_only_when_task_is_project_required,
whose assertion ADR-0528 deliberately inverts. That test guarded a real
abuse channel: state["project_id"] used to be copied verbatim from the
request body, so gating the header on the task's own project_required mark
was the only thing stopping a caller from shifting consumption onto an
arbitrary project's quota bucket. ADR-0527 closed that channel higher up -
app/main.py's _initial_state no longer copies the client value at all, and
agent_chat resolves the id from the conversation's own projects row after
verifying the caller holds a grant. Database-verified membership is
strictly stronger than a frontmatter mark, so the gate could go and the
project dimension could widen to every project, customer or free.
"""
import asyncio
import json
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))

from app.graph import nodes  # noqa: E402
from app.graph.nodes import _make_reason_node  # noqa: E402
from app.registry import AgentDefinition, TaskDefinition  # noqa: E402

_SALESFORCE_ID = "006AbCdEfGhIjKlMno"


def _state(project_id):
    return {
        "message": "hi", "bearer_token": "t", "request_id": "req-1",
        "project_id": project_id, "project_context": "", "project_classification": None,
        "retrieved_docs": [], "tool_results": {}, "errors": [], "history": [], "summary": "",
    }


async def _capture_project_ids(project_required: bool, project_id):
    """Runs reason_node with the router stubbed, returning what it passed as
    project_id."""
    task = TaskDefinition(
        name="t", title="T", description="", allowed_tools=[], prompt="You are a test agent.",
    )
    task.project_required = project_required
    agent = AgentDefinition(name="fake-agent", status="active", preferred_classification="C2", rag_top_k=5)
    captured = []

    async def fake_invoke_with_fallback(**kwargs):
        captured.append(kwargs.get("project_id"))
        return SimpleNamespace(content="ok", tool_calls=[]), SimpleNamespace(name="ai-gateway")

    saved = nodes._model_router.invoke_with_fallback
    nodes._model_router.invoke_with_fallback = fake_invoke_with_fallback
    try:
        await _make_reason_node(agent, task)(_state(project_id))
    finally:
        nodes._model_router.invoke_with_fallback = saved
    return captured


async def test_an_unmarked_task_inside_a_project_now_draws_project_quota() -> None:
    """The inversion. Before ADR-0528 this asserted None; now every
    conversation attached to a real project carries the dimension, because
    the id can no longer be asserted by a client."""
    assert await _capture_project_ids(project_required=False, project_id="proj-uuid-1") == ["proj-uuid-1"]


async def test_a_project_required_task_is_unchanged() -> None:
    assert await _capture_project_ids(project_required=True, project_id="proj-uuid-1") == ["proj-uuid-1"]


async def test_a_conversation_with_no_project_sends_no_dimension() -> None:
    """model_router only sets the header when project_id is truthy, so a
    project-less conversation still attributes to the user budget alone
    (ADR-0511's default precedence)."""
    assert await _capture_project_ids(project_required=False, project_id=None) == [None]


async def test_the_project_required_gate_is_gone_from_every_call_site() -> None:
    """ADR-0528 clause 4. A single surviving `if task.project_required` gate
    would silently keep one graph path on the old behaviour - and it would
    be the kind of gap only a per-shape trace would ever reveal."""
    for name in ("nodes.py", "arkos_nodes.py"):
        source = (pathlib.Path(__file__).resolve().parents[1] / "app" / "graph" / name).read_text()
        assert "project_required else None" not in source, (
            f"app/graph/{name} still gates the quota header on task.project_required"
        )


async def test_no_salesforce_identifier_ever_reaches_the_outgoing_headers() -> None:
    """ADR-0528's hard boundary: the opportunity id stays in the database.
    Asserted against the real header-building code, not a stub, and by
    searching the WHOLE header dict rather than one key - a leak would most
    likely arrive under a name this test did not think to check."""
    from app.clients import model_router

    built = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            built.update(kwargs)

    saved = model_router.ChatOpenAI
    model_router.ChatOpenAI = _FakeChatOpenAI
    try:
        model_router.ModelRouter().chat_model_for(
            classification="C2",
            bearer_token="token",
            request_id="req-1",
            agent_name="fake-agent",
            task_name="t",
            project_id="proj-uuid-1",
            run_id="run-1",
        )
    finally:
        model_router.ChatOpenAI = saved

    headers = built.get("default_headers") or {}
    assert headers.get("X-Zuno-Project-Id") == "proj-uuid-1", headers
    assert _SALESFORCE_ID not in json.dumps(headers), headers
    assert not any("salesforce" in str(k).lower() or "salesforce" in str(v).lower()
                   for k, v in headers.items()), headers


TESTS = [
    test_an_unmarked_task_inside_a_project_now_draws_project_quota,
    test_a_project_required_task_is_unchanged,
    test_a_conversation_with_no_project_sends_no_dimension,
    test_the_project_required_gate_is_gone_from_every_call_site,
    test_no_salesforce_identifier_ever_reaches_the_outgoing_headers,
]


async def _run_all() -> int:
    failures = 0
    for test in TESTS:
        try:
            await test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    return failures


def main() -> int:
    failures = asyncio.run(_run_all())
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
