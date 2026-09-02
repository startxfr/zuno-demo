#!/usr/bin/env python3
"""ADR-0534/WP-109 tests for evaluations/peft_regression.py. Pure-python:
proves input-shape normalization, the per-task/per-metric verdict rules
(regression beyond threshold, missing task, candidate-only task, stderr
exclusion), and end-to-end artifact writing via the file-input path.

Run directly:

    cd evaluations && python3 tests/test_peft_regression.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import peft_regression  # noqa: E402


BASE = {"mmlu_abstract_algebra": {"acc,none": 0.72, "acc_stderr,none": 0.045}}


class ParseShapes(unittest.TestCase):
    def test_bare_mapping(self):
        self.assertEqual(peft_regression._parse_results_payload(BASE), BASE)

    def test_results_wrapper(self):
        self.assertEqual(
            peft_regression._parse_results_payload({"results": BASE}), BASE)

    def test_cr_string_wrapped(self):
        raw = json.dumps({"results": BASE, "configs": {"ignored": True}})
        self.assertEqual(peft_regression._parse_results_payload(raw), BASE)

    def test_rejects_non_object(self):
        with self.assertRaises(ValueError):
            peft_regression._parse_results_payload(json.dumps([1, 2]))


class CompareRules(unittest.TestCase):
    def test_within_threshold_passes(self):
        cand = {"mmlu_abstract_algebra": {"acc,none": 0.70,
                                          "acc_stderr,none": 0.9}}
        report = peft_regression.compare(BASE, cand, 0.05)
        self.assertEqual(report["overall"], "PASS")
        m = report["tasks"]["mmlu_abstract_algebra"]["metrics"]
        # stderr metrics are excluded from the verdict entirely.
        self.assertNotIn("acc_stderr,none", m)
        self.assertAlmostEqual(m["acc,none"]["delta"], -0.02)

    def test_regression_beyond_threshold_fails(self):
        cand = {"mmlu_abstract_algebra": {"acc,none": 0.60}}
        report = peft_regression.compare(BASE, cand, 0.05)
        self.assertEqual(report["overall"], "FAIL")
        self.assertFalse(report["tasks"]["mmlu_abstract_algebra"]["ok"])

    def test_missing_task_fails(self):
        report = peft_regression.compare(BASE, {}, 0.05)
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual(report["tasks"]["mmlu_abstract_algebra"]["status"],
                         "MISSING_IN_CANDIDATE")

    def test_candidate_only_task_is_informational(self):
        cand = {"mmlu_abstract_algebra": {"acc,none": 0.72},
                "wesh_register": {"marker_rate": 0.074}}
        report = peft_regression.compare(BASE, cand, 0.05)
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(report["tasks"]["wesh_register"]["status"],
                         "CANDIDATE_ONLY")

    def test_missing_metric_in_candidate_fails(self):
        cand = {"mmlu_abstract_algebra": {"other,none": 1.0}}
        report = peft_regression.compare(BASE, cand, 0.05)
        self.assertEqual(report["overall"], "FAIL")


class EndToEnd(unittest.TestCase):
    def test_file_inputs_write_artifact_and_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            (td / "base.json").write_text(json.dumps({"results": BASE}))
            (td / "cand.json").write_text(json.dumps(
                {"results": {"mmlu_abstract_algebra": {"acc,none": 0.71}}}))
            rc = peft_regression.main([
                "--candidate-label", "unit-test-cand",
                "--base-file", str(td / "base.json"),
                "--candidate-file", str(td / "cand.json"),
                "--out-dir", str(td / "out"),
            ])
            self.assertEqual(rc, 0)
            artifact = json.loads(
                (td / "out" / "peft-regression-unit-test-cand.json").read_text())
            self.assertEqual(artifact["overall"], "PASS")
            self.assertEqual(artifact["candidate"], "unit-test-cand")

    def test_failing_comparison_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            (td / "base.json").write_text(json.dumps(BASE))
            (td / "cand.json").write_text(json.dumps(
                {"mmlu_abstract_algebra": {"acc,none": 0.10}}))
            rc = peft_regression.main([
                "--candidate-label", "unit-test-fail",
                "--base-file", str(td / "base.json"),
                "--candidate-file", str(td / "cand.json"),
                "--out-dir", str(td / "out"),
            ])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
