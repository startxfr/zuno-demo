"""The page shape of ADR-0617 (WP-285) and the published GIFs: one case per rule, on a copy of the fixture catalogue.

A page with `## Page status` has its `##` sections in the contract's order, no ADR or WP reference and no link into
docs/adr/ or docs/roadmap/ in its Introduction, Personas and Presenter lifecycle, and its banner under `## Page status`
only. A page without it is reported as a warning until SHAPE_ENFORCED. A published GIF belongs to a demo, is embedded
once as the last line of its Introduction and weighs at most 8 MB. scaffold.py reads the probes from `## Page status`.

Run from the repository root:
    python3 platform/demo/tests/test_page_shape.py
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent))

import catalogue  # noqa: E402
import consistency  # noqa: E402
import gif  # noqa: E402
import scaffold  # noqa: E402

EMBED = "![The fixture demo](../../../assets/img/demo/fixture-demo.gif)"


class Shape(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="zuno-shape-"))
        shutil.copytree(FIXTURES / "docs", self.root / "docs")
        shutil.copytree(FIXTURES / "ansible", self.root / "ansible")
        self.page = self.root / "docs/demo/scenarios/fixture/fixture-demo.md"
        self.workshop = self.root / "docs/demo/workshops/fixture-workshop.md"
        self.gifs = self.root / "docs/assets/img/demo"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def edit(self, old: str, new: str, path: pathlib.Path = None) -> None:
        path = path or self.page
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def problems(self, demo: str = "fixture-demo"):
        return consistency.problems(self.root, only=[demo], docs=False)

    def warnings(self, demo: str = "fixture-demo", only: bool = True):
        return consistency.warnings(self.root, only=[demo] if only else None)

    def one(self, needle: str, demo: str = "fixture-demo") -> str:
        found = [p for p in self.problems(demo) if needle in p]
        self.assertEqual(len(found), 1, self.problems(demo))
        return found[0]

    def publish(self, size: int = 1000, name: str = "fixture-demo.gif") -> pathlib.Path:
        self.gifs.mkdir(parents=True, exist_ok=True)
        path = self.gifs / name
        with open(path, "wb") as handle:
            handle.truncate(size)
        return path

    # --- the shape ---------------------------------------------------------------------------------------------------

    def test_the_fixtures_follow_the_shape(self):
        for demo in ("fixture-demo", "fixture-workshop"):
            self.assertEqual(self.problems(demo), [], demo)
            self.assertEqual(self.warnings(demo), [], demo)

    def test_the_repository_pages_that_moved_have_no_problem(self):
        self.assertEqual(consistency.shape_problems(catalogue.discover(ROOT), ROOT), [])
        self.assertEqual(consistency.gif_problems(catalogue.discover(ROOT), ROOT, everything=True), [])

    def test_sections_out_of_order(self):
        text = self.page.read_text()
        limits = text[text.index("## Limits"):text.index("## Appendix A - HLD")]
        self.page.write_text(text.replace(limits, "").replace("## Personas", limits + "## Personas"))
        self.assertIn("the `##` sections are Introduction, Limits, Personas", self.one("the contract is"))

    def test_page_status_must_be_last(self):
        self.page.write_text(self.page.read_text() + "\n## Afterword\n\nA section after the status.\n")
        self.assertIn("Page status, Afterword", self.one("the contract is"))

    def test_references_are_required(self):
        self.edit("## References\n", "## Sources\n")
        self.one("the contract is")

    def test_an_adr_in_personas(self):
        self.edit("| **fixture-01** | Every step: no sign-in, no cluster. |",
                  "| **fixture-01** | Every step ([ADR-0349](../../../../adr/0349-x.md)). |")
        problem = self.one("`## Personas` holds")
        self.assertIn("an ADR reference and a link into docs/adr/ or docs/roadmap/", problem)
        self.assertRegex(problem, r"fixture-demo\.md:\d+: ")

    def test_a_wp_link_in_a_lifecycle_subsection(self):
        self.edit("- [ ] Read the first step aloud.",
                  "- [ ] Read the first step aloud ([evidence](../../../roadmap/evidence/x.md)).")
        self.assertIn("a link into docs/adr/ or docs/roadmap/", self.one("`## Presenter lifecycle` holds"))
        self.edit("([evidence](../../../roadmap/evidence/x.md))", "(WP-193)")
        self.assertIn("a work-package reference (WP-193)", self.one("`## Presenter lifecycle` holds"))

    def test_an_adr_in_a_code_block_or_below_the_presenter_sections_is_fine(self):
        self.edit("used to prove the path action, runner playbook, results, page section.\n",
                  "used to prove the path action, runner playbook, results, page section.\n\n```text\nADR-0616\n```\n")
        self.edit("- A fixture shows the engine, not a demo.", "- A fixture shows the engine (ADR-0616, WP-270).")
        self.assertEqual(self.problems(), [])

    def test_a_banner_left_at_the_top(self):
        self.edit("# Scenario: fixture - the presenter lifecycle end to end\n",
                  "# Scenario: fixture - the presenter lifecycle end to end\n\n> **Status:** Left here.\n")
        self.assertIn(":3: the `> **Status:**` banner belongs under `## Page status`", self.one("banner belongs"))

    def test_a_workshop_keeps_its_head_and_tail(self):
        text = self.workshop.read_text()
        agenda = text[text.index("## Agenda"):text.index("## Presenter lifecycle")]
        personas = text[text.index("## Personas"):text.index("## Agenda")]
        self.workshop.write_text(text.replace(personas + agenda, agenda + personas))
        self.one("a workshop's `##` sections start with", "fixture-workshop")

    # --- the rollout -------------------------------------------------------------------------------------------------

    def unmove(self) -> None:
        text = self.page.read_text()
        status = text[text.index("## Page status"):]
        banner = status.split("\n", 2)[2].strip("\n")
        title, rest = text.replace(status, "").split("\n", 1)
        self.page.write_text(f"{title}\n\n{banner}\n{rest}".rstrip("\n") + "\n")

    def test_a_page_not_moved_yet_is_a_warning(self):
        self.unmove()
        self.assertEqual(self.problems(), [])
        detailed = self.warnings()
        self.assertTrue(detailed and all(w.startswith("not moved yet: ") for w in detailed), detailed)
        self.assertTrue(any("banner belongs" in w for w in detailed))
        summary = [w for w in self.warnings(only=False) if "fixture-demo.md" in w]
        self.assertEqual(len(summary), 1, summary)
        self.assertIn("not in the ADR-0617 page shape yet", summary[0])
        self.assertIn("--only fixture-demo", summary[0])

    def test_once_enforced_a_page_not_moved_is_a_problem(self):
        self.unmove()
        with mock.patch.object(consistency, "SHAPE_ENFORCED", True):
            self.assertTrue(any("banner belongs" in p for p in self.problems()))
            self.assertEqual([w for w in self.warnings() if "not moved yet" in w], [])

    def test_a_page_before_the_presenter_lifecycle_is_not_read(self):
        self.assertEqual(consistency.shape_findings(
            catalogue.find("fixture-unscaffolded", self.root),
            catalogue.load(catalogue.find("fixture-unscaffolded", self.root)), self.root), [])

    # --- the GIF -----------------------------------------------------------------------------------------------------

    def embed_last_in_introduction(self) -> None:
        self.edit("results, page section.\n", f"results, page section.\n\n{EMBED}\n")

    def test_a_published_gif_embedded_last_in_the_introduction(self):
        self.publish()
        self.one("embed it as the last line of `## Introduction`")
        self.embed_last_in_introduction()
        self.assertEqual(self.problems(), [])

    def test_the_embed_must_be_the_last_line_and_only_once(self):
        self.publish()
        self.edit("results, page section.\n", f"results, page section.\n\n{EMBED}\n\nOne more line.\n")
        self.one("embed it as the last line")
        self.one("embedded once, as the last line")
        self.edit("\n\nOne more line.\n", "\n")
        self.edit("- A fixture shows the engine, not a demo.", f"- A fixture shows the engine.\n\n{EMBED}")
        self.one("embedded once, as the last line")

    def test_an_embed_without_its_gif(self):
        self.embed_last_in_introduction()
        self.one("which is not published (the owner's go comes first)")

    def test_another_demos_gif(self):
        self.edit("results, page section.\n",
                  "results, page section.\n\n![x](../../../assets/img/demo/open-webui.gif)\n")
        self.one("embeds the GIF of another demo (open-webui)")

    def test_over_8_mb(self):
        self.publish(gif.MAX_BYTES + 1)
        self.embed_last_in_introduction()
        self.assertIn("over the 8 MB limit", self.one("MB, over the"))

    def test_an_orphan_gif(self):
        self.publish(name="no-such-demo.gif")
        self.publish(name="notes.txt")
        found = consistency.gif_problems(catalogue.discover(self.root), self.root, everything=True)
        self.assertEqual(sorted(found), ["docs/assets/img/demo/no-such-demo.gif: no catalogue demo has this GIF",
                                         "docs/assets/img/demo/notes.txt: no catalogue demo has this GIF"])

    def test_a_published_gif_without_its_cut_list_is_a_warning(self):
        self.publish()
        self.embed_last_in_introduction()
        self.assertIn("docs/assets/img/demo/fixture-demo.gif: no ansible/demos/fixture-demo/gif.yml says how it was cut",
                      self.warnings())
        (self.root / "ansible/demos/fixture-demo/gif.yml").write_text("moments: []\n")
        self.assertEqual(self.warnings(), [])


class PageProbes(unittest.TestCase):
    """scaffold.py reads the golden-path probes of the banner from `## Page status` (ADR-0617)."""

    PAGE = ("# Scenario: x\n\n{top}## Introduction\n\nText.\n\n## Page status\n\n{status}\n")

    def probes(self, top: str, status: str):
        page = catalogue.Page("x", "scenario", "l", pathlib.Path("x.md"), "", [])
        page.text = self.PAGE.format(top=top, status=status)
        page.sections = catalogue.parse_sections(page.text)
        return scaffold.page_probes(page, "none", [])

    def test_the_banner_is_read_at_the_bottom(self):
        self.assertEqual(self.probes("", "> **Show-ready:** yes, golden-path probes `alpha` and `beta`."),
                         ["alpha", "beta"])

    def test_the_top_is_ignored_once_page_status_exists(self):
        self.assertEqual(self.probes("> golden-path probe `stale`.\n\n", "> golden-path probe `fresh`."), ["fresh"])

    def test_fallback_to_the_top_for_a_page_not_moved_yet(self):
        page = catalogue.Page("x", "scenario", "l", pathlib.Path("x.md"), "", [])
        page.text = "# Scenario: x\n\n> golden-path probe `top`.\n\n## Introduction\n\nText.\n"
        page.sections = catalogue.parse_sections(page.text)
        self.assertEqual(scaffold.page_probes(page, "none", []), ["top"])


if __name__ == "__main__":
    unittest.main()
