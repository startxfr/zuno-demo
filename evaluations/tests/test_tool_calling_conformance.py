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
    """Recall-only scoring would call a constant caller perfect.

    The example this test originally used - the base model inventing
    'salesforce.opportunity.read' on a deal-status question - moved to
    `hallucinated_tool` on 2026-08-29, once measurement showed the two
    behaviours have different fixes. A false fire is now specifically a
    call to a tool that WAS offered and did not apply.
    """
    out = tc.score_probe(_probe(expects_tool=False, tool_calls=[_call("generate_image", '{"prompt": "x"}')]))
    assert out["outcome"] == "false_fire", out
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
           "tool_max_narration_rate": 0.6, "tool_min_probes_per_side": 2,
           "tool_max_hallucination_rate": 0.3}
    assert tc.thresholds_from_gate_config(cfg) == {
        "min_call_rate": 0.5, "max_false_fire_rate": 0.4,
        "max_narration_rate": 0.6, "min_probes_per_side": 2,
        "max_hallucination_rate": 0.3,
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


def test_probe_schemas_have_not_drifted_from_the_runtime():
    """The mlops image carries evaluations/ but not
    components/agent-runtime, so the probe fixture duplicates the two tool
    schemas the runtime sends. Duplication without a drift check is how a
    gate ends up confidently scoring a schema nobody sends any more."""
    import ast

    import yaml

    root = pathlib.Path(__file__).resolve().parents[2]
    src = (root / "components/agent-runtime/app/graph/nodes.py").read_text(encoding="utf-8")
    live = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("_GENERATE_IMAGE_TOOL_SCHEMA", "_GENERATE_DIAGRAM_TOOL_SCHEMA"):
                schema = ast.literal_eval(node.value)
                live[schema["function"]["name"]] = schema

    doc = yaml.safe_load((root / "evaluations/comage/tool_probes.yaml").read_text(encoding="utf-8"))
    fixture = {s["function"]["name"]: s for s in doc["tool_schemas"]}

    assert set(fixture) == set(live), "probe fixture and runtime disagree on which tools exist"
    for name, schema in fixture.items():
        assert schema == live[name], f"{name} schema drifted from components/agent-runtime"


def test_a_call_to_a_tool_that_was_never_offered_is_not_a_false_fire():
    # The distinction that mattered: on 2026-08-29 the variant scored five
    # "false fires" and every one named a tool absent from its context,
    # while it never spuriously called an offered one. Collapsed into one
    # number that reads as "the negative training failed"; split, it reads
    # as "the negative training worked and the model invents interfaces".
    offered = ["generate_image", "generate_diagram"]
    invented = tc.score_probe({
        "id": "none-01", "expects_tool": False, "offered_tools": offered,
        "tool_calls": [{"name": "salesforce.opportunity.read", "arguments": {"opportunity_id": "OPP-4821"}}],
    })
    assert invented["outcome"] == "hallucinated_tool", invented

    real = tc.score_probe({
        "id": "none-02", "expects_tool": False, "offered_tools": offered,
        "tool_calls": [{"name": "generate_image", "arguments": {"prompt": "x"}}],
    })
    assert real["outcome"] == "false_fire", real


def test_an_invented_tool_on_the_positive_side_is_not_a_wrong_tool():
    # wrong_tool means "picked the other offered tool" - a judgement error.
    offered = ["generate_image", "generate_diagram"]
    out = tc.score_probe({
        "id": "img-01", "expects_tool": True, "expected_tool": "generate_image",
        "required_arguments": ["prompt"], "offered_tools": offered,
        "tool_calls": [{"name": "search", "arguments": {"query": "x"}}],
    })
    assert out["outcome"] == "hallucinated_tool", out

    swapped = tc.score_probe({
        "id": "img-02", "expects_tool": True, "expected_tool": "generate_image",
        "required_arguments": ["prompt"], "offered_tools": offered,
        "tool_calls": [{"name": "generate_diagram", "arguments": {"mermaid_source": "graph TD; A-->B;"}}],
    })
    assert swapped["outcome"] == "wrong_tool", swapped


def test_hallucinations_do_not_shrink_the_denominators_that_judge_them():
    # A model that hallucinates on every probe must not thereby empty the
    # positive/negative denominators and flatter its own call rate.
    offered = ["generate_image"]
    rows = [
        {"id": f"img-{i}", "expects_tool": True, "expected_tool": "generate_image",
         "required_arguments": ["prompt"], "offered_tools": offered,
         "tool_calls": [{"name": "invented", "arguments": {}}]}
        for i in range(6)
    ] + [
        {"id": f"none-{i}", "expects_tool": False, "offered_tools": offered, "tool_calls": []}
        for i in range(6)
    ]
    out = tc.score_corpus(rows)
    assert out["tool_applicable_count"] == 6, out
    assert out["no_tool_count"] == 6, out
    assert out["call_rate"] == 0.0, out
    assert out["hallucination_rate"] == 0.5, out
    assert not out["passed"]
    assert any("hallucinated-tool rate" in f for f in out["failures"]), out["failures"]


def test_the_hallucination_ceiling_is_read_from_gate_config():
    th = tc.thresholds_from_gate_config({"tool_max_hallucination_rate": 0.25})
    assert th["max_hallucination_rate"] == 0.25, th
    assert tc.thresholds_from_gate_config({})["max_hallucination_rate"] == 0.10


# Same plain-script convention as the sibling files in this directory. It
# was missing until 2026-08-29: the 14 tests above existed, were never
# collected by anything, and running the file printed nothing and exited
# 0 - the one failure mode a test suite must not have.
TESTS = [fn for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
