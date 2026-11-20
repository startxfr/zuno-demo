"""Tests for check_unifai_in_registry (WP-248): copy before pin. The registry is faked, nothing real is called."""
import json
import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import admit_okf_bundle as admit  # noqa: E402
import check_unifai_in_registry as c  # noqa: E402

D = "a" * 64
REF = f"quay.io/zuno/unifai-rag@sha256:{D}"
PREFIX = "quay.example/zuno"


class CheckTests(unittest.TestCase):
    def fake(self, image=True, sig=True, wrong=False):
        def run(args, env=None, cwd=None):
            target = args[-1]
            if target.endswith(".sig"):
                if not sig:
                    raise admit.AdmissionError("not found")
                return "{}"
            if not image:
                raise admit.AdmissionError("not found")
            return json.dumps({"digest": "sha256:" + ("b" * 64 if wrong else D)})
        return run

    def check(self, **kw):
        with mock.patch.object(admit, "require", return_value="oras"):
            return c.check_ref(REF, PREFIX, self.fake(**kw))

    def test_present_with_signature_is_ok(self):
        self.assertTrue(self.check()["ok"])

    def test_missing_image_is_named(self):
        r = self.check(image=False)
        self.assertFalse(r["ok"])
        self.assertIn("is not in the registry", r["reason"])

    def test_image_without_signature_tag_is_refused(self):
        r = self.check(sig=False)
        self.assertFalse(r["ok"])
        self.assertIn(f"sha256-{D}.sig", r["reason"])

    def test_a_wrong_digest_from_the_registry_is_refused(self):
        self.assertFalse(self.check(wrong=True)["ok"])

    def test_a_tag_only_reference_is_refused_and_third_party_is_skipped(self):
        with mock.patch.object(admit, "require", return_value="oras"):
            out = c.check_refs(["quay.io/zuno/unifai-rag:0.1.69", "docker.io/library/mongo@sha256:" + D], PREFIX, self.fake())
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0]["ok"])


class PinGateTests(unittest.TestCase):
    """WP-282: the pin scripts check the registry before they write, and copy what is missing with --mirror-to."""

    def registry(self, held):
        """A fake registry holding the digests in `held` (a set it can grow), each with its .sig tag."""
        def run(args, env=None, cwd=None):
            target = args[-1]
            digest = target.split("@", 1)[1] if "@" in target else "sha256:" + target.rsplit(":", 1)[1][len("sha256-"):-len(".sig")]
            if digest not in held:
                raise admit.AdmissionError("not found")
            return json.dumps({"digest": digest}) if "@" in target else "{}"
        return run

    def cluster_file(self, body):
        import tempfile
        path = pathlib.Path(tempfile.mkdtemp()) / "c.yml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_the_prefix_comes_from_the_cluster_file(self):
        self.assertEqual(c.mirror_prefix(self.cluster_file("zuno_unifai_signature_mirror_host: quay.example/\n")),
                         "quay.example/zuno")
        for body in ("zuno_unifai_signature_mirror_host: ''\n", "other: 1\n", ""):
            self.assertEqual(c.mirror_prefix(self.cluster_file(body)), "")

    def test_the_committed_demo333_file_reads_the_internal_quay(self):
        root = HERE.parents[2]
        self.assertTrue(c.mirror_prefix(root / "ansible" / "inventories" / "demo333" / "cluster.yml").endswith("/zuno"))

    def test_a_cluster_that_reads_quay_io_gets_no_gate_and_a_notice(self):
        seen = []
        self.assertIsNone(c.pin_gate(self.cluster_file("other: 1\n"), log=seen.append))
        self.assertIn("no internal registry check", seen[0])

    def test_without_a_copy_the_missing_digests_are_reported(self):
        other = "sha256:" + "c" * 64
        refs = [REF, f"quay.io/zuno/unifai-operator@{other}"]
        with mock.patch.object(admit, "require", return_value="oras"):
            out = c.gate(PREFIX, run=self.registry({"sha256:" + D}))(refs)
        self.assertEqual([r["ok"] for r in out], [True, False])
        message = c.refusal([r for r in out if not r["ok"]])
        self.assertIn(f"unifai-operator@{other}", message)
        self.assertIn("--mirror-to", message)
        self.assertIn("nothing was written", message)

    def test_a_copy_gets_only_the_missing_digests_then_they_are_checked_again(self):
        other = "sha256:" + "c" * 64
        held = {"sha256:" + D}
        copied = []

        def copy(refs):
            copied.extend(refs)
            held.update(r.split("@", 1)[1] for r in refs)

        refs = [REF, f"quay.io/zuno/unifai-operator@{other}"]
        with mock.patch.object(admit, "require", return_value="oras"):
            out = c.gate(PREFIX, copy=copy, run=self.registry(held))(refs)
        self.assertEqual(copied, [f"quay.io/zuno/unifai-operator@{other}"])
        self.assertTrue(all(r["ok"] for r in out))

    def test_a_copy_that_does_not_land_is_still_reported(self):
        other = "sha256:" + "c" * 64
        with mock.patch.object(admit, "require", return_value="oras"):
            out = c.gate(PREFIX, copy=lambda refs: None, run=self.registry(set()))([f"quay.io/zuno/unifai-operator@{other}"])
        self.assertFalse(out[0]["ok"])

    def test_a_dry_run_never_copies(self):
        path = self.cluster_file("zuno_unifai_signature_mirror_host: quay.example\n")
        with mock.patch.object(c, "gate", side_effect=lambda prefix, copy=None: copy) as built:
            self.assertIsNone(c.pin_gate(path, mirror_to="quay.example/zuno", dry_run=True))
            self.assertIsNotNone(c.pin_gate(path, mirror_to="quay.example/zuno", dry_run=False))
        self.assertEqual(built.call_args_list[0].args[0], "quay.example/zuno")


if __name__ == "__main__":
    unittest.main()
