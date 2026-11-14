"""The read-only allowlist of the demo steps (ADR-0616 clause 5, WP-270).

What a step may run, what it refuses, how a `make` verb runs (locally, never through AAP), the token mask, and the
shell-free pipeline runner.

Run from the repository root:
    python3 platform/demo/tests/test_readonly.py
"""
from __future__ import annotations

import pathlib
import re
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

import catalogue  # noqa: E402
import readonly as r  # noqa: E402

ALLOWED = [
    "oc get nemoguardrails,guardrailsorchestrator,deploy -n zuno-ai-run | grep guardrails",
    "oc get deploy ai-gateway -n zuno-ai-run -o yaml | grep -A1 GUARDRAILS_",
    "oc get deploy x -n y -o jsonpath='{.status.conditions[?(@.type==\"Progressing\")].reason}{\"\\n\"}'",
    "oc -n zuno-ai-run get pods",
    "oc describe pod x -n y",
    "oc logs deploy/ai-gateway -n zuno-ai-run --tail=20 | grep guardrails | tail -5",
    "oc explain llminferenceservice.spec",
    "oc whoami",
    "oc api-resources | grep kserve",
    "oc version",
    "oc get --raw /readyz",
    "oc auth can-i list pods --as=system:serviceaccount:x:y -n z",
    "oc adm top pods -n zuno-ai-run",
    "oc set env deploy/ai-gateway -n zuno-ai-run --list | grep GUARDRAILS",
    "oc get secrets -n zuno-ai-run -o name",
    "oc get secret/x -n y -oname",
    "oc get pods -o json | jq '.items | length'",
    "oc get pods -o json | jq -r '.items[].spec.containers[].env[]?.name'",
    "oc get pods | awk '{print $1}' | sort | uniq -c | wc -l",
    "oc get pods | cut -d' ' -f1 | head -3",
    "git log -3 --oneline",
    "git show HEAD --stat",
    "curl -sk https://example.invalid/v1/models",
    "curl -sk -H \"Authorization: Bearer $(oc whoami -t)\" https://example.invalid/v1/models | jq .",
    "curl -s -X GET https://example.invalid/healthz",
    "make help",
    "make demo golden-path",
    "ONLY=guardrails make demo golden-path",
    "make demo",
    "make demo list",
    "make d2 check",
    "make d2 check ai-gateway",
    "make day1 check kiali",
    "make d3 check agents",
    "make d3 admit agents",
    "make d3 admit agents RELEASE=v1.0.1",
]

