"""What the stress Job can import, and what happens when a driver module cannot be imported (WP-310 follow-up, 2026-11-19).

The campaign Job mounts ONE ConfigMap of flat files at /stress (stresstest_campaign_launch.yml): the runner, its helpers, every
driver_*.py and profile_*.yaml. A driver that imports a module the ConfigMap does not ship kills `load_drivers` at start, and
with it the whole run (standard-20261119-115419 produced zero rows because driver_mutating.py imports unifai_rag_library).

  - the file set is read from the launch task itself, copied into an empty directory, and the real runner is started there
    (`stress_runner.py --list`, no repository on the path): every driver module must import and every driver must register;
  - a module that fails to import is recorded and reported as one failing row, the others keep running.

Run from the repository root:
    python3 evaluations/tests/test_stress_job_files.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
LAUNCH = REPO / "ansible" / "roles" / "day3" / "tasks" / "stresstest_campaign_launch.yml"
STRESS = REPO / "evaluations" / "stress"
sys.path.insert(0, str(REPO / "platform" / "testing"))

import stress_runner as sr  # noqa: E402

FILE_RE = re.compile(r"'([A-Za-z0-9_.-]+)':\s*zuno_repo_root \+ '([^']+)'")


def shipped_files() -> dict:
    """{name in the ConfigMap: source path} from the launch task's `_stress_files` mapping, plus the globbed drivers and profiles."""
    text = LAUNCH.read_text()
    block = text[text.index("_stress_files: >-"):text.index("- name: \"stress | read the files\"")]
    files = {name: REPO / rel.lstrip("/") for name, rel in FILE_RE.findall(block)}
    for pattern in ("driver_*.py", "profile_*.yaml"):
        for path in STRESS.glob(pattern):
            files[path.name] = path
    return files


class JobFileSet(unittest.TestCase):
    def test_the_launch_task_names_files_that_exist(self):
        files = shipped_files()
        self.assertGreater(len(files), 10)
        for name, source in files.items():
            self.assertTrue(source.is_file(), f"{name}: {source} does not exist")

    def test_every_driver_module_imports_with_only_the_shipped_files(self):
        with tempfile.TemporaryDirectory(prefix="stress-job-") as tmp:
            for name, source in shipped_files().items():
                shutil.copy(source, pathlib.Path(tmp) / name)
            # the launch task adds the demos' state assertions as one more key (stress_state.py extract): the state drivers
            # read it at import, so it is part of the file set
            extracted = subprocess.run([sys.executable, str(REPO / "platform" / "testing" / "stress_state.py"), "extract"],
                                       capture_output=True, text=True, check=True, timeout=120)
            (pathlib.Path(tmp) / "state_assertions.json").write_text(extracted.stdout)
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "STRESS_DIR")}
            env["STRESS_DIR"] = tmp
            proc = subprocess.run([sys.executable, str(pathlib.Path(tmp) / "stress_runner.py"), "--list"], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertNotIn("cannot import", proc.stderr, "a driver module does not import in /stress: ship what it imports in the "
                         "ConfigMap file set of stresstest_campaign_launch.yml\n" + proc.stderr[-800:])
        listed = {line.split()[0] for line in proc.stdout.splitlines() if line.strip()}
        for driver in ("delegation-approval", "unifai-live-rag", "image-signing-refusal", "maas-portal-api-keys", "multi-gateway",
                       "blender-3d", "open-webui", "saturation", "limitador-counters", "load-ai-gateway"):
            self.assertIn(driver, listed)


class ResilientLoading(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="stress-load-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        sr.LOAD_FAILURES.clear()
        self.addCleanup(sr.LOAD_FAILURES.clear)
        self.before = set(sr.REGISTRY)
        self.addCleanup(lambda: [sr.REGISTRY.pop(k) for k in set(sr.REGISTRY) - self.before])

    def test_a_module_that_cannot_import_is_one_failing_row_and_the_others_load(self):
        (self.tmp / "driver_zz_good.py").write_text(
            "from stress_runner import register, row\n"
            "@register('zz-good', family='zz', description='d', needs=('x',))\n"
            "async def zz(ctx, i):\n    return []\n")
        (self.tmp / "driver_zz_broken.py").write_text("import a_module_that_is_not_shipped\n")
        loaded = sr.load_drivers(self.tmp)
        self.assertEqual(loaded, ["driver_zz_good.py"])
        self.assertIn("zz-good", sr.REGISTRY)
        rows = sr.load_failure_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].agent, rows[0].passed, rows[0].layer), ("driver_zz_broken", False, "stress"))
        self.assertIn("ModuleNotFoundError", rows[0].detail)
        self.assertIn("a_module_that_is_not_shipped", rows[0].detail)
        self.assertNotIn("driver_zz_broken", sys.modules)

    def test_a_syntax_error_is_reported_the_same_way(self):
        (self.tmp / "driver_zz_syntax.py").write_text("def broken(:\n")
        sr.load_drivers(self.tmp)
        self.assertIn("SyntaxError", sr.load_failure_rows()[0].detail)

    def test_the_main_emits_the_failure_rows_once_and_still_runs(self):
        (self.tmp / "driver_zz_broken.py").write_text("import a_module_that_is_not_shipped\n")
        (self.tmp / "profile_zz.yaml").write_text("name: zz\nfamilies: [tools]\ndefaults: {iterations: 1}\njob: {deadline_seconds: 60}\n")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run([sys.executable, str(STRESS.parents[1] / "platform" / "testing" / "stress_runner.py"), "--dir", str(self.tmp),
                               "--profile", "zz", "--dry-run"], cwd=str(self.tmp), env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        self.assertIn("cannot import driver_zz_broken.py", proc.stderr)


if __name__ == "__main__":
    unittest.main()
