"""ADR-0590: platform/supply-chain/pin_claw_catalog.py (registry, tags and catalog content are faked).

Run from the repository root:
    python3 platform/supply-chain/tests/test_pin_claw_catalog.py
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pin_claw_catalog as p  # noqa: E402

REAL_CHART = pathlib.Path(__file__).resolve().parents[3] / "gitops" / "charts" / "openclaw"
CAT, MGR, PRX, OC = ("sha256:" + c * 64 for c in "abcd")
CSV = "claw-operator.v0.0.300-commit-abc1234"


def docs(entries=(CSV,), related=(("manager", "quay.io/codeready-toolchain/claw-operator:abc1234"),
                                  ("proxy", "quay.io/codeready-toolchain/claw-proxy:abc1234"))):
    return [
        {"schema": "olm.package", "name": "claw-operator", "defaultChannel": "staging"},
        {"schema": "olm.channel", "package": "claw-operator", "name": "staging",
         "entries": [{"name": e} for e in entries]},
        {"schema": "olm.bundle", "name": CSV, "package": "claw-operator",
         "properties": [{"type": "olm.package", "value": {"packageName": "claw-operator", "version": "0.0.300-commit-abc1234"}}],
         "relatedImages": [{"name": n, "image": i} for n, i in related]},
    ]


def resolver(repo, tag):
    return {("quay.io/codeready-toolchain/claw-operator-catalog", "latest"): CAT,
            ("quay.io/codeready-toolchain/claw-operator", "abc1234"): MGR,
            ("quay.io/codeready-toolchain/claw-proxy", "abc1234"): PRX,
            ("ghcr.io/openclaw/openclaw", "2026.10.9"): OC}[(repo, tag)]


def tags(_repo):
    return ["2026.7.1-2", "2026.10.9", "2026.10.10-beta.5", "2026.10.9-slim", "latest", "2026.9.30"]


class Pin(unittest.TestCase):
    def setUp(self):
        self.chart = pathlib.Path(tempfile.mkdtemp()) / "openclaw"
        shutil.copytree(REAL_CHART, self.chart)
        self.before = (self.chart / "values.yaml").read_text(encoding="utf-8")

    def test_newest_catalog_and_stable_openclaw_are_written_together(self):
        pins = p.pin(chart=self.chart, resolver=resolver, tags=tags, configs=lambda ref: docs())
        values = (self.chart / "values.yaml").read_text(encoding="utf-8")
        self.assertIn(f"catalogImage: {p.CATALOG}@{CAT}\n", values)
        self.assertIn(f"startingCSV: {CSV}\n", values)
        self.assertIn(f"manager: {MGR}\n", values)
        self.assertIn(f"proxy: {PRX}\n", values)
        self.assertIn(f"openclaw: {p.OPENCLAW}@{OC}\n", values)
        self.assertIn('appVersion: "0.0.300-commit-abc1234"', (self.chart / "Chart.yaml").read_text(encoding="utf-8"))
        self.assertEqual(pins["openclaw_tag"], "2026.10.9")
        self.assertTrue(pins["csv_changed"])
        # comments and every other value survive
        self.assertEqual(len(values.splitlines()), len(self.before.splitlines()))

    def test_dry_run_writes_nothing(self):
        p.pin(chart=self.chart, dry_run=True, resolver=resolver, tags=tags, configs=lambda ref: docs())
        self.assertEqual((self.chart / "values.yaml").read_text(encoding="utf-8"), self.before)

    def test_a_catalog_with_two_entries_is_refused(self):
        with self.assertRaises(p.PinError):
            p.pin(chart=self.chart, resolver=resolver, tags=tags, configs=lambda ref: docs(entries=(CSV, "other")))
        self.assertEqual((self.chart / "values.yaml").read_text(encoding="utf-8"), self.before)

    def test_a_bundle_without_the_proxy_image_is_refused(self):
        with self.assertRaises(p.PinError):
            p.pin(chart=self.chart, resolver=resolver, tags=tags,
                  configs=lambda ref: docs(related=(("manager", "quay.io/codeready-toolchain/claw-operator:abc1234"),)))

    def test_a_digest_referenced_image_is_kept_without_resolving(self):
        related = (("manager", "quay.io/codeready-toolchain/claw-operator@" + MGR),
                   ("proxy", "quay.io/codeready-toolchain/claw-proxy:abc1234"))
        pins = p.pin(chart=self.chart, resolver=resolver, tags=tags, configs=lambda ref: docs(related=related))
        self.assertEqual(pins["manager"], MGR)

    def test_newest_stable_ignores_betas_and_variants(self):
        self.assertEqual(p.newest_stable(tags(None)), "2026.10.9")

    def test_a_bad_catalog_target_is_refused(self):
        with self.assertRaises(p.PinError):
            p.pin(catalog="latest-ish", chart=self.chart, resolver=resolver, tags=tags, configs=lambda ref: docs())


if __name__ == "__main__":
    unittest.main()
