"""ADR-0586: platform/supply-chain/pin_operator_catalog.py (resolver and verifier are faked).

Run from the repository root:
    python3 platform/supply-chain/tests/test_pin_operator_catalog.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pin_operator_catalog as p  # noqa: E402
import verify_unifai_images as v  # noqa: E402

OLD, NEW = "sha256:" + "1" * 64, "sha256:" + "2" * 64
FILE = """operator:
  # pin it by digest. Current: 0.1.39, the first release signed end to end (ADR-0586)
  catalogImage: quay.io/zuno/unifai-operator-catalog@%s
  catalogSourceName: unifai-operator-catalog
""" % OLD


def resolver(repo, tag):
    return {"latest": NEW}.get(tag, "sha256:" + format(abs(hash(repo + tag)) % (16 ** 8), "08x") * 8)


def ok(refs):
    return [v.Result(r, True, "ok") for r in refs]


def refuse_bundle(refs):
    return [v.Result(r, "bundle" not in r, "no signatures found") for r in refs]


class Pin(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "values.yaml"
        self.path.write_text(FILE, encoding="utf-8")

    def test_latest_is_resolved_verified_and_written_with_the_version_comment(self):
        refs = p.pin("latest", "0.1.40", self.path, resolver=resolver, verifier=ok)
        text = self.path.read_text(encoding="utf-8")
        self.assertIn(f"catalogImage: quay.io/zuno/unifai-operator-catalog@{NEW}\n", text)
        self.assertIn("Current: 0.1.40,", text)
        self.assertEqual(set(refs), {"catalog", "operator", "bundle"})
        self.assertNotIn(OLD, text)

    def test_a_digest_without_a_version_verifies_only_the_catalog(self):
        refs = p.pin(NEW, None, self.path, resolver=resolver, verifier=ok)
        self.assertEqual(set(refs), {"catalog"})
        self.assertIn("Current: 0.1.39,", self.path.read_text(encoding="utf-8"))

    def test_a_refused_image_changes_nothing(self):
        with self.assertRaises(p.PinError) as ctx:
            p.pin("latest", "0.1.40", self.path, resolver=resolver, verifier=refuse_bundle)
        self.assertIn("bundle", str(ctx.exception))
        self.assertEqual(self.path.read_text(encoding="utf-8"), FILE)

    def test_bad_arguments_are_refused(self):
        for target, version in (("sha256:abc", None), ("latest", "0.1"), ("v1", None)):
            with self.assertRaises(p.PinError):
                p.pin(target, version, self.path, resolver=resolver, verifier=ok)
        self.assertEqual(self.path.read_text(encoding="utf-8"), FILE)

    def test_dry_run_writes_nothing_and_a_file_without_the_line_is_refused(self):
        p.pin("latest", "0.1.40", self.path, dry_run=True, resolver=resolver, verifier=ok)
        self.assertEqual(self.path.read_text(encoding="utf-8"), FILE)
        self.path.write_text("operator: {}\n", encoding="utf-8")
        with self.assertRaises(p.PinError):
            p.pin("latest", None, self.path, resolver=resolver, verifier=ok)

    def test_it_rewrites_the_committed_chart(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        out = p.rewrite((root / "gitops/charts/unifai/values.yaml").read_text(encoding="utf-8"), NEW, "9.9.9")
        self.assertIn(f"unifai-operator-catalog@{NEW}", out)
        self.assertIn("Current: 9.9.9", out)


if __name__ == "__main__":
    unittest.main()
