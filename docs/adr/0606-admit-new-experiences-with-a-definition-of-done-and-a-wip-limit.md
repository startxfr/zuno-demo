# ADR-0606: Admit new experiences with a definition of done and a WIP limit

- **Status:** Implemented
- **Target:** v0.16
- **Date:** 2026-11-07
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md) (the admission contract of an experience client)
- **Related:** [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0592](0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md), [ADR-0607](0607-pin-gate-and-schedule-pre-ga-dependencies.md), [ADR-0608](0608-keep-the-repository-the-only-source-of-cluster-state.md), [ADR-0609](0609-rehearse-on-canary-namespaces-of-demo333.md)

## Context

The project review of 2026-11-07 found that the platform's breadth is growing faster than its robustness, and that the
records that steer it are starting to drift.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Six user experiences were decided in six days. | Open WebUI and OpenClaw (ADR-0588 to ADR-0590, 2026-11-02), Zuno Code, Dify and kagent (ADR-0596, ADR-0599, ADR-0600, 2026-11-04), the world model (ADR-0604, 2026-11-07). 443 commits landed between 2026-11-01 and 2026-11-07. |
| F2 | Tags carry many named exceptions. | v0.14.0 was tagged with eight known defects (D1 to D10 minus the closed ones, `docs/roadmap/versions.md`); D11 is still open. |
| F3 | Nine bands were never tagged. | v0.4 to v0.12 have no tag; their content is only in `v0.13.0`. |
| F4 | Two records shared a number. | A second `0602` file (the world model, now ADR-0604) sat next to ADR-0602 on 2026-11-07. `platform/docs/check_docs.py` keys ADR files by their first four characters, so the duplicate showed only as link and status drift, and would have shown nothing had its slug sorted first. |
| F5 | The checks stop before the current bands. | `ADR_VERSIONS` in `check_docs.py` ends at v0.14, so the v0.15 and v0.16 rows of the by-version table are not verified; the v0.14 text of `versions.md` still says "3 ADRs, all `Proposed`"; `30-60-90-days.md` was last edited on 2026-08-13. |
| F6 | Procedures live in operators' notes. | The freeze protocol, the release-pinning routine and the coordination between parallel working sessions are written down only outside the repository. |
| F7 | Numbers are taken by parallel sessions. | ADR and WP numbers have been allocated by message between sessions since 2026-11-02 ("next free ADR-0592, WP-189"), with no check that catches a clash. |

## Decision

**A new user experience is admitted only with a definition of done, at most two per band, and the records that steer
the project are kept consistent by checks, not by memory.**

1. **Definition of done of an experience.** On top of ADR-0587's admission contract, an experience client is "done"
   only with:
   - its work package, with a tracker row;
   - its golden-path probe (ADR-0605 clause 1), passing on the target cluster;
   - a written rollback: the previous pinned digest or the uninstall path, tested once;
   - its step in a demonstration script under `docs/demo/`, with its named limits;
   - its `client` value in the ai-gateway's `experienceClients`, so its traffic is counted (ADR-0593).
   An experience without all five may run on the cluster; it is not shown to an audience.
2. **WIP limit.** At most two new experiences per band, counted by the `**Target:**` of the ADR that introduces them.
   A third waits for the next band. Hardening work, probes and fixes are not limited.
3. **Named exceptions are capped.** A tag carries at most three named exceptions. A band with more is not tagged until
   enough are fixed or moved out by a dated retarget.
4. **Every band is tagged when it closes.** A band that cannot close within two weeks of its first tag date is split:
   what is done keeps the band, what is not moves to the next one with a CHANGELOG entry.
5. **Numbers are reserved, then checked.** A new ADR or WP number is reserved by message to every live working session
   and checked against `origin` and every local branch before the file is written. `check_docs.py` fails when two
   files under `docs/adr/` share their four-digit prefix, and its `ADR_VERSIONS` follows the bands of `versions.md`.
   `docs/adr/TEMPLATE.md` gives the header and the sections of a record.
6. **A procedure run twice lives in the repository.** Any procedure run more than once against a live cluster gets a
   runbook under `docs/`. The first ones are the freeze protocol (ADR-0605), the coordination of parallel working
   sessions (`docs/platform/parallel-sessions.md`: who holds which worktree, how a cluster window is announced and
   closed) and the pinning of a pre-GA release (ADR-0607).
7. **Stale planning pages are replaced, not kept.** A planning page that no longer describes the project is replaced by
   a pointer to `versions.md`.

## Alternatives considered

- **Alternate feature bands and stabilisation bands.** Simple to read, but an urgent experience waits a whole band.
  Rejected in favour of a WIP limit, which still lets two experiences in.
