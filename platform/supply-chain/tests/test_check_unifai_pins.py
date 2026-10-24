"""ADR-0586: platform/supply-chain/check_unifai_pins.py.

Run from the repository root:
    python3 platform/supply-chain/tests/test_check_unifai_pins.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import check_unifai_pins as c  # noqa: E402

D = "@sha256:" + "a" * 64


def images(**over):
    out = {k: f"quay.io/zuno/unifai-{k}{D}" for k in c.APPLICATION_IMAGES}
    out.update(over)
    return {"zuno_unifai_values": {"stack": {"images": out}}}


class Pins(unittest.TestCase):
    def test_a_cluster_with_five_digests_passes(self):
        self.assertEqual(c.check_cluster("demo", images()), ([], []))

    def test_a_tag_fails_by_component(self):
        findings, _ = c.check_cluster("demo", images(ui="quay.io/zuno/unifai-ui:devel-1bb72a84d"))
        self.assertEqual(len(findings), 1)
        self.assertIn("stack.images.ui", findings[0])

    def test_a_missing_application_image_fails(self):
        doc = images()
        del doc["zuno_unifai_values"]["stack"]["images"]["rag"]
        findings, _ = c.check_cluster("demo", doc)
        self.assertTrue(any("stack.images.rag is missing" in f for f in findings))

    def test_a_version_alone_is_not_a_pin(self):
        findings, _ = c.check_cluster("demo", {"zuno_unifai_values": {"stack": {"version": "devel-1bb72a84d"}}})
        self.assertEqual(len(findings), len(c.APPLICATION_IMAGES))

    def test_a_listed_data_service_must_be_pinned_too(self):
        findings, _ = c.check_cluster("demo", images(qdrant="docker.io/qdrant/qdrant:v1.16.0"))
        self.assertEqual(len(findings), 1)
        self.assertIn("qdrant", findings[0])
        self.assertEqual(c.check_cluster("demo", images(qdrant="docker.io/qdrant/qdrant" + D)), ([], []))

    def test_switching_verification_off_is_a_visible_note_not_a_failure(self):
        doc = images(ui="quay.io/zuno/unifai-ui:devel-x")
        doc["zuno_unifai_verify_images"] = False
        findings, notes = c.check_cluster("demo", doc)
        self.assertEqual(findings, [])
        self.assertIn("not verified", notes[0])

    def test_a_cluster_with_no_unifai_values_is_ignored(self):
        self.assertEqual(c.check_cluster("other", {"zuno_build_git_ref": "devel"}), ([], []))

    def test_the_committed_clusters_pass(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        done = subprocess.run([sys.executable, str(root / "platform/supply-chain/check_unifai_pins.py")],
                              cwd=root, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout)


if __name__ == "__main__":
    unittest.main()
