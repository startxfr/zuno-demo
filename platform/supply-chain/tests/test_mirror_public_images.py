"""Tests for mirror_public_images (WP-248 family d): the list is closed, tags wait, a digest mismatch is refused."""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import mirror_public_images as m  # noqa: E402

D = "sha256:" + "a" * 64


def item(source="docker.io/hashicorp/vault", pin="digest", digest=D, tag=None):
    return {"source": source, "pin": pin, "digest": digest, "tag": tag, "signature": "none", "reason": "test"}


class ListTests(unittest.TestCase):
    def test_the_committed_list_is_valid(self):
        images = m.load_list()
        self.assertGreater(len(images), 10)
        self.assertTrue(all(i["signature"] == "none" for i in images))

    def write(self, text):
        d = tempfile.mkdtemp()
        p = pathlib.Path(d) / "l.yaml"
        p.write_text(text)
        return p

    def test_refuses_an_entry_without_reason_or_with_a_bad_digest(self):
        with self.assertRaises(m.ListError):
            m.load_list(self.write("images:\n  - {source: a.io/x/y, pin: digest, digest: sha256:aa, signature: none, reason: r}\n"))
        with self.assertRaises(m.ListError):
            m.load_list(self.write("images:\n  - {source: a.io/x/y, pin: tag, tag: v1, signature: none}\n"))

    def test_refuses_a_duplicate(self):
        row = f"  - {{source: a.io/x/y, pin: digest, digest: {D}, signature: none, reason: r}}\n"
        with self.assertRaises(m.ListError):
            m.load_list(self.write("images:\n" + row + row))


class MirrorTests(unittest.TestCase):
    def test_path_drops_the_registry_host(self):
        self.assertEqual(m.mirror_target("docker.io/hashicorp/vault", "h.example"), "h.example/zuno/mirror/hashicorp/vault")
        self.assertEqual(m.mirror_target("ghcr.io/kagent-dev/kagent/ui", "h.example"), "h.example/zuno/mirror/kagent-dev/kagent/ui")

    def test_tags_wait_and_are_not_copied(self):
        copied = []
        out = m.mirror_all([item(), item("docker.io/library/python", "tag", None, "3.12-slim")], "h.example",
                           copy=lambda i, h: copied.append(i["source"]) or "x")
        self.assertEqual(copied, ["docker.io/hashicorp/vault"])
        self.assertEqual(out["waiting_for_a_digest_pin"], ["docker.io/library/python:3.12-slim"])

    def test_dry_run_copies_nothing(self):
        out = m.mirror_all([item()], "h.example", dry_run=True, copy=lambda i, h: self.fail("copied"))
        self.assertEqual(out["copied"], [f"h.example/zuno/mirror/hashicorp/vault@{D}"])

    def test_a_digest_mismatch_is_refused(self):
        def run(args, env=None, cwd=None):
            return "sha256:" + "b" * 64 + "\n" if args[1] == "resolve" else ""
        with self.assertRaises(m.ListError):
            m.copy_one(item(), "h.example", run)

    def test_only_filters_by_source(self):
        out = m.mirror_all([item(), item("ghcr.io/open-webui/open-webui")], "h.example", dry_run=True, only="open-webui")
        self.assertEqual(len(out["copied"]), 1)


if __name__ == "__main__":
    unittest.main()