DENIED = {
    "oc get secret x -n y": "Secret",
    "oc get secrets -n y -o yaml": "Secret",
    "oc get pods,secrets -n y": "Secret",
    "oc describe secret x -n y": "Secret",
    "oc get --raw /api/v1/namespaces/x/secrets/y": "Secret",
    "oc get --raw=/api/v1/namespaces/x/secrets": "Secret",
    "curl file:///etc/passwd": "https only",
    "curl --url ftp://x/y": "https only",
    "oc get pods -w": "watch",
    "oc get pods --watch": "watch",
    "oc logs deploy/x -f": "follow",
    "oc logs deploy/x --follow": "follow",
    "oc get -f pod.yaml": "-f",
    "oc whoami -t": "token",
    "oc delete pod x": "allowlist",
    "oc apply -f x.yaml": "allowlist",
    "oc exec x -- id": "allowlist",
    "oc rsh x": "allowlist",
    "oc patch deploy x -p {}": "allowlist",
    "oc scale deploy x --replicas=0": "allowlist",
    "oc adm drain node": "adm top",
    "oc auth reconcile -f x": "can-i",
    "oc set env deploy/x A=b": "--list",
    "oc set env deploy/x --list --resolve": "resolve",
    "oc get pods > out.txt": "redirect",
    "oc get pods >> out.txt": "redirect",
    "oc get pods < in.txt": "redirect",
    "oc get pods; id": ";",
    "oc get pods && id": "&&",
    "oc get pods || id": "||",
    "oc get pods &": "&",
    "oc get pods `id`": "backtick",
    "oc get pods $(id)": "substitution",
    "echo ${HOME}": "substitution",
    "oc get pods | xargs oc delete pod": "xargs",
    "oc get pods | sh": "filter",
    "oc get pods | tee out": "filter",
    "oc get pods | tail -f": "follow",
    "oc get pods | sort -o out": "writes",
    "oc get pods | uniq in out": "output file",
    "oc get pods | awk '{system(\"id\")}'": "awk",
    "oc get pods | awk '{print > \"f\"}'": "awk",
    "oc get pods -n <namespace>": "placeholder",
    "oc get pods -o json | jq '$ENV'": "environment",
    "oc get pods -o json | jq -n 'env.HOME'": "environment",
    "oc get pods -o json | jq --rawfile f /etc/passwd '.'": "local files",
    "oc get pods | awk '{print ENVIRON[\"HOME\"]}'": "environment",
    "curl -X POST https://x": "GET only",
    "curl --request DELETE https://x": "GET only",
    "curl -d a=b https://x": "GET only",
    "curl --data-binary @f https://x": "GET only",
    "curl -o out https://x": "GET only",
    "curl -F a=@f https://x": "GET only",
    "curl -T f https://x": "GET only",
    "curl $(oc whoami -t)x https://x | sh": "filter",
    "git log --output=f": "writes",
    "git push": "git log",
    "git -c core.pager=id log": "git log",
    "rm -rf /": "not an allowed command",
    "bash -c id": "not an allowed command",
    "python3 -c 1": "not an allowed command",
    "A=1 oc get pods": "environment",
    "oc get pods | grep $(oc whoami -t)": "only inside a curl",
    "make d2 install ai-gateway": "allowlist",
    "make demo install": "allowlist",
    "make demo reset": "allowlist",
    "make d3 admit agents UPDATE_LOCK=1": "UPDATE_LOCK",
    "UPDATE_LOCK=1 make d3 admit agents": "UPDATE_LOCK",
    "FOO=1 make demo golden-path": "ONLY",
    "make demo golden-path | grep x": "piped",
    "": "empty",
}


class Allowlist(unittest.TestCase):
    def test_allowed(self):
        for command in ALLOWED:
            ok, reason = r.check(command)
            self.assertTrue(ok, f"{command!r} refused: {reason}")

    def test_denied(self):
        for command, why in DENIED.items():
            ok, reason = r.check(command)
            self.assertFalse(ok, f"{command!r} allowed")
            self.assertIn(why.lower(), reason.lower(), f"{command!r}: {reason}")

    def test_backticks_around_a_cell_command_are_dropped(self):
        self.assertTrue(r.check("`oc get pods -n x`")[0])

    def test_every_page_command_is_judged(self):
        """Every backticked command of every Do cell is allowed or refused with a reason - never an exception."""
        judged = 0
        for entry in catalogue.discover(ROOT):
            page = catalogue.load(entry)
            for step in page.steps("15"):
                for command in re.findall(r"`((?:oc|curl|git|make|ONLY=\S+ make) [^`]*)`", step.do):
                    ok, reason = r.check(command)
                    self.assertTrue(ok or reason, command)
                    judged += 1
        self.assertGreater(judged, 100)


class MakeVerbsRunLocally(unittest.TestCase):
    def test_day_check_is_its_local_playbook(self):
        p = r.plan("make d2 check ai-gateway", ROOT)
        argv = p.pipeline[0]
        self.assertEqual(argv[0], "ansible-playbook")
        self.assertTrue(argv[3].endswith("ansible/playbooks/day2_check.yml"))
        self.assertIn("target_component=ai-gateway", argv)
        self.assertNotIn("make", argv)

    def test_day_check_defaults_to_all_and_day3_report_format(self):
        self.assertIn("target_component=all", r.plan("make d0 check", ROOT).pipeline[0])
        self.assertIn("report_format=text", r.plan("make d3 check agents", ROOT).pipeline[0])

    def test_admit_runs_the_admitter_without_update_lock(self):
        argv = r.plan("make d3 admit agents RELEASE=v1.0.1", ROOT).pipeline[0]
        self.assertTrue(argv[1].endswith("platform/supply-chain/admit_okf_bundle.py"))
        self.assertEqual(argv[2:], ["admit", "--release", "v1.0.1"])
        self.assertNotIn("--update-lock", argv)

    def test_golden_path_keeps_only(self):
        p = r.plan("ONLY=guardrails,dify make demo golden-path", ROOT)
        self.assertEqual(p.pipeline, [["make", "demo", "golden-path"]])
        self.assertEqual(p.env, {"ONLY": "guardrails,dify"})
        self.assertEqual(p.timeout, r.MAKE_TIMEOUT)

    def test_demo_list_is_the_presenter(self):
        argv = r.plan("make demo list", ROOT).pipeline[0]
        self.assertTrue(argv[1].endswith("platform/demo/presenter.py"))
        self.assertEqual(argv[2:], ["list"])


