#!/usr/bin/env python3
"""WP-112 unit tests for app/graph/nodes.py's narrated-instead-of-called
visual-tool retry (_retry_narrated_visual_tool_call, wired into
reason_node/_make_reason_node). Same no-pytest, direct-call style as
tests/test_arkos_nodes.py - these build a reason_node for Comage's own
check-deal-status task (_make_reason_node), the exact (agent, task) pair
the live defect this WP fixes was found on
(evaluations/comage/stress_test.py::img-mockup_request), rather than the
module-level Tekos-bound `reason_node`, since Tekos never declares
generate_image (only generate_diagram - see
agents/tekos/tasks/answer-technical-question.md's own comment).

Run directly:

    cd components/agent-runtime && python3 tests/test_reason_node_narration_retry.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
os.environ.setdefault("AGENTS_DIR", str(_REPO_ROOT / "agents"))
os.environ.setdefault(
    "KNOWLEDGE_POLICY_PATH", str(_REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml")
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # import app.*

from app.clients.model_router import ModelRouterError, ProviderCandidate  # noqa: E402
from app.graph import nodes  # noqa: E402

_COMAGE = nodes._registry.get("comage")
_CHECK_DEAL_STATUS_TASK = _COMAGE.tasks.get("check-deal-status")
comage_reason_node = nodes._make_reason_node(_COMAGE, _CHECK_DEAL_STATUS_TASK)


class _FakeModelResult:
    def __init__(self, content: str, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


_BASE_STATE = {
    "message": "Can you generate a mockup image to go with this deal's proposal?",
    "bearer_token": "t",
    "request_id": "req-1",
    "retrieved_docs": [],
}


async def test_reason_node_retries_and_succeeds_when_the_reply_narrates_generate_image() -> None:
    """The live-observed shape: the model reasons correctly ('for a
    marketing visual I use generate_image') but never actually calls it -
    zero tool_calls, the tool name present in the reply text. The retry
    offers generate_image again with the narration fed back, and this
    time the model actually calls it."""
    call_count = 0

    async def fake_invoke(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                _FakeModelResult("Pour un visuel marketing j'utilise generate_image. C'est le bon outil."),
                ProviderCandidate(name="ai-gateway"),
            )
        if call_count == 2:
            assert kwargs.get("tools"), "the retry round must still offer the visual tool schemas"
            assert kwargs["messages"][-1].__class__.__name__ == "HumanMessage", (
                "the retry must append an explicit nudge as the final message"
            )
            return (
                _FakeModelResult(
                    "",
                    tool_calls=[
                        {"name": "generate_image", "args": {"prompt": "a marketing mockup"}, "id": "call_1"}
                    ],
                ),
                ProviderCandidate(name="ai-gateway"),
            )
        # _resolve_image_generation_call's own follow-up (tool-less) call,
        # composing the natural-language reply after the retry's real
        # tool call resolved.
        return _FakeModelResult("Here's the marketing mockup."), ProviderCandidate(name="ai-gateway")

    async def fake_invoke_tool(**kwargs):
        return {
            "tool": "generate_image",
            "result": {"data_base64": "abc123", "mime_type": "image/png", "alt": "a marketing mockup"},
        }

    saved_invoke = nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    try:
        nodes._model_router.invoke_with_fallback = fake_invoke
        nodes.invoke_tool = fake_invoke_tool
        result = await comage_reason_node(dict(_BASE_STATE))
    finally:
        nodes._model_router.invoke_with_fallback = saved_invoke
        nodes.invoke_tool = saved_invoke_tool

    assert call_count == 3, "must call the model exactly three times: original + one retry + the follow-up reply"
    assert result["reply"] == "Here's the marketing mockup."
    assert result["generated_images"] == [
        {"data_base64": "abc123", "mime_type": "image/png", "alt": "a marketing mockup"}
    ]


async def test_reason_node_falls_back_to_the_retrys_own_words_when_it_narrates_again() -> None:
    """One shot only: if the retry ALSO narrates instead of calling, its
    own (possibly different) words become the final reply - not the
    original narration, and not a surfaced error."""
    call_count = 0

    async def fake_invoke(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                _FakeModelResult("J'utilise generate_image pour ce visuel."),
                ProviderCandidate(name="ai-gateway"),
            )
        return (
            _FakeModelResult("En fait, generate_image n'est pas adapte ici, je vais juste decrire l'idee."),
            ProviderCandidate(name="ai-gateway"),
        )

    saved_invoke = nodes._model_router.invoke_with_fallback
    try:
        nodes._model_router.invoke_with_fallback = fake_invoke
        result = await comage_reason_node(dict(_BASE_STATE))
    finally:
        nodes._model_router.invoke_with_fallback = saved_invoke

    assert call_count == 2
    assert result["reply"] == "En fait, generate_image n'est pas adapte ici, je vais juste decrire l'idee."


async def test_reason_node_falls_back_to_the_original_reply_when_the_retry_call_fails() -> None:
    """A ModelRouterError on the retry round must not surface as a system
    error - the original (narrated) reply is already a valid answer, so
    it is used as-is."""
    call_count = 0

    async def fake_invoke(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                _FakeModelResult("Je vais utiliser generate_image pour cette maquette."),
                ProviderCandidate(name="ai-gateway"),
            )
        raise ModelRouterError("all eligible providers failed")

    saved_invoke = nodes._model_router.invoke_with_fallback
    try:
        nodes._model_router.invoke_with_fallback = fake_invoke
        result = await comage_reason_node(dict(_BASE_STATE))
    finally:
        nodes._model_router.invoke_with_fallback = saved_invoke

    assert call_count == 2
    assert result["reply"] == "Je vais utiliser generate_image pour cette maquette."
    assert result["provider_used"] == "ai-gateway"


async def test_reason_node_does_not_retry_a_reply_that_never_mentions_a_visual_tool_by_name() -> None:
    """The narrow detection (literal tool name in the reply) must not fire
    on an ordinary tool-less answer - a single model call only."""
    call_count = 0

    async def fake_invoke(**kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeModelResult("OpenShift AI runs on RHEL CoreOS nodes."), ProviderCandidate(name="ai-gateway")

    saved_invoke = nodes._model_router.invoke_with_fallback
    try:
        nodes._model_router.invoke_with_fallback = fake_invoke
        result = await comage_reason_node({**_BASE_STATE, "message": "What OS do the nodes run?"})
    finally:
        nodes._model_router.invoke_with_fallback = saved_invoke

    assert call_count == 1, "must not retry when the reply never names a visual tool"
    assert result["reply"] == "OpenShift AI runs on RHEL CoreOS nodes."


async def test_reason_node_does_not_retry_when_a_real_tool_call_already_fired() -> None:
    """A genuine first-attempt tool call must go straight to its resolver,
    never through the narration-retry path (which only fires when
    tool_calls is empty)."""
    call_count = 0

    async def fake_invoke(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (
                _FakeModelResult(
                    "", tool_calls=[{"name": "generate_image", "args": {"prompt": "a mascot"}, "id": "call_1"}]
                ),
                ProviderCandidate(name="ai-gateway"),
            )
        # _resolve_image_generation_call's own follow-up call.
        return _FakeModelResult("Here's the mascot."), ProviderCandidate(name="ai-gateway")

    async def fake_invoke_tool(**kwargs):
        return {"tool": "generate_image", "result": {"data_base64": "xyz", "mime_type": "image/png", "alt": "a mascot"}}

    saved_invoke = nodes._model_router.invoke_with_fallback
    saved_invoke_tool = nodes.invoke_tool
    try:
        nodes._model_router.invoke_with_fallback = fake_invoke
        nodes.invoke_tool = fake_invoke_tool
        result = await comage_reason_node(dict(_BASE_STATE))
    finally:
        nodes._model_router.invoke_with_fallback = saved_invoke
        nodes.invoke_tool = saved_invoke_tool

    assert call_count == 2, "exactly the real tool call + its own follow-up reply, no extra narration-retry round"
    assert result["generated_images"] == [{"data_base64": "xyz", "mime_type": "image/png", "alt": "a mascot"}]


# --- WP-112, 2026-09-03: the widened trigger --------------------------
# Three live runs produced three different failing replies for
# evaluations/comage/stress_test.py::img-mockup_request, and NOT ONE of
# them names a tool - so _NARRATED_TOOL_NAME_PATTERN alone could never
# fire on any of them. These are the verbatim replies, kept as the
# regression corpus, with sxa_visualization_boundary's deliberate decline
# as the negative case it must never swallow.

_LIVE_NARRATIONS = [
    (
        "boundary_adjudication_2026_09_03_run1",
        "\n\nOuais, pour un visuel de proposition commerciale, c'est le bon "
        "outil. C'est un mockup marketing, pas une visualisation de "
        "donn\u00e9es structur\u00e9es.",
    ),
    (
        "conditional_promise_2026_09_03_run2",
        "\n\nJ'ai pas de document de r\u00e9f\u00e9rence pour construire un mockup "
        "r\u00e9aliste. Fournis le contenu exact \u00e0 illustrer et j'gen\u00e8re le visuel "
        "proprement.",
    ),
    ("bare_intent_2026_09_03_run3", "\n\nOuais, j'peux faire ca."),
]


async def test_reason_node_retries_every_live_narration_that_names_no_tool() -> None:
    """The three real failing replies, verbatim. Each must trigger the
    retry even though none contains "generate_image"/"generate_diagram"."""
    for case, narration in _LIVE_NARRATIONS:
        call_count = 0

        async def fake_invoke(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FakeModelResult(narration), ProviderCandidate(name="ai-gateway")
            return (
                _FakeModelResult(
                    "", tool_calls=[{"name": "generate_image", "args": {"prompt": "a deal mockup"}, "id": "call_1"}]
                ),
                ProviderCandidate(name="ai-gateway"),
            )

        async def fake_invoke_tool(**kwargs):
            return {
                "tool": "generate_image",
                "result": {"data_base64": "img", "mime_type": "image/png", "alt": "a deal mockup"},
            }

        saved_invoke = nodes._model_router.invoke_with_fallback
        saved_invoke_tool = nodes.invoke_tool
        try:
            nodes._model_router.invoke_with_fallback = fake_invoke
            nodes.invoke_tool = fake_invoke_tool
            result = await comage_reason_node(dict(_BASE_STATE))
        finally:
            nodes._model_router.invoke_with_fallback = saved_invoke
            nodes.invoke_tool = saved_invoke_tool

        assert call_count >= 2, f"{case}: the widened trigger did not fire on a real live narration"
        assert result["generated_images"] == [
            {"data_base64": "img", "mime_type": "image/png", "alt": "a deal mockup"}
        ], f"{case}: the retry fired but its tool call was not resolved"


async def test_reason_node_does_not_retry_a_deliberate_decline() -> None:
    """The load-bearing negative case. sxa_visualization_boundary (1/1
    passing live) depends on Comage being able to refuse without being
    nudged into fabricating a visual. Note this reply opens on "J'ai pas"
    exactly like the conditional-promise narration above, so the opener
    is not the discriminator - the explicit refusal is."""
    for case, decline in (
        ("sxa_boundary_verbatim", "\n\nJ'ai pas le tableau de donn\u00e9es. J'ai pas le droit de cr\u00e9er des tranches invent\u00e9es."),
        ("sxa_boundary_live_variant", "\n\nJ'ai pas les donn\u00e9es de g\u00e9n\u00e9ration de devis entre 2003 et 2013. J'ai pas de quoi construire ce pie chart."),
    ):
        call_count = 0

        async def fake_invoke(**kwargs):
            nonlocal call_count
            call_count += 1
            return _FakeModelResult(decline), ProviderCandidate(name="ai-gateway")

        saved_invoke = nodes._model_router.invoke_with_fallback
        try:
            nodes._model_router.invoke_with_fallback = fake_invoke
            result = await comage_reason_node(
                {**_BASE_STATE, "message": "Genere un pie chart des devis SXA entre 2003 et 2013."}
            )
        finally:
            nodes._model_router.invoke_with_fallback = saved_invoke

        assert call_count == 1, f"{case}: a correct decline must never be retried"
        assert result["reply"] == decline, f"{case}: the decline must survive verbatim"


TESTS = [
    test_reason_node_retries_and_succeeds_when_the_reply_narrates_generate_image,
    test_reason_node_falls_back_to_the_retrys_own_words_when_it_narrates_again,
    test_reason_node_falls_back_to_the_original_reply_when_the_retry_call_fails,
    test_reason_node_does_not_retry_a_reply_that_never_mentions_a_visual_tool_by_name,
    test_reason_node_does_not_retry_when_a_real_tool_call_already_fired,
    test_reason_node_retries_every_live_narration_that_names_no_tool,
    test_reason_node_does_not_retry_a_deliberate_decline,
]


async def _run_all() -> int:
    failed = 0
    for test in TESTS:
        try:
            result = test()
            if asyncio.iscoroutine(result):
                await result
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    return failed


def main() -> int:
    failed = asyncio.run(_run_all())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
