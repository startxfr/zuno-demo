"""The reply cap: body max_tokens / max_completion_tokens, the X-Zuno-Max-Tokens header and a default.

Before 2026-10-31 the request schema had no max_tokens field, so the 4096 the UnifAI client sends was
dropped and an arkos reply ran to ~40k tokens on gpt-oss-20b.
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main  # noqa: E402
from app.schemas import ChatCompletionRequest  # noqa: E402


def _req(**caps):
    return ChatCompletionRequest(messages=[{"role": "user", "content": "hi"}], **caps)


def test_the_schema_keeps_both_openai_cap_fields():
    r = ChatCompletionRequest.model_validate(
        {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10, "max_completion_tokens": 20})
    assert r.max_tokens == 10 and r.max_completion_tokens == 20


def test_the_smallest_cap_wins():
    with mock.patch.object(main, "MAX_TOKENS_DEFAULT", 8192):
        assert main._effective_max_tokens(None, _req(max_completion_tokens=4096)) == 4096
        assert main._effective_max_tokens(1536, _req(max_completion_tokens=4096)) == 1536
        assert main._effective_max_tokens(6000, _req(max_tokens=300, max_completion_tokens=4096)) == 300


def test_the_default_applies_only_when_no_cap_is_given():
    with mock.patch.object(main, "MAX_TOKENS_DEFAULT", 8192):
        assert main._effective_max_tokens(None, _req()) == 8192
        assert main._effective_max_tokens(None, _req(max_tokens=20000)) == 20000  # explicit caller cap
    with mock.patch.object(main, "MAX_TOKENS_DEFAULT", 0):
        assert main._effective_max_tokens(None, _req()) is None


def test_non_positive_body_caps_are_ignored():
    with mock.patch.object(main, "MAX_TOKENS_DEFAULT", 8192):
        assert main._effective_max_tokens(None, _req(max_tokens=0, max_completion_tokens=-5)) == 8192


def _msgs(chars):
    return [main.HumanMessage(content="x" * chars)]


def test_the_cap_shrinks_to_the_room_left_in_the_model_window():
    cfg = {"max_model_len": 32768}
    estimated = main._estimate_prompt_tokens(_msgs(100_000), None)
    assert main._candidate_max_tokens(8192, cfg, _msgs(100_000), None) == min(8192, 32768 - estimated)
    assert main._candidate_max_tokens(8192, cfg, _msgs(400), None) == 8192


def test_no_window_or_no_cap_leaves_the_cap_alone():
    assert main._candidate_max_tokens(4096, {}, _msgs(10), None) == 4096
    assert main._candidate_max_tokens(None, {"max_model_len": 32768}, _msgs(10), None) is None
    # prompt already over the window: keep the cap and let the upstream error surface (pre-flight logic)
    assert main._candidate_max_tokens(4096, {"max_model_len": 100}, _msgs(10_000), None) == 4096
