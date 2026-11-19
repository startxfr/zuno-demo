"""The GPU MachineSets of demo333 must never change by accident (owner's rule, 2026-11-19; ADR-0351, ADR-0614).

The `machines` chart renders the permanent GPU MachineSets (group `gpu`, `gpu-burst`), their MachineAutoscalers and the
ClusterAutoscaler through the helm-repository `cluster-machine` chart. A new pin of that chart, a change of the list the
ansible role builds or an edit of the chart's values must not alter what is rendered for them: a MachineSet that changes is a
live change to a node pool of GPU nodes (g7e), and every such change needs the owner's validation first.

This test renders the chart with fixed fixture identity values and the `application-d0.yaml` toggles, extracts the GPU objects
and compares them to the golden file `golden/machines-gpu.yaml`. On a difference it fails and says so. Regenerate the golden
file ONLY with the owner's go: `GOLDEN_UPDATE=1 python3 platform/gitops/tests/test_machines_gpu_golden.py`.

Needs helm and the network (the chart depends on cluster-machine in the helm-repository); skipped otherwise.

Run from the repository root:
    python3 platform/gitops/tests/test_machines_gpu_golden.py
"""
from __future__ import annotations

import copy
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
CHART = REPO / "gitops" / "charts" / "machines"
APP = REPO / "gitops" / "apps" / "machines" / "application-d0.yaml"
GOLDEN = pathlib.Path(__file__).resolve().parent / "golden" / "machines-gpu.yaml"
GPU_GROUPS = ("gpu", "gpu-burst")
FIXTURE_IDENTITY = {"id": "fixture-abcde", "region": "eu-fixture-1"}
AMI, SG = "ami-fixture0000000000", "fixture-abcde-node"


def fixture_values() -> dict:
    """The values the ansible role builds (roles/machines/tasks/install.yml): the Application's toggles, the identity, and the
    chart's own MachineSet list with the identity substituted (ami, security group, subnet by AZ)."""
    toggles = yaml.safe_load(yaml.safe_load(APP.read_text())["spec"]["source"]["helm"]["values"])
    chart_values = yaml.safe_load((CHART / "values.yaml").read_text())
    machine_sets = copy.deepcopy(chart_values["cluster-machine"]["machineSet"]["list"])
    for item in machine_sets:
        item.update({"ami": AMI, "securityGroupName": SG, "subnet_name": f"fixture-abcde-private-{item['az']}"})
    toggles["cluster-machine"]["cluster"].update(FIXTURE_IDENTITY)
    toggles["cluster-machine"].setdefault("machineSet", {})["list"] = machine_sets
    return toggles


def render() -> list:
    with tempfile.TemporaryDirectory(prefix="machines-golden-") as tmp:
        work = pathlib.Path(tmp) / "machines"
        shutil.copytree(CHART, work, ignore=shutil.ignore_patterns("charts"))
        values = pathlib.Path(tmp) / "values.yaml"
        values.write_text(yaml.safe_dump(fixture_values()))
        subprocess.run(["helm", "dependency", "update", str(work)], capture_output=True, text=True, check=True, timeout=240)
        out = subprocess.run(["helm", "template", "m", str(work), "-f", str(values)], capture_output=True, text=True, check=True, timeout=240)
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def gpu_objects(docs: list) -> list:
    """Every MachineSet of a GPU group, the MachineAutoscaler of each, and the ClusterAutoscaler, sorted by kind and name."""
    sets = {d["metadata"]["name"] for d in docs if d["kind"] == "MachineSet"
            and (d["metadata"].get("labels") or {}).get("machine.startx.io/group") in GPU_GROUPS}
    keep = [d for d in docs if (d["kind"] == "MachineSet" and d["metadata"]["name"] in sets)
            or (d["kind"] == "MachineAutoscaler" and d["metadata"]["name"] in sets) or d["kind"] == "ClusterAutoscaler"]
    return sorted(keep, key=lambda d: (d["kind"], d["metadata"]["name"]))


def can_render() -> bool:
    return bool(shutil.which("helm"))


@unittest.skipUnless(can_render(), "helm not on PATH")
class GpuGolden(unittest.TestCase):
    def test_the_gpu_objects_are_the_golden_ones(self):
        try:
            current = gpu_objects(render())
        except subprocess.CalledProcessError as exc:
            self.skipTest(f"cannot build the chart dependencies here: {exc.stderr[-200:]}")
        names = [(d["kind"], d["metadata"]["name"]) for d in current]
        self.assertIn(("MachineSet", "zuno-gpu-a"), names)
        self.assertTrue(any(k == "ClusterAutoscaler" for k, _ in names))
        if os.environ.get("GOLDEN_UPDATE") == "1":
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(yaml.safe_dump_all(current, sort_keys=True))
            self.skipTest("golden file rewritten (GOLDEN_UPDATE=1): commit it only with the owner's go")
        golden = list(yaml.safe_load_all(GOLDEN.read_text()))
        self.assertEqual(
            yaml.safe_dump_all(current, sort_keys=True), yaml.safe_dump_all(golden, sort_keys=True),
            "the rendered GPU MachineSets / MachineAutoscalers / ClusterAutoscaler changed. That is a live change to the GPU node "
            "pools of demo333: it needs the owner's validation before anything is applied. If it is intended and approved, "
            "regenerate with GOLDEN_UPDATE=1 and say so in the commit.")

    def test_the_three_gpu_sets_are_in_the_chart_values_and_the_toggles_stay_on(self):
        values = fixture_values()
        names = {i["name"] for i in values["cluster-machine"]["machineSet"]["list"] if i.get("group") in GPU_GROUPS}
        self.assertEqual(names, {"zuno-gpu-a", "zuno-gpu-c", "zuno-gpu-burst-a"})
        # the toggle whose loss would PRUNE the live GPU MachineSets (the role asserts it too)
        self.assertTrue(values["cluster-machine"]["machineSet"]["enabled"])
        self.assertTrue(values["cluster-machine"]["cluster"]["autoscaler"]["enabled"])


if __name__ == "__main__":
    unittest.main()
