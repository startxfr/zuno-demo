"""The terminal capture driver (evaluations/browser/terminal/capture.py, ADR-0618), offline: a real bash in a real
pty, harmless commands only, no cluster and no `oc`.

Run from the repository root:
    python3 evaluations/browser/tests/test_capture.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "evaluations/browser/terminal"))
sys.path.insert(0, str(ROOT / "platform/demo"))

import capture  # noqa: E402
import readonly  # noqa: E402

ANSI = re.compile(r"\x1b\][^\x07]*\x07|\x1b\[[0-9;?]*[A-Za-z]|\r")


def steps(*rows):
    return [capture.Step(time, [capture.Command(c) for c in commands]) for time, commands in rows]


class Capture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name) / "out"
        self.out.mkdir()
        self.home = pathlib.Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.env = capture.clean_env("/nowhere/kubeconfig", {"ZUNO_NS": "zuno-vault", "API_TOKEN": "s3cr3t-value-123"}, str(self.home))

    def tearDown(self):
        self.tmp.cleanup()

    def take(self, plan, values=(), **options):
        passed, detail = capture.capture("fixture", plan, self.out, self.env, list(values), cwd=ROOT, key_delay=0.002, **options)
        record = json.loads((self.out / "terminal-steps.json").read_text())
        cast = self.out / "terminal.cast"
        lines = [json.loads(line) for line in cast.read_text().splitlines()] if cast.exists() else []
        text = ANSI.sub("", "".join(event[2] for event in lines[1:]))
        return passed, detail, record, lines, text

    def test_a_session_is_its_bytes_and_its_instants(self):
        rows = steps(("0:00", ["echo hello from the pty"]), ("1:00", ["printf 'a\\nb\\n'", "echo $ZUNO_NS"]))
        passed, detail, record, lines, text = self.take(rows)
        self.assertTrue(passed, detail)
        self.assertEqual(lines[0]["version"], 2)
        self.assertEqual((lines[0]["width"], lines[0]["height"]), (100, 30))
        instants = [event[0] for event in lines[1:]]
        self.assertEqual(instants, sorted(instants))
        self.assertTrue(all(event[1] == "o" for event in lines[1:]))
        self.assertIn("$ echo hello from the pty\nhello from the pty\n", text)
        self.assertIn("$ printf 'a\\nb\\n'\na\nb\n", text)
        self.assertIn("zuno-vault", text)
        first, second = record["steps"]
        self.assertEqual((first["time"], second["time"]), ("0:00", "1:00"))
        self.assertLess(first["typed"], first["done"])
        self.assertLess(first["done"], second["typed"])
        self.assertEqual(second["typed"], second["commands"][0]["typed"])
        self.assertEqual(second["done"], second["commands"][1]["done"])
        self.assertEqual([c["rc"] for c in second["commands"]], [0, 0])
        self.assertEqual(record["status"], "done")

    def test_the_shell_is_clean(self):
        rows = steps(("0:00", ["echo home=$HOME user=[$USER] hist=[$HISTFILE] lang=$LC_ALL", "stty size", "pwd", "ls -a ~", "history"]))
        passed, detail, _, _, text = self.take(rows, clear=False)
        self.assertTrue(passed, detail)
        self.assertIn(f"home={self.home} user=[] hist=[/dev/null] lang=C.UTF-8", text)
        self.assertIn("\n30 100\n", text)
        self.assertIn(f"\n{ROOT}\n", text)
        self.assertNotIn(".bash_history", text)
        self.assertTrue(text.rstrip("$ ").endswith("$ history\n"), text[-80:])   # history is off: the command prints nothing
        self.assertEqual(set(self.env) - {"PYTHONUSERBASE"},
                         {"PATH", "TERM", "LC_ALL", "HOME", "PS1", "PS2", "INPUTRC", "HISTFILE", "KUBECONFIG", "ZUNO_NS", "API_TOKEN"})
        self.assertRegex(text, r"(?m)^\$ pwd$")   # the prompt is `$ `: no user, no host, no path

    def test_the_window_is_the_one_asked_for(self):
        passed, detail, record, lines, text = self.take(steps(("0:00", ["stty size"])), cols=136, rows=24)
        self.assertTrue(passed, detail)
        self.assertIn("\n24 136\n", text)
        self.assertEqual((lines[0]["width"], lines[0]["height"]), (136, 24))
        self.assertEqual((record["cols"], record["rows"]), (136, 24))

    def test_the_window_of_a_demo_comes_from_its_manifest_within_bounds(self):
        self.assertEqual(capture.window({}), (100, 30, []))
        self.assertEqual(capture.window({"kind": "terminal", "cols": 136, "rows": 24}), (136, 24, []))
        self.assertEqual(capture.window({"cols": 80, "rows": 40}), (80, 40, []))
        for bad in ({"cols": 79}, {"cols": 141}, {"rows": 19}, {"rows": 41}, {"cols": "120"}, {"cols": 120.5}, {"rows": True}):
            cols, rows, problems = capture.window(bad)
            self.assertEqual((cols, rows), (100, 30), bad)
            self.assertEqual(len(problems), 1, bad)
            self.assertIn("must be a whole number from", problems[0])

    def test_a_failing_command_fails_the_take_and_keeps_its_exit_code(self):
        passed, detail, record, lines, _ = self.take(steps(("0:00", ["false", "echo after"])))
        self.assertFalse(passed)
        self.assertIn("`false` (row 0:00) ended with exit code 1", detail)
        self.assertEqual([c["rc"] for c in record["steps"][0]["commands"]], [1, 0])
        self.assertTrue(lines)   # nothing private was printed: the cast is kept for the reader

    def test_a_command_that_does_not_finish_is_stopped(self):
        passed, detail, record, _, _ = self.take(steps(("0:00", ["sleep 30"])), timeout=1.5)
        self.assertFalse(passed)
        self.assertIn("`sleep 30` (row 0:00) did not finish within 1 s", detail)
        self.assertIsNone(record["steps"][0]["commands"][0]["rc"])

    def test_a_printed_local_value_refuses_the_take_and_writes_no_cast(self):
        values = capture.local_values("/nowhere/kubeconfig", {"API_TOKEN": "s3cr3t-value-123"}, "sha256~presenter-token")
        passed, detail, record, lines, _ = self.take(steps(("0:00", ["echo $API_TOKEN"])), values)
        self.assertFalse(passed)
        self.assertIn("the session printed the value of $API_TOKEN: the cast is not written", detail)
        self.assertEqual(lines, [])
        self.assertFalse((self.out / "terminal.cast").exists())
        self.assertNotIn("s3cr3t-value-123", (self.out / "terminal-steps.json").read_text())
        self.assertEqual(record["status"], "fail")

    def test_local_values_are_found_as_text(self):
        values = [("the presenter's token", "sha256~abcDEF123", False), ("the home directory", "/home/someone", False),
                  ("the login name", "cl", True), ("the workstation's host name", "box7", True)]
        self.assertEqual(capture.printed("NAME cluster-autoscaler include cl-01 oc", values), [])
        self.assertEqual(capture.printed("error: open /home/someone/.kube/cache: denied", values), ["the home directory"])
        self.assertEqual(capture.printed("logged in as cl on box7", values), ["the login name", "the workstation's host name"])
        self.assertEqual(capture.printed("Authorization: Bearer sha256~abcDEF123", values), ["the presenter's token"])


class WhatMayBeTyped(unittest.TestCase):
    def accept(self, command, allow=()):
        return capture.acceptable(command, list(allow), lambda c: readonly.check(c, {}))

    def test_a_read_only_command_is_typed_verbatim(self):
        for command in ("oc get pods -n zuno-vault -L vault-sealed,vault-active,vault-version",
                        "oc get externalsecrets -A --no-headers | awk '{print $(NF-1)}' | sort | uniq -c"):
            self.assertEqual(self.accept(command), (command, ""))

    def test_a_command_outside_the_allowlist_needs_the_demo_list(self):
        typed, why = self.accept("oc delete pod x -n zuno-vault")
        self.assertEqual(typed, "")
        self.assertIn("refused by the read-only allowlist", why)
        self.assertIn("record: {allow: [...]}", why)
        self.assertEqual(self.accept("oc delete pod x -n zuno-vault", ["oc delete pod x -n zuno-vault"])[1], "")

    def test_some_commands_are_never_typed_whatever_the_list_says(self):
        for command in ("oc whoami -t", "oc whoami --show-token", "oc config view --raw", "env", "printenv PATH",
                        "oc get pods | env", "cat ~/.kube/config", "cat $KUBECONFIG", "echo $HOME", "set"):
            typed, why = self.accept(command, [command])
            self.assertEqual(typed, "", command)
            self.assertIn("never typed", why, command)

    def test_a_make_command_needs_its_exact_string_in_the_demo_list(self):
        for command in ("make help", "ONLY=sovereignty make demo golden-path", "make d0 check argocd",
                        "oc get pods | make -s x", "cd /tmp && make all", "A=1 B=2 /usr/bin/make help"):
            self.assertTrue(capture.runs_make(command), command)
            typed, why = self.accept(command)
            self.assertEqual(typed, "", command)
            self.assertIn("a `make` command, typed only when demo.yml lists this exact command", why)
            self.assertEqual(self.accept(command, [command]), (command, ""))
        golden = "ONLY=sovereignty make demo golden-path"
        self.assertTrue(readonly.check(golden, {})[0])      # readonly.py accepts it: the capture is stricter
        self.assertEqual(self.accept(golden, ["make demo golden-path"])[0], "")   # nothing wider, nothing else
        self.assertEqual(self.accept(golden, ["ONLY=trace make demo golden-path"])[0], "")
        for command in ("oc get pods | grep make", "cmake --version", "echo make", "oc get cm makefile -n x"):
            self.assertFalse(capture.runs_make(command), command)

    def test_the_token_substitution_stays_runnable(self):
        command = 'curl -s -H "Authorization: Bearer $(oc whoami -t)" https://tempo.example/api/search'
        self.assertEqual(capture.never(command), "")
        self.assertEqual(capture.never("oc whoami"), "")

    def test_plan_needs_no_out_dir_and_runs_nothing(self):
        import contextlib
        import io
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = capture.main(["vault-pki", "--plan"])
        self.assertEqual(code, 0)
        lines = printed.getvalue().splitlines()
        self.assertEqual(lines[0], "0:00  $ oc get pods -n zuno-vault -L vault-sealed,vault-active,vault-version")
        self.assertEqual(len(lines), 6)

    def test_a_demo_that_needs_the_cluster_domain_does_not_plan_without_it(self):
        import shutil
        import subprocess as sp
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for rel in ("docs/demo", "ansible/demos/vault-pki", "platform/demo"):
                shutil.copytree(ROOT / rel, root / rel)
            manifest = root / "ansible/demos/vault-pki/demo.yml"
            manifest.write_text(manifest.read_text() + 'env: {VAULT_URL: "https://vault.{{ cluster_base_domain }}"}\n')
            real = sp.run
            capture.subprocess.run = lambda *a, **k: sp.CompletedProcess(a, 1, "", "")   # oc gives nothing
            try:
                with self.assertRaises(capture.NoDomain):
                    capture.demo_steps("vault-pki", root)
            finally:
                capture.subprocess.run = real

    def test_skipped_rows_are_read_and_checked(self):
        rows = [("0:00", True), ("1:00", True), ("3:00", True), ("4:15", False)]
        self.assertEqual(capture.skips({}, rows), ({}, []))
        self.assertEqual(capture.skips({"skip": {"3:00": " prints the checkout path "}}, rows),
                         ({"3:00": "prints the checkout path"}, []))
        self.assertEqual(capture.skips({"skip": {180: "unquoted 3:00"}}, rows)[0], {"3:00": "unquoted 3:00"})
        for skip, says in (({"2:00": "x"}, "not a time of the 5-minute version"),
                           ({"4:15": "x"}, "a row with no Do command"),
                           ({"3:00": "  "}, "one phrase"), ({"3:00": "two\nlines"}, "one phrase"),
                           ({"3:00": 7}, "one phrase"), (["3:00"], "must be a mapping"), ({}, "must be a mapping")):
            found, problems = capture.skips({"skip": skip}, rows)
            self.assertEqual(found, {}, skip)
            self.assertEqual(len(problems), 1, skip)
            self.assertIn(says, problems[0], skip)

    def test_a_skipped_row_is_not_typed_and_not_checked(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for rel in ("docs/demo", "ansible/demos/vault-pki", "platform/demo"):
                shutil.copytree(ROOT / rel, root / rel)
            manifest = root / "ansible/demos/vault-pki/demo.yml"
            manifest.write_text(manifest.read_text() + '  skip: {"2:15": "a reason in one phrase"}\n')
            rows, _, problems = capture.demo_steps("vault-pki", root)
            self.assertEqual(problems, [])
            self.assertEqual([row.time for row in rows], ["0:00", "1:00", "3:15"])
            self.assertEqual(capture.demo_skips("vault-pki", root), ({"2:15": "a reason in one phrase"}, []))
            # A skipped row is not checked: a refused command there does not stop the take.
            page = next((root / "docs/demo").rglob("vault-pki.md"))
            text = page.read_text()
            start = text.index("| 2:15 | ")
            page.write_text(text[:start] + "| 2:15 | `oc delete pod x -n zuno-vault` | \"x\" | x |\n"
                            + text[text.index("\n", start) + 1:])
            rows, _, problems = capture.demo_steps("vault-pki", root)
            self.assertEqual((problems, [row.time for row in rows]), ([], ["0:00", "1:00", "3:15"]))
            manifest.write_text(manifest.read_text().replace('"2:15"', '"2:16"'))
            problems = capture.demo_steps("vault-pki", root)[2]
            self.assertTrue(any("names 2:16, which is not a time" in p for p in problems), problems)
            self.assertTrue(any("`oc delete pod x -n zuno-vault` is refused" in p for p in problems), problems)

    def test_the_first_terminal_demo_plans_offline(self):
        rows, variables, problems = capture.demo_steps("vault-pki", ROOT)
        self.assertEqual(problems, [])
        self.assertEqual([row.time for row in rows], ["0:00", "1:00", "2:15", "3:15"])
        self.assertEqual(rows[0].commands[0].cmd, "oc get pods -n zuno-vault -L vault-sealed,vault-active,vault-version")
        self.assertEqual(len(rows[1].commands), 2)


if __name__ == "__main__":
    unittest.main()
