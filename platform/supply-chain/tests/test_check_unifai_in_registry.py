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


if __name__ == "__main__":
    unittest.main()
