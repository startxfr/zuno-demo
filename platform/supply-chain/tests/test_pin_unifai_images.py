"""ADR-0586: platform/supply-chain/pin_unifai_images.py (resolver and verifier are faked).

Run from the repository root:
    python3 platform/supply-chain/tests/test_pin_unifai_images.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pin_unifai_images as p  # noqa: E402
import verify_unifai_images as v  # noqa: E402

FILE = """# header comment
zuno_unifai_values:
  stack:
    images:
      # a third-party comment
      mongodb: docker.io/library/mongo@sha256:%s  # 8.0.3
      backend: quay.io/zuno/unifai-backend:devel-old
      identity: quay.io/zuno/unifai-identity@sha256:%s  # devel-old
      multiagent: quay.io/zuno/unifai-multiagent:devel-old
      rag: quay.io/zuno/unifai-rag:devel-old
      ui: quay.io/zuno/unifai-ui:devel-old
    rag:
      tokenReview: true
""" % ("a" * 64, "b" * 64)


def resolver(repo, tag):
    return "sha256:" + format(abs(hash(repo)) % (16 ** 8), "08x") * 8


def ok(refs, dev):
    return [v.Result(r, True, "ok") for r in refs]


def refuse_ui(refs, dev):
    return [v.Result(r, "unifai-ui" not in r, "no signatures found") for r in refs]


class Pin(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "demo.yml"
        self.path.write_text(FILE, encoding="utf-8")

    def test_five_digests_are_written_and_the_comments_survive(self):
        pins = p.pin("devel-ffb64e335", self.path, True, resolver=resolver, verifier=ok)
        text = self.path.read_text(encoding="utf-8")
        for component, ref in pins.items():
            self.assertIn(f"      {component}: {ref}  # devel-ffb64e335\n", text)
        self.assertIn("# header comment", text)
        self.assertIn("# a third-party comment", text)
        self.assertIn("mongodb: docker.io/library/mongo@sha256:" + "a" * 64 + "  # 8.0.3", text)
        self.assertNotIn("devel-old", text)

    def test_one_refused_image_changes_nothing(self):
        with self.assertRaises(p.PinError) as ctx:
            p.pin("devel-ffb64e335", self.path, True, resolver=resolver, verifier=refuse_ui)
        self.assertIn("unifai-ui", str(ctx.exception))
        self.assertEqual(self.path.read_text(encoding="utf-8"), FILE)

    def test_a_dev_build_needs_the_flag_and_a_bad_tag_is_refused(self):
        with self.assertRaises(p.PinError):
            p.pin("devel-ffb64e335", self.path, False, resolver=resolver, verifier=ok)
        with self.assertRaises(p.PinError):
            p.pin("latest", self.path, True, resolver=resolver, verifier=ok)
        self.assertEqual(self.path.read_text(encoding="utf-8"), FILE)

    def test_a_release_tag_needs_no_dev_flag(self):
        p.pin("v1.2.0", self.path, False, resolver=resolver, verifier=ok)
        self.assertIn("  # v1.2.0", self.path.read_text(encoding="utf-8"))

    def test_dry_run_writes_nothing(self):
        p.pin("devel-ffb64e335", self.path, True, dry_run=True, resolver=resolver, verifier=ok)
        self.assertEqual(self.path.read_text(encoding="utf-8"), FILE)

    def test_a_file_without_the_five_lines_is_refused(self):
        self.path.write_text("zuno_unifai_values: {}\n", encoding="utf-8")
        with self.assertRaises(p.PinError):
            p.pin("devel-ffb64e335", self.path, True, resolver=resolver, verifier=ok)

    def test_it_rewrites_the_committed_demo333_file_identically_when_pins_do_not_change(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        text = (root / "ansible/clusters/demo333.yml").read_text(encoding="utf-8")
        pins = {c: f"quay.io/zuno/unifai-{c}@sha256:" + "f" * 64 for c in p.APPLICATION_IMAGES}
        out = p.rewrite(text, pins, "devel-x")
        self.assertEqual(out.count("@sha256:" + "f" * 64), 5)


if __name__ == "__main__":
    unittest.main()
