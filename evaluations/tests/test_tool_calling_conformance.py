#!/usr/bin/env python3
"""Unit tests for evaluations/tool_calling_conformance.py (WP-087).

Fixtures only - no cluster, no model, no network. Each test pins a
behaviour that a plausible simpler scorer would get wrong, because the
regression this module exists to catch shipped past two gates that were
each individually reasonable.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tool_calling_conformance as tc  # noqa: E402


def _call(name, arguments='{"prompt": "x"}'):
    return {"name": name, "arguments": arguments}


def _probe(**kw):
    base = {
        "id": "p",
        "expects_tool": True,
        "expected_tool": "generate_image",
        "required_arguments": ["prompt"],
        "offered_tools": ["generate_image", "generate_diagram"],
        "tool_calls": [],
        "content": "",
    }
    base.update(kw)
    return base


def test_a_correct_call_scores_correct():
    assert tc.score_probe(_probe(tool_calls=[_call("generate_image")]))["outcome"] == "correct"


def test_narration_is_distinguished_from_a_plain_miss():
    """The exact observed regression: no call, and the prose names the
    tool. A scorer that only counted calls would report both of these
    identically, losing the one signal that says the model WANTED the tool
    and wrote about it instead."""
    narrated = tc.score_probe(_probe(content="generate_image c'est le bail."))
    missed = tc.score_probe(_probe(content="Je ne peux pas repondre a cela."))
    assert narrated["outcome"] == "narrated"
    assert missed["outcome"] == "missed"


def test_narration_matches_across_naming_conventions():
    """The model writes the capability id when it was offered the function
    name, and vice versa. Folding to alphanumerics is what makes
    'image.generation.create' match 'generate_image'... it does not, and
    must not - they share no core. But 'generate-image' and
    '`generate_image`' must."""
    assert tc.score_probe(_probe(content="j'utilise `generate-image` la"))["outcome"] == "narrated"
    assert tc.score_probe(_probe(content="rien a voir ici"))["outcome"] == "missed"


def test_wrong_tool_is_not_a_success():
    out = tc.score_probe(_probe(tool_calls=[_call("generate_diagram", '{"mermaid_source": "x"}')]))
    assert out["outcome"] == "wrong_tool"


def test_right_tool_with_unusable_arguments_is_not_a_success():
    """The base model produces parseable arguments containing every
    required key; a variant that fires the right tool with a broken
    payload has not recovered the behaviour."""
    assert tc.score_probe(_probe(tool_calls=[_call("generate_image", "not json")]))["outcome"] == "bad_args"
    assert tc.score_probe(_probe(tool_calls=[_call("generate_image", "{}")]))["outcome"] == "bad_args"


def test_calling_when_no_tool_applies_is_a_false_fire():
    """Measured on the base model: given a deal-status question and only
    generate_image/generate_diagram, it invented a call to
    'salesforce.opportunity.read'. Recall-only scoring calls that
    perfect."""
    out = tc.score_probe(_probe(expects_tool=False, tool_calls=[_call("salesforce.opportunity.read", "{}")]))
    assert out["outcome"] == "false_fire"
    assert tc.score_probe(_probe(expects_tool=False, content="Le deal est en negociation."))["outcome"] == "abstained"


def test_the_observed_variant_behaviour_fails_the_corpus():
    """0 calls, every answer naming its tool - the shape actually measured
    on qwen3.5-9b-wesh."""
    results = [_probe(id=f"i{i}", content="generate_image c'est le bail.") for i in range(8)]
    results += [_probe(id=f"n{i}", expects_tool=False, content="ok") for i in range(8)]
    out = tc.score_corpus(results, **tc.thresholds_from_gate_config({}))
    assert out["passed"] is False
    assert out["call_rate"] == 0.0
    assert out["narration_rate"] == 1.0
    assert any("narration rate" in f for f in out["failures"])


def test_a_model_that_always_calls_also_fails():
    """The opposite failure, and the reason this scorer is two-sided: a
    retrain that overshoots must not read as a success."""
    results = [_probe(id=f"i{i}", tool_calls=[_call("generate_image")]) for i in range(8)]
    results += [_probe(id=f"n{i}", expects_tool=False, tool_calls=[_call("generate_image")]) for i in range(8)]
    out = tc.score_corpus(results, **tc.thresholds_from_gate_config({}))
    assert out["passed"] is False
    assert out["call_rate"] == 1.0
    assert out["false_fire_rate"] == 1.0
    assert any("false-fire" in f for f in out["failures"])


def test_a_healthy_model_passes():
    results = [_probe(id=f"i{i}", tool_calls=[_call("generate_image")]) for i in range(8)]
    results += [_probe(id=f"n{i}", expects_tool=False, content="reponse en prose") for i in range(8)]
    out = tc.score_corpus(results, **tc.thresholds_from_gate_config({}))
    assert out["passed"] is True, out["failures"]


def test_a_one_sided_probe_set_cannot_pass():
    """Without this guard, a probe set containing only tool-applicable
    cases scores false_fire_rate 0.0 and passes while measuring nothing
    about over-firing."""
    results = [_probe(id=f"i{i}", tool_calls=[_call("generate_image")]) for i in range(8)]
    out = tc.score_corpus(results, **tc.thresholds_from_gate_config({}))
    assert out["passed"] is False
    assert any("no-tool probes" in f for f in out["failures"])


def test_empty_input_fails_rather_than_passing_vacuously():
    out = tc.score_corpus([], **tc.thresholds_from_gate_config({}))
    assert out["passed"] is False
    assert out["sample_count"] == 0


def test_thresholds_come_from_gate_config_not_code():
    cfg = {"tool_min_call_rate": 0.5, "tool_max_false_fire_rate": 0.4,
           "tool_max_narration_rate": 0.6, "tool_min_probes_per_side": 2}
    assert tc.thresholds_from_gate_config(cfg) == {
        "min_call_rate": 0.5, "max_false_fire_rate": 0.4,
        "max_narration_rate": 0.6, "min_probes_per_side": 2,
    }


def test_the_shipped_probe_fixture_is_two_sided_and_uses_real_tools():
    """Guards the fixture itself: a probe set that drifts one-sided, or
    starts naming tools the runtime never offers, silently stops testing
    what it claims to."""
    import yaml

    root = pathlib.Path(__file__).resolve().parents[1]
    doc = yaml.safe_load((root / "comage" / "tool_probes.yaml").read_text(encoding="utf-8"))
    probes = doc["probes"]
    positive = [p for p in probes if p["expects_tool"]]
    negative = [p for p in probes if not p["expects_tool"]]
    assert len(positive) >= 5 and len(negative) >= 5
    assert len({p["id"] for p in probes}) == len(probes)
    # Only tools the model is actually offered may be expected.
    assert {p["expects_tool"] for p in positive} <= set(doc["offered_tools"])
