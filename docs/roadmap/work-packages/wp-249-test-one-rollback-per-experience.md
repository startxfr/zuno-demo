# WP-249: Test one rollback per experience

- **State:** Operator pending (2026-11-11: the WP-243 negative case done, the OpenClaw and world-model rollbacks recorded, single-version experiences deferred to their first upgrade, D1-D2 decided; left: Lightspeed, Blender, UnifAI with v0.1.69, the first-party digests with the next release)
- **ADRs:** [ADR-0606](../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)
- **Depends on:** [WP-243](wp-243-browser-tests-for-every-experience.md) (the browser checks used for the negative case)
- **Related:** [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md) (golden path after each change), [ADR-0607](../../adr/0607-pin-gate-and-schedule-pre-ga-dependencies.md) (OLM never downgrades), [ADR-0609](../../adr/0609-rehearse-on-canary-namespaces-of-demo333.md) (canary namespaces)
- **Target:** v0.16
- **Estimated files touched:** ~4: `docs/demo/rollback.md` (a Tested column), evidence files under `docs/roadmap/evidence/`, this brief, the tracker

> Why: ADR-0606 clause 1 asks every admitted experience for a written rollback "tested once", and the ADR stays
> `Accepted` until each one has been tested. `docs/demo/rollback.md` holds the written rollbacks; none is recorded as
> tested except the world model's teardown. WP-243 also left its negative case open: each browser check must fail when
> its experience is scaled to zero. Opened on 2026-11-11 (user decision); each live step needs the user's go, outside a
> freeze, with a golden-path run after it.

## What "tested once" means

- **An image or chart pin** (first-party images, Open WebUI, Dify, kagent, the OpenClaw assistant, the UnifAI stack
  images, Lightspeed's `OLSConfig`): move to the previous pin, check that the experience answers (its golden-path
  moment and its browser check), then move forward again. Both moves are recorded.
- **An operator** (OpenClaw, UnifAI, nfs-provisioner, Lightspeed): OLM never downgrades (ADR-0607), so its rollback is
  a forward fix or a restore. "Tested" means its restore path ran once: the backup of the data it owns, restored into a
  canary namespace (ADR-0609), and read back. Decision D1 below.
- **Data that migrates forward** (Open WebUI and Dify databases): a backup first (`make d3 backup postgresql`, Dify's
  own database), and the image move only after the backup is confirmed readable.

## Order (cheapest and safest first)

| # | Experience | Test | Data | Live cost |
|---|---|---|---|---|
| 1 | kagent | previous image pin, then forward | none | one roll |
| 2 | Lightspeed | `git revert` of the last `OLSConfig` change in a canary copy, then forward | none | none for users |
| 3 | Blender | remove the four edge objects and the client, the workstation is refused (401/404), restore | none | the Blender moment is down for minutes |
| 4 | first-party images | `render_release_digests.py --release v0.15.0` (the ledgered digests), roll, golden path; then `--clear` back to `:latest` | none | every first-party pod rolls twice |
| 5 | OpenClaw assistant | previous `images.openclaw`, then forward | the assistant's own namespace state | one roll per assistant |
| 6 | Open WebUI | backup, previous `image.tag`, then forward | its PostgreSQL database | one roll, backup first |
| 7 | Dify | backup of its database, previous image tags, restore of the database, then forward | its database migrates on start | heaviest: a restore |
| 8 | UnifAI | `pin_unifai_images.py v<previous> --cluster demo333`, `make d2 install unifai`, then the current pin | UnifAI's own databases (kept, the stack images only) | one stack roll; with unifai-main's agreement |
| 9 | World model | done: the teardown ran on 2026-11-09 and 2026-11-11 (`zuno_world_model_enabled: false`, role run) | weights in S3 | recorded, no new run |

## WP-243 negative case

**Done on 2026-11-11** ([evidence](../evidence/wp-243-negative-case-2026-11-11.md)). The experiences were blocked with a
temporary AdminNetworkPolicy instead of being scaled to zero, which ArgoCD selfHeal and the operators undo.

The original plan:

For each experience with a browser check: scale it to zero, run `make demo browser`, see that check fail and the others
pass, scale it back, see it pass. Run it right after that experience's rollback test, so each experience is down once.

## Rule for single-version experiences (D3, user decision 2026-11-11)

kagent, Dify and Open WebUI have only ever run one version, so they have no previous pin to return to, and their
uninstall path is a deletion. Their rollback is tested at their first version change (ADR-0606 amendment of 2026-11-11):
rows 1, 6 and 7 wait for that change. They no longer hold ADR-0606 open.

## Evidence already recorded

- **OpenClaw (row 5): rolled back live on 2026-11-03.** 2026.10.9 was pinned on 2026-11-02 (b41bdf2b). On demo333 it
  asked for a state-database migration, then refused the `openclaw.json` that the claw operator writes. The pin went
  back to the operator's default, 2026.7.1-2 (a759d6b9), and the assistants answered again. The rollback is a pin
  revert, and it was exercised.
- **World model (row 9):** its teardown ran on 2026-11-09 and on 2026-11-11.

## Decisions (user, 2026-11-11)

- **D1, decided: the restore.** For an operator, a rehearsed restore of its data into a canary namespace, read back,
  counts as its rollback tested. No uninstall and reinstall is required. OLM never downgrades (ADR-0607).
- **D2, decided: with the next release.** Row 4 runs together with the next release's `RENDER_DIGESTS=1` step, not in
  a window of its own. That release comes after zuno-demo's WP-248 Quay cutover.

## Acceptance

- `docs/demo/rollback.md` gains a "Tested" column: a date and an evidence link for every row.
- The WP-243 negative case is recorded for each browser check.
- A golden-path run passes after each step.
- ADR-0606 can then move to `Implemented`.
