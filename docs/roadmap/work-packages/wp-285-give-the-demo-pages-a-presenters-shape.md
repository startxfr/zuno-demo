# WP-285: Give the demo pages a presenter's shape

- **State:** Not started
- **ADRs:** [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md)
- **Depends on:** none (Phase 56 is closed)
- **Related:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md), [WP-284](wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md)
- **Target:** v0.16
- **Estimated files touched:** ~42: `docs/demo/README.md`, both templates, the 30 scenario pages, the 6 workshops, `platform/demo/consistency.py` and `scaffold.py` with their tests

> Why: the owner asked on 2026-11-15 that every demo page read for a presenter: the status banner at the end, no ADR or
> work-package reference in the sections read on stage, and room for the GIF at the end of the Introduction.

## Goal

Every scenario page and workshop follows the order of ADR-0617 clause 10, the contract is the one text in
`docs/demo/README.md`, and CI refuses a page that leaves it.

## Steps

1. **Pilot, three files.** `docs/demo/_template-scenario.md`, the contract table of `docs/demo/README.md` and
   `docs/demo/scenarios/experiences/open-webui.md` take the order: Introduction (a paragraph and "The message"; no
   image line yet), Personas, Presenter lifecycle, the versions, If something goes wrong, Limits, Appendix A, Appendix
   B, `## References`, `## Page status` (the banner, unchanged, last). The Introduction, Personas and Presenter lifecycle
   lose their ADR, WP and `docs/adr` or `docs/roadmap` links, which move to References with sentences reworded so they
   still read. "listed in the status banner" becomes "listed under Page status". The README says that the other pages
   still have the old shape until the rollout.
2. **Owner's gate.** The owner and the team review the pilot page on `devel`, with the GIF of WP-284 when it exists.
3. **Rollout,** after the gate: `_template-workshop.md`, the 29 other scenarios and the 6 workshops, by layer, with a
   one-off move script that is not committed; the README sentence about the old shape is removed.
4. **Checks.** `platform/demo/consistency.py` reports an ADR or WP mention or a `docs/adr` or `docs/roadmap` link inside
   Introduction, Personas or Presenter lifecycle, a missing `## References`, a `## Page status` that is missing or not
   the last `##`, and a GIF present but not embedded at the end of the Introduction (or the reverse). `scaffold.py`
   reads the probe names from `## Page status`. Both are switched on in the same push as the last page, with tests.
5. **Generators.** The tools that write a rehearsal result into the status banner and the README write into
   `## Page status` once a page has it.

## Acceptance

- The pilot page has the new order, and the template and the README say the same.
- After the rollout, every page under `docs/demo/scenarios/` and `docs/demo/workshops/` passes the new checks.
- `make demo list`, `make demo check open-webui` and the catalogue tests pass: the parser reads the same sections.
- `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.
