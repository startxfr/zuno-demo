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
    "make d2 check chaos",
    "make d3 check chaos",
    "oc get --raw /api/v1/namespaces/zuno-chaos/services/http:cerberus:8080/proxy/",
    "oc get pipelineruns -n zuno-chaos -l zuno.io/chaos=true",
    "oc get externalsecrets -A --no-headers | awk '{print $(NF-1)}' | sort | uniq -c",
    "oc get pods -o json | jq '.items[] | select(.status.restartCount > 1 and .x < 3) | `x`'",
    "curl -s -o /dev/null -w '%{http_code}\\n' https://example.invalid/v1/models",
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
    "oc describe node <a node of the 1:00 step> | grep nvidia.com/": "placeholder",
    "curl -s https://<route>/v1/models": "placeholder",
    "oc get pods -n $NS": "variable $NS is not set by the step",
    "curl -s $MAAS/v1/models": "variable $MAAS is not set by the step",
    "oc get pods -o json | jq \"$(id)\"": "substitution",
    "oc get pods -o json | jq \"`id`\"": "backtick",
    "curl -s -o out.txt https://x": "GET only",
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
    "make d3 chaos infra TIER=pods CHAOS_CONFIRM=infra": "allowlist",
    "make d3 chaos platform TARGETS=pod-ai-gateway CHAOS_CONFIRM=platform": "allowlist",
    "make d3 chaos platform": "allowlist",
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


