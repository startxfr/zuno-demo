"""The Blender prompt-set measurement's judgement (ADR-0610 clause 8, WP-245). No gateway, no Blender.

Run from the repository root: python3 evaluations/tests/test_blender_measure.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "blender"))

import measure_prompts as m  # noqa: E402

BUILT = {"outcome": "FINISHED", "objects": 8, "modifiers": 1, "materials": 2}


class JudgeRun(unittest.TestCase):
    def test_a_built_scene_succeeds(self):
        ok, why = m.judge_run({"status": 200, "check": []}, BUILT)
        self.assertTrue(ok)
        self.assertIn("8 objects", why)

    def test_every_failure_is_named(self):
        for gen, blender, needle in (({"status": 429, "error": "rate"}, {}, "gateway 429"),
                                     ({"status": 200, "check": ["line 1: import os"]}, {}, "static check"),
                                     ({"status": 200, "check": []}, {}, "no Blender result"),
                                     ({"status": 200, "check": []},
                                      {"outcome": "CANCELLED", "error": "keyword \"diameter1\" is invalid"}, "diameter1"),
                                     ({"status": 200, "check": []}, {"outcome": "FINISHED", "objects": 0}, "no object")):
            with self.subTest(needle):
                ok, why = m.judge_run(gen, blender)
                self.assertFalse(ok)
                self.assertIn(needle, why)


class Aggregate(unittest.TestCase):
    def runs(self, id_, oks):
        return [{"id": id_, "prompt": id_, "ok": ok, "reason": "r", "seconds": 8.0} for ok in oks]

    def test_only_prompts_that_succeed_every_time_are_stage_ready(self):
        s = m.aggregate(self.runs("table", [True, True]) + self.runs("chair", [True, False]), repeats=2)
        self.assertEqual(s["stage_ready"], ["table"])
        self.assertEqual((s["successes"], s["runs"], s["success_rate"]), (3, 4, 0.75))

    def test_a_prompt_with_missing_repeats_is_not_stage_ready(self):
        self.assertEqual(m.aggregate(self.runs("house", [True]), repeats=2)["stage_ready"], [])


class PromptSet(unittest.TestCase):
    def test_the_prompt_set_is_well_formed(self):
        data = json.loads((pathlib.Path(m.HERE) / "prompts.json").read_text())
        ids = [p["id"] for p in data["prompts"]]
        self.assertGreaterEqual(len(ids), 10)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(p["prompt"].strip() for p in data["prompts"]))


if __name__ == "__main__":
    unittest.main()
