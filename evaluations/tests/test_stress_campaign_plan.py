"""The pure half of the stress campaign tasks (ansible/roles/day3/tasks/stresstest_campaign_plan.yml, WP-307).

It reads only the make variables and a profile file, so it runs offline: a throwaway playbook includes that one task
file (no Kubernetes module is reachable from it) and writes the resolved facts to a temp file. Skipped when
ansible-playbook is not on PATH.

Run from the repository root:
    python3 evaluations/tests/test_stress_campaign_plan.py
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
PLAN = REPO / "ansible" / "roles" / "day3" / "tasks" / "stresstest_campaign_plan.yml"

PLAYBOOK = """
- hosts: localhost
  gather_facts: false
  tasks:
    - ansible.builtin.include_tasks: "{plan}"
    - ansible.builtin.copy:
        dest: "{out}"
        content: >-
          {{{{ {{'families': _stress_families, 'drivers': _stress_drivers, 'shards': _stress_shards | int,
                'wait': _stress_wait, 'overrides': _stress_overrides, 'deadline': _stress_deadline | int,
                'run_id': _stress_run_id}} | to_json }}}}
"""


def plan(**extra_vars):
    """Runs the plan tasks with `extra_vars`; returns (resolved facts or None, ansible output)."""
    with tempfile.TemporaryDirectory(prefix="stress-plan-") as tmp:
        out = pathlib.Path(tmp) / "facts.json"
        book = pathlib.Path(tmp) / "plan.yml"
        book.write_text(PLAYBOOK.format(plan=PLAN, out=out))
        env = dict(os.environ, ANSIBLE_NOCOLOR="1", ANSIBLE_LOCALHOST_WARNING="False", ANSIBLE_INVENTORY_UNPARSED_WARNING="False",
                   ANSIBLE_HOME=tmp, ANSIBLE_LOCAL_TEMP=tmp + "/tmp")
        vars_ = dict(zuno_repo_root=str(REPO), **extra_vars)
        proc = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(book), "-e", json.dumps(vars_)],
                              capture_output=True, text=True, env=env, cwd=tmp, timeout=120)
        facts = json.loads(out.read_text()) if out.exists() else None
        return facts, proc.stdout + proc.stderr


@unittest.skipUnless(shutil.which("ansible-playbook"), "ansible-playbook not on PATH")
class CampaignPlan(unittest.TestCase):
    def test_smoke_takes_everything_from_the_profile(self):
        facts, _ = plan(stress_profile="smoke")
        self.assertEqual(facts["families"], ["tools", "models"])
        self.assertEqual((facts["shards"], facts["wait"], facts["deadline"]), (1, True, 900))
        self.assertEqual(facts["overrides"], {})
        self.assertRegex(facts["run_id"], r"^smoke-\d{8}-\d{6}$")

    def test_make_variables_override_the_profile(self):
        facts, _ = plan(stress_profile="standard", stress_iterations="7", stress_concurrency=3, stress_duration="120",
                        stress_families="tools", stress_drivers="mcp-tools-by-group,ai-gateway-routing", stress_shards="3")
        self.assertEqual(facts["families"], ["tools"])
        self.assertEqual(facts["drivers"], ["mcp-tools-by-group", "ai-gateway-routing"])
        self.assertEqual(facts["shards"], 3)
        self.assertEqual(facts["overrides"], {"iterations": 7, "concurrency": 3, "duration": 120, "families": ["tools"],
                                              "drivers": ["mcp-tools-by-group", "ai-gateway-routing"]})

    def test_the_standard_profile_keeps_the_agents_family(self):
        facts, _ = plan(stress_profile="standard")
        self.assertIn("agents", facts["families"])

    def test_soak_is_async_and_its_deadline_covers_a_longer_duration(self):
        facts, _ = plan(stress_profile="soak")
        self.assertFalse(facts["wait"])
        self.assertEqual(facts["deadline"], 15600)
        facts, _ = plan(stress_profile="soak", stress_duration="20000")
        self.assertEqual(facts["deadline"], 20900)
        facts, _ = plan(stress_profile="soak", stress_wait="true")
        self.assertTrue(facts["wait"])

    def test_aggressive_runs_on_two_shards(self):
        self.assertEqual(plan(stress_profile="aggressive")[0]["shards"], 2)
        self.assertEqual(plan(stress_profile="aggressive", stress_shards="4")[0]["shards"], 4)

    def test_a_bad_profile_name_or_knob_is_refused_before_anything_else(self):
        for bad in ({"stress_profile": "Bad/../x"}, {"stress_profile": "smoke", "stress_iterations": "1;rm"},
                    {"stress_profile": "smoke", "stress_drivers": "a b"}, {"stress_profile": "smoke", "stress_families": "A"}):
            facts, output = plan(**bad)
            self.assertIsNone(facts, bad)
            self.assertIn("stress_profile must be a profile name", output)

    def test_an_unknown_profile_fails(self):
        facts, output = plan(stress_profile="nope")
        self.assertIsNone(facts)
        self.assertIn("profile_nope.yaml", output)


if __name__ == "__main__":
    unittest.main()
