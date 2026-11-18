"""Tests for mirror_redhat_images (WP-261 family e): registry.redhat.io only, digest pins, private repositories, drift."""
import base64
import json
import os
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import admit_okf_bundle as admit  # noqa: E402
import mirror_redhat_images as m  # noqa: E402

D = "sha256:" + "a" * 64
E = "sha256:" + "b" * 64
SRC = "registry.redhat.io/rhoai/odh-mlflow-rhel9"
_REQUIRE = admit.require


def setUpModule():  # no oc or oras needed on the test host
    admit.require = lambda binary: binary


def tearDownModule():
    admit.require = _REQUIRE


def item(source=SRC, digest=D):
    return {"source": source, "pin": "digest", "digest": digest, "signature": "red-hat-lookaside", "reason": "test"}


def write(text):
    p = pathlib.Path(tempfile.mkdtemp()) / "l.yaml"
    p.write_text(text)
    return p


class ListTests(unittest.TestCase):
    def test_the_committed_list_is_valid(self):
        images = m.load_list()
        self.assertEqual(len(images), 8)
        self.assertTrue(all(i["source"].startswith("registry.redhat.io/") for i in images))

    def test_the_chart_redirects_exactly_the_listed_repositories(self):
        import yaml
        values = yaml.safe_load((HERE.parents[2] / "gitops/charts/quay-registry/values.yaml").read_text())
        self.assertFalse(values["redhatRedirects"]["enabled"])
        self.assertEqual(sorted(values["redhatRedirects"]["sources"]), sorted({i["source"] for i in m.load_list()}))

    def test_refuses_another_registry_or_a_tag_pin(self):
        with self.assertRaises(m.ListError):
            m.load_list(write(f"images:\n  - {{source: quay.io/x/y, pin: digest, digest: {D}, signature: s, reason: r}}\n"))
        with self.assertRaises(m.ListError):
            m.load_list(write("images:\n  - {source: registry.redhat.io/x/y, pin: tag, tag: v1, signature: s, reason: r}\n"))

    def test_two_digests_of_one_repository_are_allowed(self):
        rows = "".join(f"  - {{source: {SRC}, pin: digest, digest: {d}, signature: s, reason: r}}\n" for d in (D, E))
        self.assertEqual(len(m.load_list(write("images:\n" + rows))), 2)


class CopyTests(unittest.TestCase):
    def test_path_goes_under_redhat(self):
        self.assertEqual(m.mirror_target(SRC, "h.example"), "h.example/zuno/redhat/rhoai/odh-mlflow-rhel9")

    def test_copy_reads_the_source_credential_and_checks_the_digest(self):
        calls = []

        def run(args):
            calls.append(args)
            return D if args[1] == "resolve" else ""

        self.assertEqual(m.copy_one(item(), "h.example", "/tmp/auth.json", run=run), f"h.example/zuno/redhat/rhoai/odh-mlflow-rhel9@{D}")
        cp = calls[0]
        self.assertEqual(cp[1:6], ["cp", "--concurrency", "1", "--from-registry-config", "/tmp/auth.json"])
        self.assertNotIn("-r", cp)
        self.assertEqual(cp[-2:], [f"{SRC}@{D}", "h.example/zuno/redhat/rhoai/odh-mlflow-rhel9:d-aaaaaaaaaaaa"])

    def test_refuses_a_digest_mismatch(self):
        with self.assertRaises(m.ListError):
            m.copy_one(item(), "h.example", "a", run=lambda args: E if args[1] == "resolve" else "")

    def test_source_auth_keeps_only_registry_redhat_io_and_is_removed(self):
        secret = {"auths": {"registry.redhat.io": {"auth": "eDp5"}, "quay.io": {"auth": "c2VjcmV0"}}}
        raw = base64.b64encode(json.dumps(secret).encode()).decode()
        with m.source_auth_from_cluster(run=lambda args: raw) as path:
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
            self.assertEqual(json.loads(pathlib.Path(path).read_text()), {"auths": {"registry.redhat.io": {"auth": "eDp5"}}})
        self.assertFalse(pathlib.Path(path).exists())

    def test_source_auth_refuses_a_pull_secret_without_registry_redhat_io(self):
        raw = base64.b64encode(json.dumps({"auths": {}}).encode()).decode()
        with self.assertRaises(m.ListError):
            with m.source_auth_from_cluster(run=lambda args: raw):
                pass

    def test_dry_run_copies_nothing(self):
        out = m.mirror_all([item(), item("registry.redhat.io/rhoai/odh-ogx-core-rhel9")], "h", dry_run=True, only="ogx")
        self.assertEqual(out, [f"h/zuno/redhat/rhoai/odh-ogx-core-rhel9@{D}"])


class VisibilityTests(unittest.TestCase):
    def test_makes_public_repositories_private_and_never_public(self):
        sent = []

        def request(method, url, body):
            sent.append((method, url, body))
            return {"is_public": url.endswith("/a")} if method == "GET" else {}

        self.assertEqual(m.ensure_private("h", ["redhat/a", "redhat/b"], "t", request=request), ["redhat/a"])
        posts = [s for s in sent if s[0] == "POST"]
        self.assertEqual(posts, [("POST", "https://h/api/v1/repository/zuno/redhat/a/changevisibility", {"visibility": "private"})])


class DriftTests(unittest.TestCase):
    def pods(self, *images):
        return {"items": [{"metadata": {"namespace": "ns", "name": f"p{i}"},
                           "spec": {"containers": [{"image": img}]}} for i, img in enumerate(images)]}

    def test_reports_a_running_digest_the_list_misses(self):
        out = m.drift(self.pods(f"{SRC}@{D}", f"{SRC}@{E}", f"registry.redhat.io/other/repo@{E}", f"{SRC}:latest"), [item()])
        self.assertEqual(out, [f"{SRC}@{E} (used by ns/p1)"])

    def test_no_drift_when_everything_is_listed(self):
        self.assertEqual(m.drift(self.pods(f"{SRC}@{D}"), [item()]), [])


class MainTests(unittest.TestCase):
    def test_drift_exit_code(self):
        orig = admit.run
        try:
            admit.run = lambda args: json.dumps({"items": []})
            self.assertEqual(m.main(["--drift"]), 0)
        finally:
            admit.run = orig


if __name__ == "__main__":
    unittest.main()
