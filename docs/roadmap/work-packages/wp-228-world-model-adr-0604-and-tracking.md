# WP-228: World-model ADR-0604 and tracking (delivers ADR-0604 bookkeeping)

- **State:** Repo work in review
- **ADRs:** ADR-0604
- **Depends on:** none
- **Blocks:** WP-229, WP-230, WP-233
- **Estimated files touched:** ~15

> Execute this brief as a standalone task from the repository root.

## Goal

Give the world-model decision a valid number and an index row, record the user's 2026-11-07 decisions in it, and open the
work packages that deliver it.

## ADR references

ADR-0604, all clauses (amendment note at the top of the record).

## Repo changes

1. `git mv` the second `docs/adr/0602-introduce-an-interactive-generative-world-model-experience.md` (a380cc77) to
   `docs/adr/0604-...md`; header `ADR-0604`, `Status: Accepted` (plain, so `check_docs.py` normalizes it), `Target: v0.16`.
2. Amend D3 (FLUX inside the namespace), D4 (H.264 over WebSocket, WebCodecs), D5 (on-demand node, taint, switch, cost
   alert), D6/D7, new D8 (prompt enhancement through the ai-gateway), §4, §6, §7, §8, §9 G5, §11 (WP-228 to WP-237),
   §12, §13, §15, with a dated amendment note.
3. Row in the v0.16 band of `docs/adr/README.md`; entry in `docs/adr/CHANGELOG.md`.
4. Phase 51 in `docs/roadmap/implementation-roadmap.md`, the v0.16 row of the by-version table, a change-log line.
5. Briefs `wp-228` to `wp-237`.

## Verification

`python3 -B platform/docs/check_docs.py` passes (the duplicate-0602 link mismatch and the em-dash status drift are gone).
