"""WP-178: platform/supply-chain/admission_preflight.py (the `oc` calls are faked).

Run from the repository root:
    python3 platform/supply-chain/tests/test_admission_preflight.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import admission_preflight as a  # noqa: E402

SIGNED = "quay.io/zuno/unifai-ui@sha256:" + "a" * 64
UNSIGNED = "quay.io/zuno/unifai-ui@sha256:" + "b" * 64
REKOR_V2 = "quay.io/zuno/unifai-ui@sha256:" + "c" * 64
PODSEC = 'Warning: would violate PodSecurity "restricted:latest": allowPrivilegeEscalation != false\n'


def cp(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class FakeOc:
    def __init__(self, labelled=True, namespace_rc=0):
        self.labelled, self.namespace_rc, self.calls = labelled, namespace_rc, []

    def __call__(self, args, stdin=None):
        self.calls.append((args, stdin))
        if args[:3] == ["oc", "get", "namespace"]:
            labels = {a.OPT_IN_LABEL: "true"} if self.labelled else {}
            return cp(self.namespace_rc, json.dumps({"metadata": {"labels": labels}}), "" if self.namespace_rc == 0 else "boom")
        image = json.loads(stdin)["spec"]["containers"][0]["image"]
        if image == UNSIGNED:
            return cp(0, "pod/x created (server dry run)", PODSEC + "Warning: failed policy: zuno-unifai-images: spec.containers[0].image\n"
                      f"Warning: {image} signature keyless validation failed for authority github-keyless: no signatures found\n")
        if image == REKOR_V2:
            return cp(1, "", 'Error from server (BadRequest): admission webhook "policy.rhtas.com" denied the request: validation failed: failed policy: x\n')
        return cp(0, "pod/x created (server dry run)", PODSEC)


class Preflight(unittest.TestCase):
    def test_a_signed_image_is_admitted_and_the_podsecurity_noise_is_ignored(self):
        results = a.preflight([SIGNED], FakeOc())
        self.assertTrue(results[0].ok, results[0].reason)

    def test_a_warning_or_a_refusal_is_reported_with_the_webhooks_words(self):
        results = a.preflight([SIGNED, UNSIGNED, REKOR_V2], FakeOc())
        self.assertEqual([r.ok for r in results], [True, False, False])
        self.assertIn("no signatures found", results[1].reason)
        self.assertIn("denied the request", results[2].reason)

    def test_the_dry_run_pod_names_the_image_and_the_namespace(self):
        oc = FakeOc()
        a.preflight([SIGNED], oc)
        args, stdin = oc.calls[-1]
        self.assertIn("--dry-run=server", args)
        pod = json.loads(stdin)
        self.assertEqual(pod["metadata"]["namespace"], a.NAMESPACE)
        self.assertEqual(pod["spec"]["containers"][0]["image"], SIGNED)

    def test_a_namespace_that_is_not_opted_in_proves_nothing(self):
        with self.assertRaises(a.PreflightUnavailable) as ctx:
            a.preflight([SIGNED], FakeOc(labelled=False))
        self.assertIn("not opted in", str(ctx.exception))

    def test_an_unreachable_cluster_is_unavailable_never_a_pass(self):
        with self.assertRaises(a.PreflightUnavailable):
            a.preflight([SIGNED], FakeOc(namespace_rc=1))

        def broken(args, stdin=None):
            if args[:3] == ["oc", "get", "namespace"]:
                return FakeOc()(args, stdin)
            return cp(1, "", "Unable to connect to the server: dial tcp: i/o timeout")
        with self.assertRaises(a.PreflightUnavailable):
            a.preflight([SIGNED], broken)

    def test_run_or_skip_skips_with_a_notice_and_when_disabled(self):
        notes = []
        self.assertEqual(a.run_or_skip([SIGNED], runner=FakeOc(labelled=False), log=notes.append), [])
        self.assertTrue(notes and "skipped" in notes[0])
        self.assertEqual(a.run_or_skip([SIGNED], enabled=False, runner=FakeOc(), log=notes.append), [])
        self.assertEqual(len(notes), 1)
        self.assertTrue(a.run_or_skip([SIGNED], runner=FakeOc(), log=notes.append)[0].ok)


if __name__ == "__main__":
    unittest.main()
