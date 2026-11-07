# WP-239: ADR numbering check, record template and band hygiene

- **State:** Repo work in review
- **ADRs:** [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)
- **Depends on:** none
- **Related:** [ADR-0323](../../adr/0323-establish-canonical-generated-and-validated-platform-documentation.md) (the documentation checks)
- **Target:** v0.16
- **Estimated files touched:** ~8: `platform/docs/check_docs.py`, `platform/docs/tests/test_adr_number_collisions.py`, `.github/workflows/lint.yml`, `docs/adr/TEMPLATE.md`, `docs/adr/README.md` (numbering section), `docs/roadmap/versions.md`, `docs/roadmap/30-60-90-days.md`, `docs/platform/parallel-sessions.md`

> Why: on 2026-11-07 two records shared the number 0602 and the documentation check only noticed indirectly; the check
> stopped verifying the bands after v0.14; two planning pages no longer described the project.

## Goal

The documentation checks catch a duplicate ADR number and verify every current band, a new record starts from a
template, and the stale planning pages are replaced.

## Steps

1. `check_docs.py`: an explicit duplicate-number finding (`adr_number_collisions`), and `ADR_VERSIONS` extended to
   v0.15, v0.16 and v0.17. Unit test in `platform/docs/tests/`, run in CI next to the other platform tests.
2. `docs/adr/TEMPLATE.md`, modelled on ADR-0603: the header fields, the sections, the findings table, the numbered
   bold-named clauses, the work-packages section. The README's numbering section points at it and states the
   reservation rule (ADR-0606 clause 5).
3. `docs/roadmap/versions.md`: the v0.14 text says what is true (three ADRs `Implemented`, no open work package).
4. `docs/roadmap/30-60-90-days.md`: replaced by a pointer to `versions.md`.
5. `docs/platform/parallel-sessions.md`: how parallel working sessions reserve numbers, hold worktrees, announce and
   close a cluster window, and hand work over (ADR-0606 clause 6).

## Acceptance

- `python3 platform/docs/check_docs.py` passes, and the unit test proves that two `0602-*` files are reported, including
  when the extra file sorts first.
- The by-version table rows of v0.15 to v0.17 are verified by the check.
- The template, the parallel-sessions page and the replaced planning page exist.