class RepositoryFileReads(unittest.TestCase):
    """grep/tail/head/cat/wc as the first segment read repository files only (reorg follow-up of WP-278)."""

    ALLOWED = [
        "grep -c 'release_tag' platform/supply-chain/pinned-releases.yaml",
        "grep -A8 'release_tag: v0.15.0' platform/supply-chain/pinned-releases.yaml",
        "grep -n -e release_tag -e signed platform/supply-chain/pinned-releases.yaml | head -5",
        "tail -2 platform/okf/agents.lock",
        "tail -n 2 platform/okf/agents.lock",
        "head -3 platform/demo/readonly.py",
        "cat platform/demo/readonly.py | wc -l",
        "wc -l platform/demo/readonly.py",
    ]
    DENIED = {
        "cat /etc/passwd": "relative path",
        "cat ~/.ssh/id_rsa": "relative path",
        "cat ../outside.txt": "..",
        "cat platform/../../outside": "..",
        "grep x -r platform": "walks directories",
        "grep -rn x platform": "walks directories",
        "grep -f patterns.txt platform/okf/agents.lock": "other files",
        "grep -x": "needs a pattern",
        "grep x": "needs a repository file",
        "tail": "needs a repository file",
        "tail -f platform/okf/agents.lock": "other files",
        "tail -F platform/okf/agents.lock": "other files",
        "cat platform": "not a regular file",
        "cat platform/okf/missing-file.lock": "not a regular file",
        "cat .git/config": "never read",
        "cat ansible/confidential.yml": "never read",
        "cat ansible/confidential/vault.yml": "never read",
        "cat ansible/inventories/demo333/confidential.yml": "never read",
        "cat ansible/inventories/demo222/confidential.yml.back": "never read",
        "head ansible/inventories/demo333/vault-recovery-demo333.json": "never read",
        "cat ansible/vault-recovery-demo333.json": "never read",
        "cat docs/.env": "never read",
        "cat docs/x.env": "never read",
        "wc --files0-from=list.txt": "other files",
        "cat -": "repository file",
        "cat https://x/y": "relative path",
        "grep x platform/okf/agents.lock > out": "redirect",
        "cat platform/okf/agents.lock; id": ";",
        "A=1 cat platform/okf/agents.lock": "environment",
    }

    def test_allowed(self):
        for command in self.ALLOWED:
            ok, reason = r.check(command)
            self.assertTrue(ok, f"{command!r} refused: {reason}")

    def test_denied(self):
        for command, why in self.DENIED.items():
            ok, reason = r.check(command)
            self.assertFalse(ok, f"{command!r} allowed")
            self.assertIn(why.lower(), reason.lower(), f"{command!r}: {reason}")

    def test_a_secret_named_file_is_refused_even_when_it_exists(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "ansible" / "confidential").mkdir(parents=True)
            (root / "ansible" / "confidential" / "a.yml").write_text("x")
            (root / "docs").mkdir()
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("x")
            for name in ("my-secret.yaml", ".env", "tls.key", "ca.pem", "notes.txt"):
                (root / "docs" / name).write_text("x")
            with self.assertRaises(r.Denied):
                r.plan("cat .git/config", root=root)
            for name in ("my-secret.yaml", ".env", "tls.key", "ca.pem"):
                with self.assertRaises(r.Denied, msg=name):
                    r.plan(f"cat docs/{name}", root=root)
            with self.assertRaises(r.Denied):
                r.plan("cat ansible/confidential/a.yml", root=root)
            (root / "ansible" / "inventories" / "demo333").mkdir(parents=True)
            for name in ("confidential.yml", "confidential.yml.back", "vault-recovery-demo333.json", "hosts.yml"):
                (root / "ansible" / "inventories" / "demo333" / name).write_text("x")
            for name in ("confidential.yml", "confidential.yml.back", "vault-recovery-demo333.json"):
                with self.assertRaises(r.Denied, msg=name):
                    r.plan(f"cat ansible/inventories/demo333/{name}", root=root)
            r.plan("cat ansible/inventories/demo333/hosts.yml", root=root)
            r.plan("cat docs/notes.txt", root=root)

    def test_a_symlink_cannot_leave_the_repository_or_reach_a_secret(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = pathlib.Path(tmp)
            (root / "docs").mkdir()
            (root / "ansible" / "confidential").mkdir(parents=True)
            (root / "ansible" / "confidential" / "a.yml").write_text("x")
            (pathlib.Path(outside) / "out.txt").write_text("x")
            (root / "docs" / "out.txt").symlink_to(pathlib.Path(outside) / "out.txt")
            (root / "docs" / "innocent.txt").symlink_to(root / "ansible" / "confidential" / "a.yml")
            with self.assertRaises(r.Denied) as out:
                r.plan("cat docs/out.txt", root=root)
            self.assertIn("outside", str(out.exception))
            with self.assertRaises(r.Denied) as inside:
                r.plan("cat docs/innocent.txt", root=root)
            self.assertIn("never read", str(inside.exception))

    def test_runs_without_a_shell(self):
        out = r.run("grep -c release_tag platform/supply-chain/pinned-releases.yaml")
        self.assertEqual(out.rc, 0, out.output)
        self.assertRegex(out.output.strip(), r"^\d+$")
        tail = r.run("tail -2 platform/okf/agents.lock")
        self.assertEqual(tail.rc, 0, tail.output)
        self.assertEqual(len(tail.output.splitlines()), 2)

    def test_filters_after_a_file_read_still_apply(self):
        self.assertFalse(r.check("cat platform/okf/agents.lock | sh")[0])
        self.assertFalse(r.check("cat platform/okf/agents.lock | xargs rm")[0])


class MakeVerbsRunLocally(unittest.TestCase):
    def test_day_check_is_its_local_playbook(self):
        p = r.plan("make d2 check ai-gateway", ROOT)
        argv = p.pipeline[0]
        self.assertEqual(argv[0], "ansible-playbook")
        self.assertTrue(argv[3].endswith("ansible/playbooks/day2_check.yml"))
        self.assertIn("target_component=ai-gateway", argv)
        self.assertNotIn("make", argv)
        self.assertTrue(argv[2].endswith("ansible/inventories/demo333/hosts.yml"), argv[2])

    def test_day_check_uses_the_inventory_of_zuno_cluster(self):
        with mock.patch.dict("os.environ", {"ZUNO_CLUSTER": "demo222"}):
            argv = r.plan("make d2 check ai-gateway", ROOT).pipeline[0]
        self.assertTrue(argv[2].endswith("ansible/inventories/demo222/hosts.yml"), argv[2])
        for bad in ("../x", "demo333/../../etc", "Demo 333"):
            with mock.patch.dict("os.environ", {"ZUNO_CLUSTER": bad}), self.assertRaises(r.Denied):
                r.plan("make d2 check ai-gateway", ROOT)

    def test_day_check_defaults_to_all_and_day3_report_format(self):
        self.assertIn("target_component=all", r.plan("make d0 check", ROOT).pipeline[0])
        self.assertIn("report_format=text", r.plan("make d3 check agents", ROOT).pipeline[0])

    def test_chaos_check_is_the_day3_check_and_a_chaos_run_is_not_a_read(self):
        argv = r.plan("make d3 check chaos", ROOT).pipeline[0]
        self.assertTrue(argv[3].endswith("ansible/playbooks/day3_check.yml"), argv)
        self.assertIn("target_component=chaos", argv)
        for command in ("make d3 chaos infra TIER=hog CHAOS_CONFIRM=infra", "make d3 chaos check",
                        "TIER=pods make d3 chaos infra"):
            with self.assertRaises(r.Denied, msg=command):
                r.plan(command, ROOT)

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


class Variables(unittest.TestCase):
    def test_resolved_from_the_step(self):
        p = r.plan("curl -s -o /dev/null -w '%{http_code}' $MAAS/v1/models", ROOT,
                   variables={"MAAS": "https://maas.apps.example.invalid"})
        self.assertIn("https://maas.apps.example.invalid/v1/models", p.pipeline[0])
        self.assertEqual(p.secrets, [])
        self.assertIn("$MAAS", p.display)

    def test_single_quotes_keep_dollars_literal(self):
        self.assertEqual(r.variables_of("oc get x | awk '{print $1, $(NF-1)}'"), [])
        self.assertEqual(r.variables_of("curl -H \"Authorization: Bearer $MAAS_API_KEY\" $MAAS/v1"),
                         ["MAAS", "MAAS_API_KEY"])

    def test_values_are_arguments_never_shell(self):
        p = r.plan("oc get pods -n $NS", ROOT, variables={"NS": "x; rm -rf /"})
        self.assertEqual(p.pipeline, [["oc", "get", "pods", "-n", "x; rm -rf /"]])

    def test_a_variable_cannot_smuggle_a_secret_read(self):
        ok, reason = r.check("oc get $KIND -n x", {"KIND": "secrets"})
        self.assertFalse(ok)
        self.assertIn("Secret", reason)

    def test_credential_values_are_masked(self):
        key = "sk-not-a-real-key-5678"
        plan = r.plan("curl -s -H \"Authorization: Bearer $MAAS_API_KEY\" https://example.invalid", ROOT,
                      variables={"MAAS_API_KEY": key})
        self.assertEqual(plan.secrets, [key])
        echo = r.Plan(plan.display, [[sys.executable, "-c", "import sys; print(sys.argv[1])", key]],
                      secrets=plan.secrets)
        result = r.run_plan(echo, cwd=ROOT)
        self.assertNotIn(key, result.output + result.log)
        self.assertIn("***", result.output)

    def test_environment_variables_for_run_reads(self):
        with mock.patch.dict("os.environ", {"ZUNO_DEMO_VARS": '{"MAAS": "https://m", "N": null}'}):
            self.assertEqual(r.env_variables(), {"MAAS": "https://m"})
        with mock.patch.dict("os.environ", {"ZUNO_DEMO_VARS": "not json"}):
            self.assertEqual(r.env_variables(), {})


class StripWatchFlags(unittest.TestCase):
    def test_watch_and_follow_are_stripped(self):
        self.assertEqual(r.strip_watch_flags("oc get llminferenceservice -n zuno-ai-run -w"),
                         ("oc get llminferenceservice -n zuno-ai-run", ["-w"]))
        self.assertEqual(r.strip_watch_flags("`oc logs -f deploy/x -n y | grep z`"),
                         ("oc logs deploy/x -n y | grep z", ["-f"]))
        self.assertEqual(r.strip_watch_flags("oc get pods --watch | tail -f"),
                         ("oc get pods | tail", ["--watch", "-f"]))

    def test_the_spaces_of_the_command_are_kept(self):
        awk = "git show HEAD:a.yaml | awk '/^  - name:/{n=$3} /^    eligible_for:/{print n, $2}'"
        self.assertEqual(r.strip_watch_flags(awk), (awk, []))
        self.assertEqual(r.strip_watch_flags("oc get pods -w | awk '/^a  b/'"), ("oc get pods | awk '/^a  b/'", ["-w"]))
        self.assertEqual(r.strip_watch_flags("oc get pods -n x  -w"), ("oc get pods -n x", ["-w"]))

    def test_never_raises_and_the_caller_judges(self):
        self.assertEqual(r.strip_watch_flags("oc get -f pod.yaml"), ("oc get -f pod.yaml", []))
        self.assertEqual(r.strip_watch_flags("oc delete pod x -w"), ("oc delete pod x -w", []))
        self.assertEqual(r.strip_watch_flags("oc get pods `id` -w"), ("oc get pods `id` -w", []))
        stripped, flags = r.strip_watch_flags("oc get externalsecrets -A -w | awk '{print $(NF-1)}'")
        self.assertEqual((stripped, flags), ("oc get externalsecrets -A | awk '{print $(NF-1)}'", ["-w"]))
        self.assertTrue(r.check(stripped)[0])


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

    def test_may_be_empty_only_forgives_a_final_grep_with_no_match(self):
        plain = r.run("git log -1 --format=%h | grep zuno-no-such-line", cwd=ROOT)
        self.assertEqual(plain.rc, 1)
        forgiven = r.run("git log -1 --format=%h | grep zuno-no-such-line", cwd=ROOT, may_be_empty=True)
        self.assertEqual(forgiven.rc, 0)
        self.assertIn("no line matched yet", forgiven.output)
        upstream_failure = r.run("git show zuno-no-such-ref-for-tests | grep x", cwd=ROOT, may_be_empty=True)
        self.assertNotEqual(upstream_failure.rc, 0)
        not_grep = r.run("git show zuno-no-such-ref-for-tests", cwd=ROOT, may_be_empty=True)
        self.assertNotEqual(not_grep.rc, 0)

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
