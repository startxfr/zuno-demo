"""ADR-0586: platform/supply-chain/verify_unifai_images.py with a fake cosign.

Run from the repository root:
    python3 platform/supply-chain/tests/test_verify_unifai_images.py
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import admit_okf_bundle as admit  # noqa: E402
import verify_unifai_images as v  # noqa: E402

D1, D2 = "sha256:" + "a" * 64, "sha256:" + "b" * 64
UI = f"quay.io/zuno/unifai-ui@{D1}"
OPERATOR = f"quay.io/zuno/unifai-operator@{D2}"
CATALOG = f"quay.io/zuno/unifai-operator-catalog@{D2}"
TAGGED = "quay.io/zuno/unifai-ui:devel-1bb72a84d"
PUBLISH = "https://github.com/startxfr/UnifAI/.github/workflows/publish-images.yml"
OPERATOR_WF = "https://github.com/startxfr/UnifAI/.github/workflows/unifai-operator-release.yml"


class FakeCosign:
    """Stands in for admit.run/require/offline_trust: it records every cosign call and answers
    like a registry holding one signer identity per reference."""

    def __init__(self, signer=None, missing=()):
        # signer: {reference: certificate identity}; missing: {(reference, 'verify'|'verify-attestation'|type)}
        self.signer = dict(signer or {})
        # the SBOM of an image is a signed artifact at its own reference
        for ref, who in list(self.signer.items()):
            if v.DIGEST_RE.search(ref):
                self.signer[v.sbom_reference(ref)] = who
        self.missing = {(v.sbom_reference(r) if k == "sbom" else r, k) for r, k in missing}
        self.calls = []

    def run(self, args, env=None, cwd=None):
        self.calls.append(args)
        sub = args[1]
        ref = args[args.index("--offline") + 1]
        kind = args[args.index("--type") + 1] if "--type" in args else sub
        if ref.endswith(".sbom"):
            kind = "sbom"
        if (ref, kind) in self.missing or (ref, sub) in self.missing:
            raise admit.AdmissionError(f"cosign {sub} failed: no matching signatures")
        identity = self.signer.get(ref)
        regexp = args[args.index("--certificate-identity-regexp") + 1]
        if identity is None or not re.search(regexp, identity):
            raise admit.AdmissionError(f"cosign {sub} failed: none of the expected identities matched")
        return "{}"

    @contextlib.contextmanager
    def install(self):
        saved = (admit.run, admit.require, admit.offline_trust)
        admit.run, admit.require = self.run, lambda b: b

        @contextlib.contextmanager
        def trust():
            yield {}

        admit.offline_trust = trust
        try:
            yield self
        finally:
            admit.run, admit.require, admit.offline_trust = saved


ident = v.load_identities()


class Pinning(unittest.TestCase):
    def test_a_tag_is_refused_as_unpinned_without_calling_cosign(self):
        fake = FakeCosign()
        with fake.install():
            result = v.verify_all([TAGGED])[0]
        self.assertFalse(result.ok)
        self.assertIn("not pinned by digest", result.reason)
        self.assertEqual(fake.calls, [])

    def test_a_tag_with_a_digest_is_pinned(self):
        ref = f"quay.io/zuno/unifai-ui:devel-1bb72a84d@{D1}"
        fake = FakeCosign({ref: PUBLISH + "@refs/tags/v1.2.0"})
        with fake.install():
            self.assertTrue(v.verify_all([ref])[0].ok)

    def test_a_foreign_image_is_out_of_policy(self):
        with FakeCosign().install():
            result = v.verify_all([f"docker.io/library/mongo@{D1}"])[0]
        self.assertFalse(result.ok)
        self.assertIn("not an UnifAI image", result.reason)

    def test_the_repository_of_a_reference_ignores_tag_digest_and_registry_port(self):
        self.assertEqual(v.repository(f"quay.io/zuno/unifai-ui:t@{D1}"), "quay.io/zuno/unifai-ui")
        self.assertEqual(v.repository("localhost:5000/zuno/unifai-ui"), "localhost:5000/zuno/unifai-ui")


class ThirdPartyDrift(unittest.TestCase):
    MONGO = "docker.io/library/mongo@sha256:" + "c" * 64
    MONGO7 = "docker.io/library/mongo@sha256:" + "d" * 64

    @staticmethod
    def pods(*images, phase="Running", init=()):
        return {"items": [{"metadata": {"name": f"p{i}"}, "status": {"phase": phase},
                           "spec": {"containers": [{"image": img}], "initContainers": [{"image": x} for x in init]}}
                          for i, img in enumerate(images)]}

    def test_a_pod_running_a_pinned_reference_is_clean(self):
        self.assertEqual(v.check_third_party(self.pods(self.MONGO, init=[self.MONGO7]), [self.MONGO, self.MONGO7]), [])

    def test_a_tag_or_another_digest_of_a_pinned_repository_is_drift(self):
        for image in ("docker.io/library/mongo:8.0.3", "docker.io/library/mongo@sha256:" + "e" * 64):
            findings = v.check_third_party(self.pods(image), [self.MONGO])
            self.assertEqual(len(findings), 1, image)
            self.assertIn("drift", findings[0])

    def test_an_unrelated_image_and_ended_pods_are_ignored(self):
        self.assertEqual(v.check_third_party(self.pods("quay.io/other/x:1"), [self.MONGO]), [])
        self.assertEqual(v.check_third_party(self.pods("docker.io/library/mongo:old", phase="Succeeded"), [self.MONGO]), [])

    def test_the_cli_reports_third_party_drift(self):
        fake = FakeCosign({UI: PUBLISH + "@refs/heads/devel"})
        path = pathlib.Path(tempfile.mkdtemp()) / "pods.json"
        path.write_text(json.dumps(self.pods("docker.io/library/mongo:8.0.3")))
        out = io.StringIO()
        with fake.install(), contextlib.redirect_stdout(out):
            code = v.main(["--ref", UI, "--accept-dev", "--pods", str(path), "--third-party", self.MONGO])
        report = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertTrue(report["results"][0]["ok"])
        self.assertEqual(len(report["pod_findings"]), 1)


class Identities(unittest.TestCase):
    def verify(self, ref, signer, accept_dev=False, missing=()):
        fake = FakeCosign({ref: signer}, missing)
        with fake.install():
            return v.verify_all([ref], accept_dev=accept_dev)[0], fake

    def test_a_release_signature_is_accepted_and_all_three_proofs_are_checked(self):
        result, fake = self.verify(UI, PUBLISH + "@refs/tags/v1.2.0")
        self.assertTrue(result.ok, result.reason)
        self.assertEqual([c[1] for c in fake.calls], ["verify", "verify-attestation", "verify"])
        types = [c[c.index("--type") + 1] for c in fake.calls if "--type" in c]
        self.assertEqual(types, ["https://slsa.dev/provenance/v1"])
        self.assertEqual(fake.calls[2][fake.calls[2].index("--offline") + 1],
                         f"quay.io/zuno/unifai-ui:sha256-{'a' * 64}.sbom")
        self.assertTrue(all("--offline" in c for c in fake.calls))

    def test_a_devel_signature_needs_the_explicit_opt_in(self):
        signer = PUBLISH + "@refs/heads/devel"
        refused, _ = self.verify(UI, signer, accept_dev=False)
        self.assertFalse(refused.ok)
        self.assertIn("signature", refused.reason)
        self.assertTrue(self.verify(UI, signer, accept_dev=True)[0].ok)

    def test_another_branch_or_another_workflow_or_another_repository_is_refused(self):
        for signer in (PUBLISH + "@refs/heads/feature/x", PUBLISH.replace("publish-images", "other") + "@refs/heads/devel",
                       PUBLISH.replace("startxfr/UnifAI", "someone/UnifAI") + "@refs/tags/v1.0.0"):
            self.assertFalse(self.verify(UI, signer, accept_dev=True)[0].ok, signer)

    def test_the_operator_images_take_only_the_operator_release_identity(self):
        for ref in (OPERATOR, CATALOG):
            self.assertTrue(self.verify(ref, OPERATOR_WF + "@refs/tags/operator-v0.1.35")[0].ok, ref)
            self.assertFalse(self.verify(ref, PUBLISH + "@refs/tags/v1.0.0")[0].ok, ref)
            self.assertFalse(self.verify(ref, OPERATOR_WF + "@refs/heads/devel", accept_dev=True)[0].ok, ref)

    def test_a_missing_provenance_or_sbom_is_refused_by_name(self):
        signer = PUBLISH + "@refs/tags/v1.0.0"
        for missing, label in (("https://slsa.dev/provenance/v1", "provenance"), ("sbom", "sbom")):
            result, _ = self.verify(UI, signer, missing=[(UI, missing)])
            self.assertFalse(result.ok)
            self.assertTrue(result.reason.startswith(label), result.reason)

    def test_an_unsigned_image_is_refused(self):
        with FakeCosign({}).install():
            result = v.verify_all([UI])[0]
        self.assertFalse(result.ok)
        self.assertIn("signature", result.reason)

    def test_every_failure_is_reported_not_only_the_first(self):
        fake = FakeCosign({UI: PUBLISH + "@refs/tags/v1.0.0"})
        with fake.install():
            results = v.verify_all([TAGGED, UI, f"quay.io/zuno/unifai-rag@{D2}"])
        self.assertEqual([r.ok for r in results], [False, True, False])

    def test_the_committed_identities_name_the_forks_workflow(self):
        self.assertEqual(ident["issuer"], "https://token.actions.githubusercontent.com")
        for section in ("images", "operator"):
            self.assertIn("startxfr/UnifAI", ident[section]["release_subject_regexp"].replace("\\", ""))
        self.assertNotIn("dev_subject_regexp", ident["operator"])


class Pods(unittest.TestCase):
    def pods(self, *image_ids):
        return {"items": [{"metadata": {"name": f"p{i}"}, "status": {"containerStatuses": [{"imageID": iid}]}}
                          for i, iid in enumerate(image_ids)]}

    def ok(self, ref):
        return v.Result(ref, True)

    def test_the_running_references_keep_only_unifai_images_once(self):
        pods = self.pods(f"quay.io/zuno/unifai-ui@{D1}", f"docker-pullable://quay.io/zuno/unifai-ui@{D1}",
                         f"docker.io/library/mongo@{D2}", "quay.io/zuno/unifai-ui:no-digest")
        self.assertEqual(v._running_references(pods)[0], f"quay.io/zuno/unifai-ui@{D1}")
        self.assertEqual(len(v._running_references(pods)), 1)

    def test_a_pod_on_a_pinned_verified_digest_is_clean(self):
        self.assertEqual(v.check_pods(self.pods(UI), {D1}, self.ok), [])

    def test_a_pod_on_another_digest_is_drift(self):
        findings = v.check_pods(self.pods(f"quay.io/zuno/unifai-ui@{D2}"), {D1}, self.ok)
        self.assertEqual(len(findings), 1)
        self.assertIn("drift", findings[0])

    def test_a_running_image_that_does_not_verify_is_a_finding(self):
        bad = lambda ref: v.Result(ref, False, "signature: none of the expected identities matched")  # noqa: E731
        findings = v.check_pods(self.pods(UI), {D1}, bad)
        self.assertEqual(len(findings), 1)
        self.assertIn("signature", findings[0])

    def test_the_operator_pod_is_verified_but_not_compared_to_the_pins(self):
        self.assertEqual(v.check_pods(self.pods(OPERATOR), {D1}, self.ok), [])
        bad = lambda ref: v.Result(ref, False, "unsigned")  # noqa: E731
        self.assertEqual(len(v.check_pods(self.pods(OPERATOR), {D1}, bad)), 1)


class Cli(unittest.TestCase):
    def run_main(self, argv, stdin=None):
        out, saved = io.StringIO(), sys.stdout
        sys.stdout = out
        if stdin is not None:
            saved_in, sys.stdin = sys.stdin, io.StringIO(stdin)
        try:
            code = v.main(argv)
        finally:
            sys.stdout = saved
            if stdin is not None:
                sys.stdin = saved_in
        return code, json.loads(out.getvalue())

    def test_exit_codes_and_json(self):
        fake = FakeCosign({UI: PUBLISH + "@refs/tags/v1.0.0"})
        with fake.install():
            code, doc = self.run_main(["--ref", UI])
            self.assertEqual((code, doc["ok"]), (0, True))
            code, doc = self.run_main(["--ref", UI, "--ref", TAGGED])
            self.assertEqual((code, doc["ok"]), (1, False))
            self.assertEqual([r["ok"] for r in doc["results"]], [True, False])

    def test_pods_from_stdin_with_pins_from_refs(self):
        fake = FakeCosign({UI: PUBLISH + "@refs/tags/v1.0.0"})
        with fake.install():
            code, doc = self.run_main(["--ref", UI, "--pods", "-"],
                                      stdin=json.dumps(Pods().pods(f"quay.io/zuno/unifai-ui@{D1}")))
        self.assertEqual((code, doc["pod_findings"]), (0, []))

    def test_no_reference_is_a_usage_error(self):
        with FakeCosign().install(), self.assertRaises(SystemExit) as caught:
            self.run_main([])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
