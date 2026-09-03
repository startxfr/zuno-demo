"""ADR-0544: clamp the assembled prompt against the real fleet-wide
narrowest local model window, without agent-runtime learning any
ROUTING decision from ai-gateway's config.

Why this exists: since ADR-0531, `qwen3.5-9b` (role `default`,
platform/ai-gateway/provider-routing.yaml) is a structurally
always-reachable terminal fallback for essentially every (agent, task)
chain, and it serves `--max-model-len=8192` while the other three local
models serve 32768. agent-runtime assembled prompts against a static
per-agent budget (app/registry.py's HISTORY_TOKEN_BUDGET) with no
awareness of which model would answer - measured live against Arkos's
real corpus, its two RAG-bearing tasks assembled ~9,180-9,865 tokens
against that 8192 window, overflowing before a single output token
(agents/arkos/agent.okf.md's dated 2026-09-03 measurement).

Why static and conservative, not a live handshake: ai-gateway only
decides which candidate actually serves a turn AFTER receiving the
fully-assembled prompt (its candidate loop is try-each-in-chain-order,
entangled with the HTTP call itself - there is no discrete "pick a
model" step before that). Building a synchronous protocol so
agent-runtime could ask first was rejected in favor of the simpler fix:
agent-runtime reads ONE physical fact - the narrowest `max_model_len`
among LOCAL providers in the SAME provider-routing.yaml ConfigMap
ai-gateway already reads - and clamps toward it. It deliberately does
NOT parse `eligible_for`, `prefer`, `role`, or file order: that would be
a second, independently-maintained routing implementation, exactly the
drift class this repo spent 2026-09-03 finding and fixing instances of
elsewhere. `platform/docs/check_docs.py`'s `model_context_windows` check
keeps the one field this module does read honest against
gitops/charts/models/values.yaml.

The one imprecision this buys: the floor is global, not per-(agent,
task). arkos/write-code's chain is `strict: [mistral-codestral]` and can
never reach a local model at all, yet still gets clamped to 8192 -
accepted, since that call carries no history/RAG context to begin with
(components/agent-runtime/app/graph/nodes.py's code_node), so the floor
never actually binds there.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import yaml

from app.graph.history import estimate_tokens

logger = logging.getLogger("agent_runtime.graph.prompt_budget")

PROVIDER_ROUTING_PATH = os.getenv(
    "PROVIDER_ROUTING_PATH", "/app/config/provider-routing.yaml"
)

# The narrowest max_model_len in the fleet as of ADR-0544 (qwen3.5-9b).
# Used when the ConfigMap this module wants is missing/unmounted/
# unparseable - agent-runtime must not gain a startup dependency on the
# `llm` Application (the volume mount is `optional: true`), so a missing
# file degrades TOWARD the conservative value, mirroring
# RoutingTable._load's own fail-closed posture on the ai-gateway side.
LOCAL_CONTEXT_FLOOR_FALLBACK = 8192

# Ops escape hatch: override the computed floor without a code change,
# e.g. if a cluster's fleet composition differs from this repo's default.
_CONTEXT_FLOOR_OVERRIDE_ENV = "ZUNO_MODEL_CONTEXT_FLOOR"

# How much of the ceiling a turn with no declared max_tokens (ADR-0544's
# other half - platform/okf/schema/zuno-okf-task-v0.2.schema.json) is
# assumed to need for its own reply. A turn that DOES declare max_tokens
# reserves that many instead - see allocate_prompt_budget's output_reserve.
OUTPUT_RESERVE_TOKENS = int(os.getenv("ZUNO_OUTPUT_RESERVE_TOKENS", "1024"))

# Sacrifice-order floors (ADR-0544): project context can go to zero (it is
# static across the engagement and already framed as background, not
# instructions - ADR-0527); history and RAG context each keep a minimum
# so a clamped turn is degraded, not gutted. build_history_messages
# already guarantees at least one verbatim turn regardless of budget, so
# HISTORY_FLOOR_TOKENS is headroom for that guarantee, not a new promise.
HISTORY_FLOOR_TOKENS = 512
CONTEXT_FLOOR_TOKENS = 512  # roughly one median RAG chunk (~312 tok) + margin

_CHARS_PER_TOKEN = 4  # mirrors history.py's own heuristic

_cached_floor: Optional[int] = None


def local_context_window_floor() -> int:
    """`min(max_model_len)` across every `kind: local` provider in
    provider-routing.yaml - the narrowest window ANY chain reaching a
    local model could be answered by. Cached after first read; this
    process does not need to notice a live ConfigMap edit (a rebuild
    already bakes ai-gateway's own copy of the same config, per
    ADR-0531's operational note on how this file takes effect).
    """
    global _cached_floor
    if _cached_floor is not None:
        return _cached_floor

    override = os.getenv(_CONTEXT_FLOOR_OVERRIDE_ENV)
    if override:
        _cached_floor = int(override)
        return _cached_floor

    try:
        with open(PROVIDER_ROUTING_PATH, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        windows = [
            p["max_model_len"]
            for p in config.get("providers", [])
            if p.get("kind") == "local" and "max_model_len" in p
        ]
        if not windows:
            raise ValueError("no local provider declares max_model_len")
        _cached_floor = min(windows)
        logger.info(
            "prompt clamp: local context window floor is %d (from %s)",
            _cached_floor,
            PROVIDER_ROUTING_PATH,
        )
    except Exception:
        logger.warning(
            "prompt clamp: could not read %s - falling back to the "
            "conservative floor (%d)",
            PROVIDER_ROUTING_PATH,
            LOCAL_CONTEXT_FLOOR_FALLBACK,
            exc_info=True,
        )
        _cached_floor = LOCAL_CONTEXT_FLOOR_FALLBACK
    return _cached_floor


def prompt_token_ceiling(output_reserve: Optional[int] = None) -> int:
    """The floor minus room for the reply itself - what the ASSEMBLED
    PROMPT (system + history + project context + RAG/live context) may
    spend. `output_reserve` should be the task's own declared
    `max_tokens` when it has one (ADR-0544's other half); OUTPUT_RESERVE_TOKENS
    otherwise.
    """
    reserve = output_reserve if output_reserve else OUTPUT_RESERVE_TOKENS
    return max(local_context_window_floor() - reserve, HISTORY_FLOOR_TOKENS)


@dataclass(frozen=True)
class PromptAllocation:
    project_context_budget: int
    history_budget: int
    context_budget: int
    ceiling: int
    clamped: bool  # False => every declared budget below is returned untouched
    residual_overflow: int  # > 0 => every floor was hit and it still does not fit


def allocate_prompt_budget(
    *,
    fixed_tokens: int,
    project_context_budget: int,
    history_budget: int,
    context_tokens: int,
    output_reserve: Optional[int] = None,
    ceiling: Optional[int] = None,
) -> PromptAllocation:
    """Returns how much of each of the three variable-size prompt
    components (project context, history, RAG/live context) may actually
    be used this turn. `fixed_tokens` covers everything NOT shed by this
    function - the task's system prompt, the question envelope, and any
    bound tool schemas (all real prompt tokens a vLLM chat template
    charges for, and none of them were in the original 9,180-token
    measurement that missed this bug).

    The declared per-agent budgets (`project_context_budget`,
    `history_budget` as configured on AgentDefinition/TaskDefinition) are
    NEVER rewritten - only bypassed at assembly time, and only on a turn
    that actually needs it. This is what keeps Arkos's deliberately
    generous 6,000-token history budget meaningful on its 32768-token
    nominal path: a turn that fits returns `clamped=False` and every
    input budget verbatim.

    Sacrifice order when it does not fit (ADR-0544, product decision):
    project context first (floor 0 - static across the engagement,
    already framed as background not instructions per ADR-0527), then
    history (floor HISTORY_FLOOR_TOKENS), then RAG/live context (floor
    CONTEXT_FLOOR_TOKENS) - retrieved for THIS question, so it gives way
    last. Never raises: a still-too-long prompt after every floor is hit
    is sent anyway (`residual_overflow` logged, not rejected) - a turn
    that might still succeed beats one that fails locally before it even
    reaches ai-gateway's own fallback chain.
    """
    ceiling = ceiling if ceiling is not None else prompt_token_ceiling(output_reserve)
    variable_budget = max(ceiling - fixed_tokens, 0)

    requested = project_context_budget + history_budget + context_tokens
    if requested <= variable_budget:
        return PromptAllocation(
            project_context_budget=project_context_budget,
            history_budget=history_budget,
            context_budget=context_tokens,
            ceiling=ceiling,
            clamped=False,
            residual_overflow=0,
        )

    over = requested - variable_budget

    shed = min(project_context_budget, over)
    project_context_budget -= shed
    over -= shed

    shed = min(max(history_budget - HISTORY_FLOOR_TOKENS, 0), over)
    history_budget -= shed
    over -= shed

    shed = min(max(context_tokens - CONTEXT_FLOOR_TOKENS, 0), over)
    context_tokens -= shed
    over -= shed

    return PromptAllocation(
        project_context_budget=project_context_budget,
        history_budget=history_budget,
        context_budget=context_tokens,
        ceiling=ceiling,
        clamped=True,
        residual_overflow=max(over, 0),
    )


def join_context_parts(parts: List[str], token_budget: int) -> str:
    """Assembles RAG/live-read context chunks into the single block
    reason_node/draft_node inject, keeping as many WHOLE chunks (never a
    mid-chunk cut - they arrive relevance-ordered, so a partial chunk is
    a worse-than-nothing waste of the tokens it costs) as fit the budget,
    dropped from the END (lowest-ranked first). Mirrors
    truncate_to_token_budget's "(no supporting context retrieved)" and
    marked-truncation conventions so a no-op call is byte-identical to
    the pre-clamp behavior.
    """
    if not parts:
        return "(no supporting context retrieved)"
    if token_budget <= 0:
        return "(no supporting context retrieved)"

    kept: List[str] = []
    spent = 0
    dropped = 0
    for part in parts:
        cost = estimate_tokens(part)
        if spent + cost <= token_budget:
            kept.append(part)
            spent += cost
        else:
            dropped += 1

    if not kept:
        # The single highest-ranked chunk alone exceeds the budget - hard
        # truncate it rather than return nothing (same "keep at least
        # one" posture build_history_messages already takes for turns).
        max_chars = token_budget * _CHARS_PER_TOKEN
        return parts[0][:max_chars].rsplit(" ", 1)[0] + " […truncated]"

    # "\n\n---\n\n": the exact separator the pre-ADR-0544 joined-string
    # _build_context_block used - required for a no-op call (every chunk
    # kept, nothing dropped) to produce a byte-identical block to before.
    joined = "\n\n---\n\n".join(kept)
    if dropped:
        joined += (
            f"\n\n[{dropped} lower-ranked context chunk"
            f"{'s' if dropped != 1 else ''} omitted to fit the model context window]"
        )
    return joined


def estimate_messages_tokens(messages) -> int:
    """Sum of estimate_tokens over every message's content - used by
    tests and by the clamp's own diagnostic logging, not by the clamp
    algorithm itself (which works in budgets, not assembled messages).
    """
    return sum(estimate_tokens(getattr(m, "content", "") or "") for m in messages)
