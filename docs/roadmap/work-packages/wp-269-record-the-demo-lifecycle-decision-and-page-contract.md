# WP-269: Record the demo lifecycle decision and the page contract

- **State:** Done (2026-11-14)
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** none
- **Related:** [ADR-0550](../../adr/0550-demonstrate-sovereign-ai-through-classification-specialization-and-resilience.md), [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [WP-270](wp-270-build-the-make-demo-lifecycle-engine.md)
- **Target:** v0.16
- **Estimated files touched:** ~20: ADR-0616, ADR-0550, ADR-0605, the ADR index, the roadmap, 13 briefs, `docs/demo/README.md`, the two templates

> Why: the owner asked on 2026-11-14 that every demo of the catalogue be prepared and played through `make demo` only,
> and took seventeen decisions in five question waves. They are recorded before any code, so the engine, the pilots
> and the rollout implement one written contract.

## Goal

ADR-0616 is written and indexed, ADR-0550 names it back, ADR-0605 carries a dated note, Phase 56 lists WP-269 to
WP-281 with their dates, and the page contract (`## Presenter lifecycle`) is in `docs/demo/README.md` and both
templates.

## Steps

1. Reserve ADR-0616 and WP-269 to WP-281 with every live session (ADR-0606 clause 5) and check them against `origin`
   and every local branch.
2. Write ADR-0616 with the owner's decisions: grammar and session, the page as source of truth, one directory per demo,
   the lifecycle section, reads-only steps, add-ons only, guards, local freeze marker, check and status, workshops by
   composition, proof by automated rehearsal, local execution, retirement of the webinar helpers, the CI test.
3. Set ADR-0550 to `Superseded in part by ADR-0616` (its "Demo automation" section) with a dated update; add a dated
   correction note to ADR-0605 (clause 1 names `make demo check`); add the index row under v0.16.
4. Add Phase 56 to `implementation-roadmap.md` and one brief per WP; regenerate the by-version table.
5. Write the page contract: the `Presenter lifecycle` row of the section table and a "Playing a demo" section in
   `docs/demo/README.md`; replace `## Before you start` by `## Presenter lifecycle` in `_template-scenario.md` and add
   it to `_template-workshop.md`. The pages themselves move in WP-271 to WP-280.

## Acceptance

- `python3 platform/docs/check_docs.py` passes.
- The two templates and the README say the same thing about the lifecycle section.

## Result (2026-11-14)

All five steps done in one commit on `devel`. The three live sessions (zuno-main, zuno-demo, zuno-worldmodels)
acknowledged the reserved numbers and that they do not touch `docs/demo/`, the `demo` part of the Makefile or the demo
playbooks. The 30 scenario pages and 6 workshops still have their old `## Before you start`; the README says so until
WP-280.