class StripWatchFlags(unittest.TestCase):
    def test_watch_and_follow_are_stripped(self):
        self.assertEqual(r.strip_watch_flags("oc get llminferenceservice -n zuno-ai-run -w"),
                         ("oc get llminferenceservice -n zuno-ai-run", ["-w"]))
        self.assertEqual(r.strip_watch_flags("`oc logs -f deploy/x -n y | grep z`"),
                         ("oc logs deploy/x -n y | grep z", ["-f"]))
        self.assertEqual(r.strip_watch_flags("oc get pods --watch | tail -f"),
                         ("oc get pods | tail", ["--watch", "-f"]))

    def test_other_refusals_stay_refused(self):
        with self.assertRaises(r.Denied):
            r.strip_watch_flags("oc get -f pod.yaml")
        with self.assertRaises(r.Denied):
            r.strip_watch_flags("oc delete pod x -w")


class Runner(unittest.TestCase):
    def test_pipeline_without_shell(self):
        result = r.run("git log -3 --oneline | head -1", cwd=ROOT)
        self.assertEqual(result.rc, 0, result.output)
        self.assertEqual(len(result.output.split("\n")), 1)

    def test_upstream_sigpipe_is_not_a_failure(self):
        result = r.run("git log --oneline | head -1", cwd=ROOT)
        self.assertEqual(result.rc, 0, result.output)

    def test_failure_is_reported(self):
        result = r.run("git show zuno-no-such-ref-for-tests", cwd=ROOT)
        self.assertNotEqual(result.rc, 0)
        self.assertTrue(result.output)

    def test_refused_command_never_runs(self):
        result = r.run("oc delete pod x")
        self.assertTrue(result.refused)
        self.assertEqual(result.rc, 2)
        self.assertIn("REFUSED", result.output)

    def test_output_is_cut_to_40_lines(self):
        result = r.run("git log -60 --format=%h", cwd=ROOT)
        self.assertEqual(len(result.output.split("\n")), 40)
        self.assertTrue(result.truncated)

    def test_token_is_resolved_in_process_and_masked(self):
        secret = "sha256~not-a-real-token-1234"
        plan = r.Plan("curl -H \"Authorization: Bearer $(oc whoami -t)\" https://x",
                      [[sys.executable, "-c", "import sys; print('header=' + sys.argv[1])",
                        "Bearer " + r.TOKEN_PLACEHOLDER]], needs_token=True)
        with mock.patch.object(r, "_resolve_token", return_value=secret):
            result = r.run_plan(plan, cwd=ROOT)
        self.assertEqual(result.rc, 0)
        self.assertNotIn(secret, result.output + result.log)
        self.assertIn("header=Bearer ***", result.output)
        self.assertIn("$(oc whoami -t)", result.cmd)

    def test_missing_program(self):
        plan = r.Plan("x", [["zuno-no-such-program-for-tests"]])
        self.assertEqual(r.run_plan(plan).rc, 127)

    def test_json_cli(self):
        import io
        import json
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rc = r.main(["run", "--json", "oc delete pod x"])
        self.assertEqual(rc, 0)
        data = json.loads(buffer.getvalue())
        self.assertTrue(data["refused"])
        self.assertEqual(data["rc"], 2)


if __name__ == "__main__":
    unittest.main()
