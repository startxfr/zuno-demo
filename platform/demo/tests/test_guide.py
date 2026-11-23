"""The demo guide generator (WP-330, ADR-0627): platform/demo/guide.py.

The page lists every demo of the catalogue and the curated console links, never holds a secret, stays far under the
1 MiB of a ConfigMap, and the copy committed in gitops/charts/demo-guide/files/ is what the pages produce.

Run from the repository root:
    python3 platform/demo/tests/test_guide.py
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import catalogue  # noqa: E402
import guide  # noqa: E402

ROOT = catalogue.repo_root()
AUTH_KINDS = {"keycloak", "openshift", "local", "token", "none", "unconfirmed"}


def opts(*argv: str):
    return guide.parse_args(list(argv))


class Data(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = guide.build_data(ROOT, opts())
        cls.demos = [d for g in cls.data["groups"] for d in g["demos"]]

    def test_every_demo_of_the_catalogue_is_listed_once(self):
        ids = [d["id"] for d in self.demos]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), sorted(e.id for e in catalogue.discover(ROOT)))

    def test_a_demo_has_a_title_a_description_and_a_page(self):
        for d in self.demos:
            with self.subTest(demo=d["id"]):
                self.assertTrue(d["title"])
                self.assertTrue(d["shows"] or d["message"])
                self.assertTrue(d["page"].startswith("https://github.com/"))

    def test_a_gif_is_given_only_when_the_file_exists(self):
        for d in self.demos:
            gif = ROOT / "docs" / "assets" / "img" / "demo" / f"{d['id']}.gif"
            with self.subTest(demo=d["id"]):
                self.assertEqual(bool(d["gif"]), gif.exists())
                if d["gif"]:
                    self.assertTrue(d["gif"].startswith("https://raw.githubusercontent.com/"))
                    self.assertTrue(d["gif"].endswith(f"/{d['id']}.gif"))

    def test_links_are_https_with_a_known_sign_in_kind(self):
        for layer in self.data["layers"]:
            for link in layer["links"]:
                with self.subTest(link=link["name"]):
                    self.assertTrue(link["url"].startswith("https://"))
                    self.assertIn(link["auth"], AUTH_KINDS)
                    if link["auth"] == "unconfirmed":
                        self.assertEqual(link["account"], "", "an unconfirmed row names no account")

    def test_the_four_layers_are_there(self):
        self.assertEqual([x["id"] for x in self.data["layers"]], ["ui", "gateway", "mlops", "infra"])

    def test_related_consoles_do_not_repeat_the_page_urls(self):
        for d in self.demos:
            with self.subTest(demo=d["id"]):
                self.assertFalse(set(d["urls"]) & set(d["related"]))

    def test_the_domain_is_a_parameter(self):
        other = guide.build_data(ROOT, opts("--domain", "apps.other.example"))
        text = json.dumps(other)
        self.assertNotIn("demo333.startx.fr", text)
        self.assertIn("https://open-webui.apps.other.example", text)

    def test_the_gif_ref_is_a_parameter(self):
        other = guide.build_data(ROOT, opts("--gif-ref", "v1.2.3"))
        gifs = [d["gif"] for g in other["groups"] for d in g["demos"] if d["gif"]]
        self.assertTrue(gifs and all("/startxfr/zuno-demo/v1.2.3/" in g for g in gifs))


class Safety(unittest.TestCase):
    def test_no_secret_in_the_output(self):
        files = guide.produce(ROOT, opts())
        self.assertEqual(guide.secret_findings(files[guide.DATA_FILE].decode("utf-8")), [])

    def test_the_secret_scan_catches_a_leak(self):
        for leak in ("password: hunter2hunter2", "token=abcdef123456", "AKIAABCDEFGHIJKLMNOP",
                     "-----BEGIN RSA PRIVATE KEY-----", "sk-abcdefghijklmnopqrstuvwx"):
            with self.subTest(leak=leak):
                self.assertTrue(guide.secret_findings(leak))
        self.assertEqual(guide.secret_findings("Vault keycloak/demo-personas, key password"), [])

    def test_the_page_is_far_under_a_configmap(self):
        files = guide.produce(ROOT, opts())
        total = sum(len(b) for b in files.values())
        self.assertLess(total, guide.MAX_BYTES)
        self.assertLess(guide.MAX_BYTES, 1024 * 1024)

    def test_the_page_source_never_calls_an_outside_host(self):
        # The only outside origin is the one that serves the animations, declared in the chart's CSP.
        for name in ("index.html", "app.js", "app.css"):
            text = (HERE.parent / "guide" / name).read_text(encoding="utf-8")
            for host in ("cdn.", "googleapis", "cloudflare", "unpkg", "jsdelivr"):
                with self.subTest(file=name, host=host):
                    self.assertNotIn(host, text)


class Output(unittest.TestCase):
    def test_two_runs_are_identical(self):
        self.assertEqual(guide.produce(ROOT, opts()), guide.produce(ROOT, opts()))

    def test_the_committed_copy_is_up_to_date(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = guide.main(["--check"])
        self.assertEqual(code, 0, err.getvalue())

    def test_check_fails_on_a_stale_copy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(guide.main(["--out", tmp]), 0)
                self.assertEqual(guide.main(["--out", tmp, "--check"]), 0)
                (pathlib.Path(tmp) / "data.json").write_text("{}\n")
                self.assertEqual(guide.main(["--out", tmp, "--check"]), 1)
            self.assertIn("out of date", err.getvalue())

    def test_a_secret_in_the_data_refuses_the_write(self):
        original = guide.build_data
        try:
            guide.build_data = lambda root, o: {"x": "password: hunter2hunter2"}
            with self.assertRaises(guide.GuideError):
                guide.produce(ROOT, opts())
        finally:
            guide.build_data = original


class Pages(unittest.TestCase):
    def test_text_helpers(self):
        self.assertEqual(guide.clean("**bold** and `code` and [a link](x.md)"), "bold and code and a link")
        self.assertEqual(guide.shorten("one two three four", 9), "one two…")
        self.assertEqual(guide.urls_of("see https://dify.apps.demo333.startx.fr/x, and `https://dify.apps.demo333.startx.fr/x`.",
                                       "apps.demo333.startx.fr"), ["https://dify.apps.demo333.startx.fr/x"])


if __name__ == "__main__":
    unittest.main()
