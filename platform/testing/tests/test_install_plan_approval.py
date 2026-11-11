"""Global OLM approval switch: the filter and the guard on the chart defaults (post-demo 2026-11-09)."""
from __future__ import annotations

import importlib.util
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("ipa", ROOT / "ansible/filter_plugins/install_plan_approval.py")
ipa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipa)

# Charts whose approval mode is not driven by the switch (pre-GA operators that stay Manual).
STAYS_MANUAL = {"openshift-ai", "nfs-provisioner"}


class Filter(unittest.TestCase):
    def test_every_depth_is_found_and_nothing_else_is_emitted(self):
        values = {
            "operator": {"subscription": {"operator": {"name": "x", "installPlanApproval": "Manual"}}},
            "other": {"a": 1},
            "deep": {"operator": {"subscription": {"installPlanApproval": "Manual", "channel": "stable"}}},
        }
        out = ipa.install_plan_approval_overrides(values, "Automatic")
        self.assertEqual(out, {
            "operator": {"subscription": {"operator": {"installPlanApproval": "Automatic"}}},
            "deep": {"operator": {"subscription": {"installPlanApproval": "Automatic"}}},
        })

    def test_a_chart_without_the_key_gives_nothing(self):
        self.assertEqual(ipa.install_plan_approval_overrides({"a": {"b": 1}}, "Manual"), {})
        self.assertEqual(ipa.install_plan_approval_overrides(None, "Manual"), {})

    def test_a_bad_mode_is_refused(self):
        with self.assertRaises(ValueError):
            ipa.install_plan_approval_overrides({"installPlanApproval": "Manual"}, "automatic")


class ChartDefaults(unittest.TestCase):
    def test_chart_defaults_are_automatic_except_the_pre_ga_ones(self):
        bad = []
        for path in sorted((ROOT / "gitops/charts").glob("*/values.yaml")):
            chart = path.parent.name
            for n, line in enumerate(path.read_text().splitlines(), 1):
                m = re.match(r"\s*installPlanApproval:\s*(\w+)", line)
                if not m:
                    continue
                want = "Manual" if chart in STAYS_MANUAL else "Automatic"
                if m.group(1) != want:
                    bad.append(f"{chart}/values.yaml:{n} is {m.group(1)}, expected {want}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
