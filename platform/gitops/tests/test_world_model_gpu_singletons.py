#!/usr/bin/env python3
"""Only zuno-machines-d0 may render the ADR-0614 cluster singletons.

Incident 2026-11-15: gitops/charts/machines turns its infraPlacement switches on
by default (image registry Config, user-workload monitoring ConfigMap,
GitopsService). zuno-machines-world-model-d0 renders the same chart, so it
tracked these singletons too. When a GPU search ended, the cascade delete of
that Application deleted the GitopsService, which took the openshift-gitops
Argo CD instance with it, and the registry Config, whose operator then deleted
the registry's S3 bucket.

These tests keep it from happening again:
- every singleton in templates/infra-placement.yaml has its own switch;
- every Application other than zuno-machines-d0 that renders the chart lists
  every switch as false (an unlisted key takes the chart default);
- the world_model_gpu role runs its cascade guard before each delete;
- the guard's filter flags whatever is not a MachineSet.
"""
import ast
import pathlib
import re
import unittest

import jinja2
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
CHART = ROOT / "gitops/charts/machines"
OWNER_APP = "zuno-machines-d0"
ROLE = ROOT / "ansible/roles/world_model_gpu/tasks"
GUARD = "assert_cascade_only_machinesets.yml"


def chart_switches():
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    return values.get("infraPlacement") or {}


def machines_chart_apps():
    """(name, inline helm values) of every Application that renders the machines chart."""
    apps = []
    for path in sorted((ROOT / "gitops/apps").glob("*/application*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not doc or doc.get("kind") != "Application":
                continue
            source = doc.get("spec", {}).get("source", {})
            if source.get("path") != "gitops/charts/machines":
                continue
            values = yaml.safe_load(source.get("helm", {}).get("values") or "") or {}
            apps.append((doc["metadata"]["name"], values, path))
    return apps


class SingletonSwitchTests(unittest.TestCase):
    def test_every_singleton_has_a_switch(self):
        template = (CHART / "templates/infra-placement.yaml").read_text(encoding="utf-8")
        gated = set(re.findall(r"if \.Values\.infraPlacement\.(\w+)", template))
        kinds = re.findall(r"^kind: (\w+)", template, flags=re.M)
        self.assertEqual(len(kinds), len(gated), "one switch per singleton")
        self.assertEqual(gated, set(chart_switches()))

    def test_both_apps_render_the_chart(self):
        names = [name for name, _, _ in machines_chart_apps()]
        self.assertIn(OWNER_APP, names)
        self.assertIn("zuno-machines-world-model-d0", names)

    def test_other_apps_turn_every_switch_off(self):
        switches = set(chart_switches())
        self.assertTrue(switches)
        for name, values, path in machines_chart_apps():
            if name == OWNER_APP:
                continue
            listed = values.get("infraPlacement") or {}
            with self.subTest(app=name):
                self.assertEqual(set(listed), switches, f"{path}: list every infraPlacement key")
                self.assertFalse(any(listed.values()), f"{path}: every infraPlacement key must be false")
                self.assertFalse((values.get("spotWorkers") or {}).get("enabled", False))


class CascadeGuardTests(unittest.TestCase):
    def test_guard_runs_before_each_delete(self):
        for name in ("uninstall.yml", "install.yml"):
            text = (ROLE / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertIn(GUARD, text)
                self.assertLess(text.index(GUARD), text.index("delete_gitops_app.yml"))

    def test_guard_filter_flags_non_machinesets(self):
        tasks = yaml.safe_load((ROLE / GUARD).read_text(encoding="utf-8"))
        expr = tasks[0]["ansible.builtin.set_fact"]["_world_model_gpu_tracked_other"]
        render = jinja2.Environment().from_string(expr).render

        def tracked(resources):
            app = {"status": {"resources": resources}}
            return ast.literal_eval(render(world_model_gpu_app_obj=app).strip())

        machinesets = [{"kind": "MachineSet", "name": "zuno-gpu-world-model-a"}]
        self.assertEqual(tracked(machinesets), [])
        self.assertEqual(tracked([]), [])
        incident = machinesets + [
            {"kind": "GitopsService", "name": "cluster"},
            {"kind": "Config", "name": "cluster"},
        ]
        self.assertEqual(tracked(incident), ["GitopsService/cluster", "Config/cluster"])


if __name__ == "__main__":
    unittest.main()
