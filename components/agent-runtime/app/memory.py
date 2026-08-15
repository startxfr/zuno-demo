"""ADR-0209 (WP-28): the memory-extraction step - identifies durable
facts, decisions, constraints and actions from a conversation transcript,
never persisting raw turns verbatim (that stays WP-08's checkpointer
concern, a deliberately separate persistence store - see that ADR's
Decision). Triggered explicitly (app/main.py's extract-memory endpoint),
not automatically on every turn: extraction is a session-end/checkpoint
action, not per-message overhead.

ADR-0035: a conversation carrying C2/C3 content is summarized by a
local-only model - the same rule app/graph/nodes.py:reason_node already
applies to the conversation's own reply, extended to this step because a
summary of restricted content is still restricted content.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from app.clients.model_router import ModelRouter, ModelRouterError

logger = logging.getLogger("agent_runtime.memory")

_EXTRACTION_SYSTEM_PROMPT = """\
You identify durable, engagement-scoped memory from a technical \
conversation transcript between a user and an assistant.

Extract ONLY information the user or assistant stated as a fact, a \
decision, a constraint, or a planned action - never speculation, never \
small talk, never the literal conversation itself.

Respond with ONLY a JSON object of this exact shape, no other text:
{"facts": [{"key": "short_snake_case_identifier", "value": "the fact, as a short string"}], \
"memories": [{"kind": "fact|decision|constraint|action", "text": "one durable sentence"}]}

Both arrays may be empty if the transcript contains nothing durable - \
that is a valid, expected result, not an error."""


class MemoryExtractionError(RuntimeError):
    pass


async def extract_memory(
    model_router: ModelRouter,
    transcript: str,
    classification: str,
    bearer_token: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (facts, memories) - both possibly empty. Raises
    MemoryExtractionError on a model-call failure or unparseable output;
    the caller (app/main.py's endpoint) is responsible for ADR-0209's
    Operational considerations requirement ("extraction failures must not
    silently drop a session's context... logged and retried/flagged") -
    this function only guarantees it never returns a half-parsed or
    guessed result.
    """
    local_only = classification.upper() in ("C2", "C3")
    system = SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT)
    human = HumanMessage(content=transcript)

    try:
        result, _ = await model_router.invoke_with_fallback(
            classification=classification,
            messages=[system, human],
            bearer_token=bearer_token,
            local_only=local_only,
        )
    except ModelRouterError as exc:
        logger.error("memory extraction model call failed: %s", exc)
        raise MemoryExtractionError(f"extraction model call failed: {exc}") from exc

    content = result.content if hasattr(result, "content") else str(result)
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("memory extraction produced non-JSON output, nothing persisted: %r", content)
        raise MemoryExtractionError(f"extraction output was not valid JSON: {exc}") from exc

    facts = parsed.get("facts") or []
    memories = parsed.get("memories") or []
    if not isinstance(facts, list) or not isinstance(memories, list):
        raise MemoryExtractionError("extraction output's facts/memories were not arrays")
    return facts, memories
