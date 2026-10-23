"""Reasoning-block fallback for vLLM reasoning parsers.

The local models run in vLLM with `--reasoning-parser=qwen3`: the parser
splits the output into `message.reasoning` (older vLLM: `reasoning_content`)
and `message.content`. When the model puts its WHOLE answer inside the
reasoning block, vLLM returns `content: null` (or "") and the answer only
exists in the reasoning field. LangChain's ChatOpenAI (langchain-openai
0.2.4) drops both reasoning fields, so clients used to receive an empty
answer (observed live on qwen3.5-9b-wesh: ~1 call in 8 with a ReAct prompt).

`with_reasoning()` returns a ChatOpenAI subclass that keeps the reasoning
text in `additional_kwargs["zuno_reasoning"]`; `app/main.py` then applies
ONE rule (`should_fold`): blank content AND no tool_calls AND reasoning
text present -> serve the reasoning as the content, flagged with
`zuno_reasoning_fallback: true`. Reasoning is never exposed otherwise.
"""

from __future__ import annotations

import functools
from typing import Any, AsyncIterator, Dict, List, Optional

REASONING_KEY = "zuno_reasoning"


def extract_reasoning(message_dict: Optional[Dict[str, Any]]) -> str:
    """`reasoning_content` (older vLLM) or `reasoning` (newer) from a raw
    OpenAI message/delta dict."""
    if not message_dict:
        return ""
    return message_dict.get("reasoning_content") or message_dict.get("reasoning") or ""


def reasoning_of(message: Any) -> str:
    kwargs = getattr(message, "additional_kwargs", None) or {}
    value = kwargs.get(REASONING_KEY)
    return value if isinstance(value, str) else ""


def should_fold(content: Any, has_tool_calls: bool, reasoning: str) -> bool:
    """The fallback rule: nothing usable in `content`, no tool call, and
    the model did produce reasoning text."""
    blank = not (content if isinstance(content, str) else str(content or "")).strip()
    return blank and not has_tool_calls and bool(reasoning.strip())


@functools.lru_cache(maxsize=None)
def _subclass(base: type) -> type:
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk
    from langchain_openai.chat_models import base as lc_base

    class ReasoningChatOpenAI(base):  # type: ignore[misc, valid-type]
        def _create_chat_result(self, response: Any, generation_info: Optional[Dict] = None):  # type: ignore[override]
            result = super()._create_chat_result(response, generation_info)
            raw = response if isinstance(response, dict) else response.model_dump()
            for gen, choice in zip(result.generations, raw.get("choices") or []):
                text = extract_reasoning(choice.get("message"))
                if text:
                    gen.message.additional_kwargs[REASONING_KEY] = text
            return result

        # Mirrors langchain-openai 0.2.4's ChatOpenAI/BaseChatOpenAI._astream (pinned in
        # requirements.txt) minus the response_format / response-headers
        # branches this gateway never uses; the only addition is the
        # reasoning delta capture.
        async def _astream(  # type: ignore[override]
            self,
            messages: List[Any],
            stop: Optional[List[str]] = None,
            run_manager: Any = None,
            stream_usage: Optional[bool] = None,
            **kwargs: Any,
        ) -> AsyncIterator[ChatGenerationChunk]:
            # ChatOpenAI._astream (the layer above BaseChatOpenAI's) adds the
            # include_usage stream option; replaced here, so redone here.
            stream_usage = self._should_stream_usage(stream_usage, **kwargs)
            if stream_usage:
                kwargs["stream_options"] = {"include_usage": stream_usage}
            kwargs["stream"] = True
            payload = self._get_request_payload(messages, stop=stop, **kwargs)
            default_chunk_class: type = AIMessageChunk
            response = await self.async_client.create(**payload)
            async with response:
                async for chunk in response:
                    if not isinstance(chunk, dict):
                        chunk = chunk.model_dump()
                    gen_chunk = lc_base._convert_chunk_to_generation_chunk(chunk, default_chunk_class, {})
                    if gen_chunk is None:
                        continue
                    default_chunk_class = gen_chunk.message.__class__
                    choices = chunk.get("choices") or []
                    text = extract_reasoning(choices[0].get("delta")) if choices else ""
                    if text:
                        gen_chunk.message.additional_kwargs[REASONING_KEY] = text
                    if run_manager:
                        await run_manager.on_llm_new_token(gen_chunk.text, chunk=gen_chunk)
                    yield gen_chunk

    ReasoningChatOpenAI.__name__ = "ReasoningChatOpenAI"
    return ReasoningChatOpenAI


def with_reasoning(chat_openai: Any) -> Any:
    """Returns the reasoning-aware subclass of `chat_openai`. Anything that
    is not a real class (a unit-test mock standing in for ChatOpenAI) is
    returned unchanged."""
    if not isinstance(chat_openai, type):
        return chat_openai
    return _subclass(chat_openai)
