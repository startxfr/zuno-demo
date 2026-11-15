# WP-281: Rehearse every demo and workshop end to end

- **State:** Done
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-280](wp-280-compose-the-workshops-from-scenario-steps.md)
- **Related:** [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)
- **Target:** v0.16
- **Estimated files touched:** ~45: the status banners of the 30 scenario pages and 6 workshops, `docs/demo/README.md`, the ADR-0616 index row and body, one evidence file

> Why: ADR-0616 clause 11. The owner chose a full rehearsal of every demo in both versions as the proof that the
> catalogue can be played through `make demo` only.

## Goal

On 2026-11-18 every scenario has passed a 5-minute and a 15-minute automated rehearsal on demo333, every workshop a
rehearsal, the pages say so, and ADR-0616 is `Implemented`.

## Steps

1. Run `make demo golden-path` once first; a red moment is fixed or named before the rehearsals.
2. Rehearse the 30 scenarios in both versions and the 6 workshops, layer by layer, with the owner's named go for each
   demo whose manifest declares a changing unit (`DEMO_CONFIRM=<id>`). The world model is rehearsed without its install
   (owner's decision of 2026-11-14) and stays "not show-ready".
3. Run `make demo browser`; it covers the screens the rehearsals do not click.
4. Update each page's status banner: replace "Not rehearsed in this format" by the date and result of its rehearsals,
   and the README tables accordingly.
5. Write `docs/roadmap/evidence/wp-281-full-rehearsal-2026-11-18.md`: one line per demo and version (result, duration,
   skipped changing steps, named failures), the golden path and browser results, what remains manual on stage.
6. Set ADR-0616 to `Implemented` in its body and the index; close Phase 56 in the tracker; record the outcome in the
   repository `MEMORY.md`.

## Acceptance

- 60 scenario rehearsal reports (30 x 2) and 6 workshop reports, each `RESULT: PASS` or with failures their page names.
- `make demo golden-path` and `make demo browser` pass after the rehearsals.
- No page under `docs/demo/` still says "Not rehearsed" except where a named reason stands (the world model).
- `python3 platform/docs/check_docs.py` and the catalogue test pass.

## Result (2026-11-15)

Done three days before the date of the brief, by the owner's decision of 2026-11-15 to complete the rehearsals that
day. 60 scenario reports and 6 workshop reports end with `RESULT: PASS`; `make demo golden-path` passed before the
last batch (14 moments, the world model as roadmap) and ran again inside the `service-mesh-kiali` start; `make demo
browser` passed last, five checks ([evidence](../evidence/wp-281-full-rehearsal-2026-11-15.md)). Every page's banner
gives the date and result of its rehearsals; the "Not rehearsed" that remain name one screen or one row.

Limits of the proof, stated in the evidence file: the reports are the sum of layer runs at four commits (68ed5a62,
fbdd31c7, b2dd53c1, d105538f), not one pass at one commit; the presenter's screen output was not reviewed; the world
model and the registry part of `model-catalog-registry` stay "not show-ready"; the path "a failed check names its
probe" was not seen live.