- **A hardening quota (a third of every band's work packages).** Flexible, but hard to check and easy to argue around.
  Rejected.
- **No limit, only the definition of done.** The definition of done alone does not stop six experiences from being
  half-done at once, which is what F1 and F2 describe. Rejected.

## Consequences

- A demonstration shows fewer new experiences, each with a probe, a rollback and a script.
- The v0.16 band, where this record sits, is the first to which the WIP limit applies. ADR-0604's world model counts
  as one of its two.
- Retargets become more frequent and are logged in `CHANGELOG.md`, which is what that file is for.
- `check_docs.py` fails on the next duplicate number instead of reporting a confusing drift.

## Security considerations

None beyond the existing checks: the definition of done reuses ADR-0587's admission contract, whose security rules
(no own keys, LLM only through the ai-gateway, tools only through the mcp-gateway) are unchanged.

## Operational considerations

The duplicate-number check and the extended `ADR_VERSIONS` run in CI with the other documentation checks
(`.github/workflows/lint.yml`). The rules apply to work started after 2026-11-08; the experiences already admitted get
their missing items through WP-238 (probes) and WP-243 (browser tests).

## Work packages

[WP-239](../roadmap/work-packages/wp-239-adr-numbering-check-template-and-band-hygiene.md) (the check, the template, the
band and page fixes),
[WP-243](../roadmap/work-packages/wp-243-browser-tests-for-every-experience.md) (one browser test per experience,
v0.16).

## Update 2026-11-07 (WP-238, WP-239, WP-243): the definition of done applied to the admitted experiences

For the experiences already admitted (UnifAI, Open WebUI, OpenClaw, Dify, kagent, Zuno Code, Lightspeed):
- a work package each: yes (WP-179 to WP-208 and WP-194);
- a golden-path probe each: `make demo golden-path` gets a real answer from every one of them (WP-238);
- a browser check each: `make demo browser` (WP-243);
- a demonstration script: `docs/demo/three-experiences.md` and `five-experiences.md`;
- a `client` value in the ai-gateway's `experienceClients`: yes;
- a written rollback each: `docs/demo/rollback.md`.

Clauses 2 to 7 are in force, and the number check and the template are in place (WP-239). This record stays
`Accepted` until each rollback has been tested once, which clause 1 requires; the tests run in the window after the
2026-11-09 demonstration. The world model (ADR-0604) is the first experience admitted under this record, in v0.16.

## Status note (2026-11-11)

The rollback tests have their own work package,
[WP-249](../roadmap/work-packages/wp-249-test-one-rollback-per-experience.md): one test per experience, cheapest first,
with WP-243's scale-to-zero negative case. The world model's teardown already ran (2026-11-09 and 2026-11-11). This record
moves to `Implemented` when WP-249 is Done.

## Amendment (2026-11-11, user decision): a single-version experience is tested at its first version change

Clause 1 asks for a rollback "tested once": the previous pinned digest, or the uninstall path. An experience that has only
ever run one version (kagent, Dify, Open WebUI on 2026-11-11) has no previous pin to return to, and its uninstall path is
a deletion. For those, the rollback is tested at the first version change: pin the new version, golden path, move back to
the old pin, golden path, move forward again. This record moves to `Implemented` once the experiences that do have a
version history have their rollback recorded (OpenClaw, UnifAI, Lightspeed, Blender, the first-party images, the world
model) and WP-243's negative case is recorded. The single-version experiences stay tracked in
[WP-249](../roadmap/work-packages/wp-249-test-one-rollback-per-experience.md) until their first upgrade. The other
clauses are unchanged.

## Status note (2026-11-12): Implemented

[WP-249](../roadmap/work-packages/wp-249-test-one-rollback-per-experience.md) is Done. Every experience that has a
version history has its rollback tested once and recorded, as the amendment above asks:

| Experience | Rollback tested | Evidence |
|---|---|---|
| OpenClaw | 2026-11-03, a pin revert run live | WP-249 brief, "Evidence already recorded" |
| World model | 2026-11-09 and 2026-11-11, teardown | WP-237, WP-249 row 9 |
| Lightspeed | 2026-11-12, `git revert` of the chart and forward. The 2026-10-24 version answers 413 today | [evidence](../roadmap/evidence/wp-249-lightspeed-rollback-2026-11-12.md) |
| Blender | 2026-11-12, edge removed (503) and restored (401) | [evidence](../roadmap/evidence/wp-249-blender-edge-rollback-2026-11-12.md) |
| First-party images | 2026-11-08, v0.14.5 digests rendered, then `--clear` | [evidence](../roadmap/evidence/wp-249-first-party-digests-2026-11-08.md) |
| UnifAI | 2026-11-12, v0.1.69 pinned, stack back to v0.1.68 and forward; operator data restore drilled 2026-10-23 | [evidence](../roadmap/evidence/wp-249-unifai-rollback-2026-11-12.md) |

WP-243's negative case is recorded too ([evidence](../roadmap/evidence/wp-243-negative-case-2026-11-11.md)).

kagent, Dify and Open WebUI have run one version only. Their rollback is tested at their first version change. Each
row of `docs/demo/rollback.md` says so in its Tested column, which replaces WP-249 as the place they are tracked.
