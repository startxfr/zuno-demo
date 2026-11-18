"""Tests for mirror_unifai_images (WP-248 family c): what is copied, what is refused, nothing real is called."""
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import admit_okf_bundle as admit  # noqa: E402
import mirror_unifai_images as m  # noqa: E402
import verify_unifai_images as v  # noqa: E402

D = "a" * 64
SBOM = "b" * 64
MIRROR = "quay.example/zuno"
SRC = f"quay.io/zuno/unifai-rag@sha256:{D}"


class CopyImageTests(unittest.TestCase):
    def fake(self, missing=()):
        calls = []

        def run(args, env=None, cwd=None):
            calls.append(args)
            if args[1] == "resolve":
                ref = args[2]
                if ref.endswith(".sbom"):
                    return f"sha256:{SBOM}\n"
                return f"sha256:{D}\n"
            if args[1] == "cp" and any(args[3].endswith(t) for t in missing):
                raise admit.AdmissionError("manifest not found")
            return ""
        return calls, run

    def test_copies_image_signature_attestation_sbom_and_sbom_signature(self):
        calls, run = self.fake()
        target = m.copy_image(SRC, MIRROR, run)
        self.assertEqual(target, f"quay.example/zuno/unifai-rag@sha256:{D}")
        copied = [c[-1] for c in calls if c[1] == "cp"]
        self.assertIn(f"quay.example/zuno/unifai-rag:d-{D[:12]}", copied)
        for suffix in (".sig", ".att", ".sbom"):
            self.assertIn(f"quay.example/zuno/unifai-rag:sha256-{D}{suffix}", copied)
        self.assertIn(f"quay.example/zuno/unifai-rag:sha256-{SBOM}.sig", copied)

    def test_a_missing_tag_is_not_an_error_but_a_digest_mismatch_is(self):
        calls, run = self.fake(missing=(".att",))
        m.copy_image(SRC, MIRROR, run)

        def wrong(args, env=None, cwd=None):
            return "sha256:" + "c" * 64 + "\n" if args[1] == "resolve" and not args[2].endswith(".sbom") else ""
        with self.assertRaises(m.MirrorError):
            m.copy_image(SRC, MIRROR, wrong)


class MirrorAllTests(unittest.TestCase):
    refs = {"unifai-rag": SRC}

    def test_nothing_is_copied_when_the_source_is_refused(self):
        copied = []
        bad = lambda ref, policy: v.Result(ref, False, "no signature")
        with self.assertRaises(m.MirrorError):
            m.mirror_all(self.refs, MIRROR, verify=bad, copy=lambda s, t: copied.append(s) or t)
        self.assertEqual(copied, [])

    def test_dry_run_copies_nothing_and_verifies_the_source(self):
        copied, seen = [], []

        def ok(ref, policy):
            seen.append((ref, policy))
            return v.Result(ref, True)
        out = m.mirror_all(self.refs, MIRROR, dry_run=True, verify=ok, copy=lambda s, t: copied.append(s) or t)
        self.assertEqual(copied, [])
        self.assertEqual(out, [f"quay.example/zuno/unifai-rag@sha256:{D}"])
        self.assertEqual(seen, [(SRC, None)])

    def test_the_copy_is_verified_with_the_policy_of_the_source(self):
        seen = []

        def ok(ref, policy):
            seen.append((ref, policy))
            return v.Result(ref, True)
        m.mirror_all(self.refs, MIRROR, verify=ok, copy=lambda s, t: admit.mirror_reference(s, t))
        self.assertEqual(seen[-1], (f"quay.example/zuno/unifai-rag@sha256:{D}", SRC))

    def test_a_copy_that_does_not_verify_is_refused(self):
        def verify(ref, policy):
            return v.Result(ref, policy is None, "bad copy")
        with self.assertRaises(m.MirrorError):
            m.mirror_all(self.refs, MIRROR, verify=verify, copy=lambda s, t: admit.mirror_reference(s, t))


class PinnedReferencesTests(unittest.TestCase):
    def test_reads_the_five_images_and_the_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            cluster = pathlib.Path(d) / "c.yml"
            images = "\n".join(f"      {c}: quay.io/zuno/unifai-{c}@sha256:{D}" for c in
                               ("backend", "identity", "multiagent", "rag", "ui"))
            cluster.write_text(f"zuno_unifai_values:\n  stack:\n    images:\n{images}\n")
            vals = pathlib.Path(d) / "v.yaml"
            vals.write_text(f"x:\n  catalogImage: quay.io/zuno/unifai-operator-catalog@sha256:{D}\n")
            refs = m.pinned_references(cluster, vals)
        self.assertEqual(len(refs), 6)
        self.assertIn("unifai-operator-catalog", refs)

    def test_an_unpinned_image_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            cluster = pathlib.Path(d) / "c.yml"
            cluster.write_text("zuno_unifai_values:\n  stack:\n    images:\n      backend: quay.io/zuno/unifai-backend:v1\n")
            vals = pathlib.Path(d) / "v.yaml"
            vals.write_text("")
            with self.assertRaises(m.MirrorError):
                m.pinned_references(cluster, vals)


class VisibilityTests(unittest.TestCase):
    def test_every_repository_is_made_public(self):
        sent = []
        m.make_public("host.example/zuno", ["unifai-rag", "unifai-ui"], "tok", lambda *a: sent.append(a))
        self.assertEqual([s[1] for s in sent], ["https://host.example/api/v1/repository/zuno/unifai-rag/changevisibility",
                                               "https://host.example/api/v1/repository/zuno/unifai-ui/changevisibility"])
        self.assertTrue(all(s[3] == {"visibility": "public"} for s in sent))


if __name__ == "__main__":
    unittest.main()
