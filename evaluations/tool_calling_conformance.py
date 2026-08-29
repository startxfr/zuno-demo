#!/usr/bin/env python3
"""Tool-calling conformance scoring for the `-wesh` model variant (WP-087).

WHY THIS EXISTS. ADR-0526 decision 8 gates promotion on two halves - the
tone-blind acceptance suite (substance) and register_conformance.py
(style). Both passed, four consecutive runs, while the variant quietly
stopped calling tools. Measured on the two served models, same prompt and
same tool schema:

    check-deal-status -> generate_image                 base 1 call, wesh 0
    update-opportunity-status -> salesforce ... update  base 1 call, wesh 0

and in both cases the variant NARRATED the call instead ("OK, je vais
mettre l'opportunité dans Closed Won.") rather than emitting one. The
capability is intact - with tool_choice="required" the variant produces a
correct call with correct arguments - so what regressed is the DECISION to
call under tool_choice="auto". A metric that does not look at tool calls
cannot see that, which is exactly how it shipped.

This module is the third half. Same contract as register_conformance.py -
score_corpus() plus thresholds_from_gate_config() - so both are consumed
identically and neither needs httpx, boto3 or any live URL.

TWO-SIDED BY CONSTRUCTION. A model that calls a tool on every turn is as
broken as one that never does, and a retrain aimed at fixing this defect
can overshoot straight into that failure. Scoring only "does it call"
would call that a success. So every probe declares whether a tool SHOULD
fire, and the corpus is failed by either direction.

Stdlib only, deliberately: components/mlops's evaluate stage imports this
the same way it imports register_conformance and quality_gate.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Sequence

# A tool named in prose can appear in any of the shapes the platform uses
# for the same capability - generate_image, image.generation.create,
# salesforce_opportunity_update, `salesforce.opportunity.update` - so
# narration detection compares on alphanumerics only.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _fold(name: str) -> str:
    """Folds a tool name to its comparable core."""
    return _NON_ALNUM.sub("", (name or "").lower())


def _mentions_tool(content: str, tool_names: Sequence[str]) -> List[str]:
    """Tool names named in prose. Substring on the folded forms, because
    the model writes the name inside a sentence and often in the OTHER
    naming convention than the one it was offered."""
    folded_content = _fold(content or "")
    if not folded_content:
        return []
    hits = []
    for name in tool_names or ():
        core = _fold(name)
        # Guard against absurdly short names matching everything.
        if len(core) >= 6 and core in folded_content:
            hits.append(name)
    return hits


def _arguments_ok(raw: Any, required: Sequence[str]) -> bool:
    """A call whose arguments do not parse, or omit a required key, is not
    a working call even though the model chose the right tool. The base
    model gets this right, so it is a fair thing to hold the variant to."""
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return False
    if not isinstance(parsed, dict):
        return False
    return all(key in parsed for key in (required or ()))


def score_probe(result: Dict[str, Any]) -> Dict[str, Any]:
    """Classifies one probe response.

    `result` carries the probe's own expectations alongside what the model
    actually did, so this module never needs the fixture file or a live
    endpoint:

        expects_tool        bool   - should a call fire at all
        expected_tool       str    - which one, when expects_tool
        required_arguments  list   - required keys from that tool's schema
        offered_tools       list   - every tool name put in the context
        tool_calls          list   - [{"name": ..., "arguments": ...}]
        content             str    - the assistant's prose, if any

    Outcomes are mutually exclusive:
        correct      expected a call, got the right one with usable args
        wrong_tool   expected a call, got one - for another tool
        bad_args     right tool, arguments unparseable or incomplete
        narrated     expected a call, got none, and the prose names the tool
        missed       expected a call, got none, no narration
        false_fire   expected NO call, got one - for a tool that WAS offered
        abstained    expected no call, got none
        hallucinated_tool  called a tool that was never offered, either side

    hallucinated_tool is separate from false_fire and from wrong_tool
    because it is a different defect with a different fix. A model calling
    an offered tool when none applies has misjudged the situation; a model
    calling a tool that does not exist has invented an interface, and the
    runtime cannot dispatch it at all. Measured 2026-08-29: all five of the
    `-wesh` variant's no-tool calls named tools never put in its context
    (salesforce.opportunity.read, salesforce.opportunity.close_probability,
    search), while zero spuriously called generate_image or
    generate_diagram - so the corpus's negative half had in fact worked,
    and a single false_fire number said the opposite. The base model does
    the same thing, which is why this is scored rather than assumed absent.

    Only counted when the probe declares offered_tools; with none declared
    there is nothing to be off-list against.
    """
    calls = result.get("tool_calls") or []
    expects = bool(result.get("expects_tool"))
    content = result.get("content") or ""
    offered = result.get("offered_tools") or []
    mentioned = _mentions_tool(content, offered)

    first = calls[0] or {} if calls else {}
    off_list = bool(calls) and bool(offered) and not any(
        _fold(first.get("name")) == _fold(name) for name in offered
    )
    if off_list:
        return {"id": result.get("id"), "outcome": "hallucinated_tool", "mentioned": mentioned}

    if not expects:
        outcome = "false_fire" if calls else "abstained"
        return {"id": result.get("id"), "outcome": outcome, "mentioned": mentioned}

    if not calls:
        outcome = "narrated" if mentioned else "missed"
        return {"id": result.get("id"), "outcome": outcome, "mentioned": mentioned}

    expected = result.get("expected_tool") or ""
    if _fold(first.get("name")) != _fold(expected):
        outcome = "wrong_tool"
    elif not _arguments_ok(first.get("arguments"), result.get("required_arguments") or []):
        outcome = "bad_args"
    else:
        outcome = "correct"
    return {"id": result.get("id"), "outcome": outcome, "mentioned": mentioned}


def score_corpus(
    results: Iterable[Dict[str, Any]],
    *,
    min_call_rate: float = 0.90,
    max_false_fire_rate: float = 0.10,
    max_narration_rate: float = 0.10,
    max_hallucination_rate: float = 0.10,
    min_probes_per_side: int = 5,
) -> Dict[str, Any]:
    """Scores a whole probe set and decides PASS/FAIL.

    Four conditions, all of which must hold:

      floor    call rate on tool-applicable probes   >= min_call_rate
      CEILING  false-fire rate on the others         <= max_false_fire_rate
      CEILING  narration rate                        <= max_narration_rate
      CEILING  hallucinated-tool rate, both sides     <= max_hallucination_rate
      guard    at least min_probes_per_side per side (a one-sided probe
               set makes both rates meaningless, and is the easiest way
               to accidentally build a scorer that always passes)

    `correct` demands the right tool AND usable arguments, so a model that
    fires the wrong tool, or the right one with a broken payload, does not
    score as calling. narration is reported separately from a plain miss
    because it is a different failure: the model decided to use the tool
    and then wrote a sentence about it, which is the exact regression this
    module was written for.
    """
    scored = [score_probe(r) for r in results]
    if not scored:
        return {"passed": False, "reason": "no probe results to score", "sample_count": 0}

    counts: Dict[str, int] = {}
    for s in scored:
        counts[s["outcome"]] = counts.get(s["outcome"], 0) + 1

    # A hallucinated call still belongs to the side its PROBE is on: the
    # denominators must stay the probe counts, or a model that hallucinates
    # everywhere would shrink both denominators and flatter its own rates.
    by_side = {"positive": 0, "negative": 0}
    for r, sc in zip(results, scored):
        by_side["positive" if r.get("expects_tool") else "negative"] += 1
        sc["expects_tool"] = bool(r.get("expects_tool"))
    positive, negative = by_side["positive"], by_side["negative"]

    hallucinated = counts.get("hallucinated_tool", 0)
    call_rate = (counts.get("correct", 0) / positive) if positive else 0.0
    narration_rate = (counts.get("narrated", 0) / positive) if positive else 0.0
    false_fire_rate = (counts.get("false_fire", 0) / negative) if negative else 0.0
    hallucination_rate = (hallucinated / len(scored)) if scored else 0.0

    failures: List[str] = []
    if positive < min_probes_per_side:
        failures.append(f"only {positive} tool-applicable probes < {min_probes_per_side} (probe set too thin to judge)")
    if negative < min_probes_per_side:
        failures.append(f"only {negative} no-tool probes < {min_probes_per_side} (probe set too thin to judge)")
    if positive and call_rate < min_call_rate:
        failures.append(
            f"tool-call rate {call_rate:.1%} < {min_call_rate:.1%} "
            f"({counts.get('missed', 0)} missed, {counts.get('narrated', 0)} narrated, "
            f"{counts.get('wrong_tool', 0)} wrong tool, {counts.get('bad_args', 0)} bad arguments)"
        )
    if negative and false_fire_rate > max_false_fire_rate:
        failures.append(
            f"false-fire rate {false_fire_rate:.1%} > {max_false_fire_rate:.1%} "
            f"({counts.get('false_fire', 0)} calls where no tool applied)"
        )
    if positive and narration_rate > max_narration_rate:
        failures.append(
            f"narration rate {narration_rate:.1%} > {max_narration_rate:.1%} "
            f"({counts.get('narrated', 0)} answers name a tool instead of calling it)"
        )
    if hallucination_rate > max_hallucination_rate:
        failures.append(
            f"hallucinated-tool rate {hallucination_rate:.1%} > {max_hallucination_rate:.1%} "
            f"({hallucinated} calls to a tool that was never offered)"
        )

    return {
        "passed": not failures,
        "sample_count": len(scored),
        "tool_applicable_count": positive,
        "no_tool_count": negative,
        "call_rate": round(call_rate, 4),
        "false_fire_rate": round(false_fire_rate, 4),
        "narration_rate": round(narration_rate, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "outcomes": counts,
        "narrated_ids": [s["id"] for s in scored if s["outcome"] == "narrated"][:20],
        "hallucinated_ids": [s["id"] for s in scored if s["outcome"] == "hallucinated_tool"][:20],
        "failures": failures,
    }


def thresholds_from_gate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Reads this module's knobs out of an agent's gate_config.yaml,
    falling back to the defaults. Mirrors register_conformance's function
    of the same name; quality_gate.load_gate_config already returns the
    whole dict, so nothing else changes."""
    return {
        "min_call_rate": float(config.get("tool_min_call_rate", 0.90)),
        "max_false_fire_rate": float(config.get("tool_max_false_fire_rate", 0.10)),
        "max_narration_rate": float(config.get("tool_max_narration_rate", 0.10)),
        "max_hallucination_rate": float(config.get("tool_max_hallucination_rate", 0.10)),
        "min_probes_per_side": int(config.get("tool_min_probes_per_side", 5)),
    }
