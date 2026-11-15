"""The presenter's session, freeze marker and guards, and the command line on the fixture (ADR-0616 clauses 1, 7, 8,
WP-270).

The fixture (platform/demo/tests/fixtures/) is a page and its demo directory that need no cluster (`cluster: false`):
the end-to-end cases run ansible/playbooks/demo_run.yml for real and are skipped where ansible-playbook is missing.
Every case runs with a temporary HOME, so the presenter's own session is never touched.

Run from the repository root:
    python3 platform/demo/tests/test_guard_session.py
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import site
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIXTURES = HERE / "fixtures"
PRESENTER = HERE.parent / "presenter.py"
sys.path.insert(0, str(HERE.parent))

import guard  # noqa: E402
import session  # noqa: E402

USER_BASE = site.getuserbase()


class TempHome(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="zuno-demo-test-")
        self.patch = mock.patch.dict(os.environ, {"HOME": self.home})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.home, ignore_errors=True)


class Session(TempHome):
    def test_paths_are_under_home(self):
        self.assertEqual(session.session_path(), pathlib.Path(self.home, ".config/zuno/demo-session.json"))
        self.assertEqual(session.freeze_path(), pathlib.Path(self.home, ".config/zuno/demo-freeze.json"))
        self.assertEqual(session.rehearsals_dir(), pathlib.Path(self.home, ".cache/zuno/demo/rehearsals"))

    def test_save_load_move(self):
        self.assertIsNone(session.load_session())
        session.save_session("guardrails", "15", 0, 14)
        current = session.load_session()
        self.assertEqual((current["demo"], current["version"], current["position"], current["total"]),
                         ("guardrails", "15", 0, 14))
        session.set_position(current, 8)
        self.assertEqual(session.load_session()["position"], 8)

    def test_corrupt_session_is_no_session(self):
        session.session_path().parent.mkdir(parents=True)
        session.session_path().write_text("{not json")
        self.assertIsNone(session.load_session())

    def test_freeze_on_off(self):
        self.assertIsNone(session.load_freeze())
        marker = session.freeze_on()
        self.assertIn("@", marker["who"])
        self.assertTrue(session.load_freeze())
        self.assertTrue(session.freeze_off())
        self.assertFalse(session.freeze_off())


class Guards(TempHome):
    CHANGES = {"install": "Writes a marker"}

    def test_freeze_refuses_install_uninstall_rehearse_only(self):
        session.freeze_on()
        for action in ("install", "uninstall", "rehearse"):
            with self.assertRaises(guard.Refused):
                guard.check_freeze(action)
        for action in ("status", "check", "start", "stop", "step"):
            guard.check_freeze(action)

    def test_nothing_to_confirm(self):
        self.assertEqual(guard.confirm("x", {}, env={}, out=io.StringIO()), "")

    def test_demo_confirm_must_be_this_id(self):
        out = io.StringIO()
        self.assertEqual(guard.confirm("fixture-demo", self.CHANGES, env={"DEMO_CONFIRM": "fixture-demo"}, out=out),
                         "fixture-demo")
        self.assertIn("install: Writes a marker", out.getvalue())
        for other in ("other", "all", "yes", "*", "fixture-dem", "fixture-demo "):
            with self.assertRaises(guard.Refused):
                guard.confirm("fixture-demo", self.CHANGES, env={"DEMO_CONFIRM": other}, out=io.StringIO())

    def test_no_tty_refuses(self):
        with self.assertRaises(guard.Refused) as ctx:
            guard.confirm("fixture-demo", self.CHANGES, env={}, stdin=io.StringIO(""), out=io.StringIO())
        self.assertIn("DEMO_CONFIRM=fixture-demo", str(ctx.exception))

    def test_tty_typed_id(self):
        tty = mock.Mock()
        tty.isatty.return_value = True
        self.assertEqual(guard.confirm("fixture-demo", self.CHANGES, env={}, stdin=tty, out=io.StringIO(),
                                       ask=lambda prompt: "fixture-demo\n"), "fixture-demo")
        with self.assertRaises(guard.Refused):
            guard.confirm("fixture-demo", self.CHANGES, env={}, stdin=tty, out=io.StringIO(), ask=lambda p: "y")

    def test_infra_unit_prints_double_approval(self):
        out = io.StringIO()
        guard.confirm("world-model", {"install": {"summary": "Adds a GPU node", "infra": True}},
                      env={"DEMO_CONFIRM": "world-model"}, out=out)
        self.assertIn("double approval", out.getvalue())
        self.assertIn("Adds a GPU node", out.getvalue())

    def test_manifest_helpers(self):
        manifest = {"mutations": {"start": "Uploads files"},
                    "steps": {"9:30": {"mutating": True, "optional": True, "freeze": "forbidden"},
                              "12:45": {"optional": True}}}
        self.assertEqual(guard.changing_units(manifest, ["status", "start"]), {"start": "Uploads files"})
        self.assertEqual(list(guard.mutating_steps(manifest)), ["9:30"])
        self.assertTrue(guard.forbidden_in_freeze(guard.step_meta(manifest, "9:30")))
        self.assertEqual(guard.step_meta(manifest, "0:00"), {})


class DomainCache(TempHome):
    def test_remember_and_read_back_per_server(self):
        import runner
        self.assertEqual(runner.cached_domain("https://api.a:6443"), "")
        runner.remember_domain("https://api.a:6443", "apps.a.example")
        runner.remember_domain("https://api.b:6443", "apps.b.example")
        self.assertEqual(runner.cached_domain("https://api.a:6443"), "apps.a.example")
        self.assertEqual(runner.cached_domain("https://api.b:6443"), "apps.b.example")
        self.assertEqual(runner.cached_domain("https://api.c:6443"), "")
        self.assertEqual(runner.cached_domain(""), "")
        runner.remember_domain("", "apps.x")
        runner.domain_cache_path().write_text("{broken")
        self.assertEqual(runner.cached_domain("https://api.a:6443"), "")

    def test_a_fixture_demo_never_asks_the_cluster(self):
        import runner
        self.assertFalse(runner._needs_cluster(FIXTURES / "ansible/demos/fixture-demo"))
        self.assertTrue(runner._needs_cluster(ROOT / "ansible/demos/guardrails"))


class NotRehearsed(unittest.TestCase):
    def test_an_action_listed_not_rehearsed_is_skipped_with_its_reason(self):
        import catalogue
        import rehearse
        page = catalogue.load_page(FIXTURES / "docs/demo/scenarios/fixture/fixture-demo.md", "scenario", "fixture")
        demo_dir = FIXTURES / "ansible/demos/fixture-demo"
        manifest = {"not_rehearsed": {"install": "the owner creates the node by hand"}}
        to_run, decided = rehearse.plan_units(page, "5", demo_dir, manifest)
        self.assertNotIn("install", [u.name for u in to_run])
        self.assertIn("uninstall", [u.name for u in to_run])
        skipped = [d for d in decided if d.name == "install"][0]
        self.assertEqual(skipped.status, "skipped")
        text, passed = rehearse.report(page, "5", rehearse.merge(page, "5", None, decided + [
            rehearse.UnitResult(u.name, "ok") for u in to_run]), None)
        self.assertIn("| install | SKIPPED | 0.0 | not rehearsed: the owner creates the node by hand |", text)
        self.assertTrue(passed)


class PresenterRun(TempHome):
    """Runs the command line on the fixture catalogue, as a subprocess without a terminal."""

    def presenter(self, *args, env=None):
        full = dict(os.environ, ZUNO_DEMO_ROOT=str(FIXTURES), ZUNO_REPO_ROOT=str(ROOT), PYTHONUSERBASE=USER_BASE,
                    HOME=self.home)
        full.pop("DEMO_CONFIRM", None)
        full.pop("VERBOSE", None)
        full.update(env or {})
        done = subprocess.run([sys.executable, str(PRESENTER)] + list(args), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=full,
                              cwd=str(ROOT), timeout=300)
        return done.returncode, done.stdout


class Presenter(PresenterRun):
    def test_usage_and_list(self):
        rc, text = self.presenter()
        self.assertEqual(rc, 0)
        self.assertIn("Usage: make demo <verb>", text)
        self.assertIn("Session: none", text)
        rc, text = self.presenter("list")
        self.assertEqual(rc, 0, text)
        self.assertRegex(text, r"fixture-demo\s+scenario\s+fixture\s+3\s+6")
        self.assertRegex(text, r"fixture-workshop\s+workshop\s+workshop\s+-\s+-\s+8\s")

    def test_unknown_verb_and_id(self):
        self.assertEqual(self.presenter("reset")[0], 2)
        self.assertEqual(self.presenter("use", "no-such-demo", "5")[0], 2)
        self.assertEqual(self.presenter("use", "fixture-demo", "10")[0], 2)
        self.assertEqual(self.presenter("use", "fixture-workshop", "15")[0], 2)
        self.assertEqual(self.presenter("step", "next")[0], 2)

    def test_use_writes_the_session(self):
        rc, text = self.presenter("use", "fixture-demo", "15")
        self.assertEqual(rc, 0, text)
        data = json.loads(pathlib.Path(self.home, ".config/zuno/demo-session.json").read_text())
        self.assertEqual((data["demo"], data["version"], data["position"], data["total"]), ("fixture-demo", "15", 0, 6))

    def test_not_scaffolded_prints_the_row_and_fails(self):
        self.presenter("use", "fixture-unscaffolded", "15")
        rc, text = self.presenter("step", "next")
        self.assertEqual(rc, 1)
        self.assertIn("NOT SCAFFOLDED: ansible/demos/fixture-unscaffolded/ is missing (WP-271)", text)
        self.assertIn("fixture-unscaffolded · 15-minute · step 1/3 · 0:00", text)
        self.assertIn("Say what the fixture is", text)
        self.assertIn("Next: 2/3 · 4:00 · Close", text)
        rc, text = self.presenter("status")
        self.assertEqual(rc, 1)
        self.assertIn("NOT SCAFFOLDED", text)
        self.assertIn("page not migrated yet", text)

    def test_step_position_is_kept_even_when_it_fails(self):
        self.presenter("use", "fixture-unscaffolded", "5")
        self.presenter("step", "2")
        data = json.loads(pathlib.Path(self.home, ".config/zuno/demo-session.json").read_text())
        self.assertEqual(data["position"], 2)
        rc, text = self.presenter("step", "next")
        self.assertEqual(rc, 0)
        self.assertIn("all 2 steps played", text)
        self.assertEqual(self.presenter("step", "3")[0], 2)

    def test_changing_action_is_guarded_before_anything_runs(self):
        rc, text = self.presenter("install", "fixture-demo", env={"DEMO_CONFIRM": "other"})
        self.assertEqual(rc, 2)
        self.assertIn("REFUSED: DEMO_CONFIRM='other' does not confirm 'fixture-demo'", text)
        rc, text = self.presenter("install", "fixture-demo")
        self.assertEqual(rc, 2)
        self.assertIn("No terminal to confirm on", text)
        self.assertFalse(pathlib.Path(self.home, ".cache/zuno/demo/logs").exists(), "nothing may have run")

    def test_freeze_refuses_install_and_rehearse(self):
        self.assertEqual(self.presenter("freeze", "on")[0], 0)
        rc, text = self.presenter("install", "fixture-demo", env={"DEMO_CONFIRM": "fixture-demo"})
        self.assertEqual(rc, 2)
        self.assertIn("refused during a freeze", text)
        rc, text = self.presenter("rehearse", "fixture-demo", "5", env={"DEMO_CONFIRM": "fixture-demo"})
        self.assertEqual(rc, 2)
        self.assertIn("refused during a freeze", text)
        self.assertEqual(self.presenter("freeze", "off")[0], 0)
        self.assertIn("Freeze: off", self.presenter("freeze")[1])

    def test_workshop_session_and_guard(self):
        rc, text = self.presenter("use", "fixture-workshop")
        self.assertEqual(rc, 0)
        self.assertIn("Using fixture-workshop · workshop · 8 steps.", text)
        self.assertEqual(self.presenter("use", "fixture-workshop", "5")[0], 2)
        self.assertEqual(self.presenter("rehearse", "fixture-workshop", "5")[0], 2)
        rc, text = self.presenter("install", env={"DEMO_CONFIRM": "fixture-demo"})
        self.assertEqual(rc, 2)
        self.assertIn("install:fixture-demo: Writes the fixture add-on marker", text)
        self.assertIn("does not confirm 'fixture-workshop'", text)
        self.assertEqual(self.presenter("step", "9")[0], 2)

    def test_completion_words(self):
        self.assertIn("fixture-demo", self.presenter("--ids")[1].split())
        self.assertEqual(self.presenter("--complete", "use", "fixture-demo")[1].split(), ["5", "15"])
        self.assertEqual(self.presenter("--complete", "freeze")[1].split(), ["on", "off"])


@unittest.skipIf(shutil.which("ansible-playbook") is None, "ansible-playbook is not installed")
class EndToEnd(PresenterRun):
    """action -> demo_run.yml -> results JSON -> page section, on the fixture (no cluster)."""

    def test_status_step_and_failure(self):
        self.presenter("use", "fixture-demo", "15")
        rc, text = self.presenter("status")
        self.assertEqual(rc, 0, text)
        self.assertIn("$ git log -1 --format=%h   [ok]", text)
        self.assertIn("PASS fixture-add-on: not installed", text)
        self.assertIn("STATUS\nNothing to do.", text)
        rc, text = self.presenter("step", "next")
        self.assertEqual(rc, 0, text)
        self.assertIn("fixture-demo · 15-minute · step 1/6 · 0:00", text)
        rc, text = self.presenter("step", "next")
        self.assertEqual(rc, 0, text)
        self.assertIn("NOT RUN: this step changes the cluster", text)
        rc, text = self.presenter("step", "5")
        self.assertEqual(rc, 1, text)
        self.assertIn("[exit 128]", text)
        self.assertIn("FAILED\nIf something goes wrong:\n- Symptom: The 6:00 read fails", text)
        self.assertIn("Next: 6/6 · 14:00 · Close", text)

    def test_install_status_uninstall(self):
        marker = pathlib.Path(self.home, ".cache/zuno/demo/fixture-demo.installed")
        rc, text = self.presenter("install", "fixture-demo", env={"DEMO_CONFIRM": "fixture-demo"})
        self.assertEqual(rc, 0, text)
        self.assertTrue(marker.exists())
        self.assertIn("INSTALL\nThe file writes the fixture add-on marker.", text)
        self.assertIn("PASS fixture-add-on: installed", self.presenter("status", "fixture-demo")[1])
        rc, text = self.presenter("uninstall", "fixture-demo", env={"DEMO_CONFIRM": "fixture-demo"})
        self.assertEqual(rc, 0, text)
        self.assertFalse(marker.exists())

    def test_playbook_rechecks_the_confirmation(self):
        """A direct ansible-playbook run of a changing unit without the confirmation is refused by demo_run.yml."""
        sys.path.insert(0, str(HERE.parent))
        import runner
        with mock.patch.dict(os.environ, {"PYTHONUSERBASE": USER_BASE}):
            result = runner.run_units("fixture-demo", FIXTURES / "ansible/demos/fixture-demo",
                                      [runner.Unit("install", "install.yml")], confirmed="other")
        self.assertNotEqual(result.rc, 0)
        self.assertIn("stopped before any unit ran", result.error)
        self.assertFalse(pathlib.Path(self.home, ".cache/zuno/demo/fixture-demo.installed").exists())

    def test_workshop_chain_steps_and_rehearsal(self):
        self.presenter("use", "fixture-workshop")
        rc, text = self.presenter("status")
        self.assertEqual(rc, 0, text)
        self.assertIn("[status:fixture-demo]\n  $ git log -1 --format=%h   [ok]", text)
        self.assertIn("[status]\n  Nothing to run.", text)
        self.assertIn("STATUS\nNothing to do. The scenario's status file runs", text)
        rc, text = self.presenter("step", "2")
        self.assertEqual(rc, 0, text)
        self.assertIn("step 2/8 · 0:02 The scenario · fixture-demo 0:00 (1/3)", text)
        self.assertIn("$ git log -1 --format=%h   [ok]", text)
        rc, text = self.presenter("step", "next")
        self.assertIn("NOT RUN: this step changes the cluster", text)
        rc, text = self.presenter("step", "5")
        self.assertIn('Transition to the next block:\n  "And the workshop\'s own rows."', text)
        rc, text = self.presenter("step", "6")
        self.assertEqual(rc, 0, text)
        self.assertIn("$ git log -1 --format=%s   [ok]", text)
        marker = pathlib.Path(self.home, ".cache/zuno/demo/fixture-demo.installed")
        rc, text = self.presenter("install", env={"DEMO_CONFIRM": "fixture-workshop"})
        self.assertEqual(rc, 0, text)
        self.assertTrue(marker.exists())
        rc, text = self.presenter("rehearse", "fixture-workshop", env={"DEMO_CONFIRM": "fixture-workshop"})
        self.assertEqual(rc, 0, text)
        self.assertIn("| 0:02/1:30 | SKIPPED (mutating) |", text)
        self.assertIn("| uninstall:fixture-demo | PASS |", text)
        self.assertIn("confirmed by `fixture-workshop`: install:fixture-demo", text)
        self.assertIn("RESULT: PASS", text)
        self.assertFalse(marker.exists())
        self.assertRegex(self.presenter("list")[1], r"fixture-workshop.*w: PASS \d{4}")

    def test_a_scenario_unit_is_rechecked_by_the_playbook(self):
        """A workshop unit that its scenario declares changing does not run without the workshop's confirmation."""
        import runner
        import workshop
        units = [u for u in workshop.action_units("fixture-workshop", {"agenda": [
            {"at": "0:02", "scenario": "fixture-demo", "version": "5"}]}, "install", FIXTURES)]
        with mock.patch.dict(os.environ, {"PYTHONUSERBASE": USER_BASE}):
            result = runner.run_units("fixture-workshop", FIXTURES / "ansible/demos/fixture-workshop", units,
                                      confirmed="fixture-demo")
        self.assertTrue(result.unit("install:fixture-demo").failed)
        self.assertIn("changes the cluster", result.unit("install:fixture-demo").error)
        self.assertFalse(pathlib.Path(self.home, ".cache/zuno/demo/fixture-demo.installed").exists())

    def test_argo_apps_fail_when_argo_cd_cannot_be_read(self):
        """_lib/argo_apps.yml end to end with no cluster (the API points at a closed local port): nothing is found, so
        the controller is reported not running and the Application fails; no stale status can pass."""
        root = pathlib.Path(tempfile.mkdtemp(prefix="zuno-argo-"))
        try:
            shutil.copytree(FIXTURES / "docs", root / "docs")
            shutil.copytree(FIXTURES / "ansible", root / "ansible")
            (root / "ansible/demos/fixture-demo/status.yml").write_text(
                '- ansible.builtin.include_tasks: "{{ demo_lib }}/argo_apps.yml"\n  vars:\n'
                '    argo_apps: ["zuno-a"]\n')
            rc, text = self.presenter("status", "fixture-demo", env={
                "ZUNO_DEMO_ROOT": str(root), "K8S_AUTH_HOST": "https://127.0.0.1:1", "K8S_AUTH_API_KEY": "none",
                "K8S_AUTH_VERIFY_SSL": "false", "KUBECONFIG": "/nonexistent/kubeconfig"})
            self.assertEqual(rc, 1, text)
            self.assertIn("FAIL argo/application-controller: Argo CD is not running", text)
            self.assertIn("FAIL argo/zuno-a: absent/absent", text)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rehearse_reports(self):
        rc, text = self.presenter("rehearse", "fixture-demo", "5", env={"DEMO_CONFIRM": "fixture-demo"})
        self.assertEqual(rc, 0, text)
        self.assertIn("| 1:30 | SKIPPED (mutating) |", text)
        self.assertIn("- Changing units, confirmed by `fixture-demo`: install (Writes the fixture add-on marker", text)
        self.assertIn("uninstall (Removes the fixture add-on marker)", text)
        self.assertIn("- Steps not run (declared mutating): 1:30", text)
        self.assertIn("RESULT: PASS", text)
        rc, text = self.presenter("rehearse", "fixture-demo", "15", env={"DEMO_CONFIRM": "fixture-demo"})
        self.assertEqual(rc, 1, text)
        self.assertIn("| 6:00 | FAIL |", text)
        self.assertIn("RESULT: FAIL", text)
        reports = sorted(pathlib.Path(self.home, ".cache/zuno/demo/rehearsals").glob("fixture-demo-*.md"))
        self.assertEqual(len(reports), 2)
        self.assertFalse(pathlib.Path(self.home, ".config/zuno/demo-session.json").exists(), "rehearse kept off the session")
        self.assertRegex(self.presenter("list")[1], r"5: PASS \d{4}-\d{2}-\d{2}, 15: FAIL")


if __name__ == "__main__":
    unittest.main()
