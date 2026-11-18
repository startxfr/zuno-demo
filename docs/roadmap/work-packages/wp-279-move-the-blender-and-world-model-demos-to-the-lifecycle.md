# WP-279: Move the Blender and world-model demos to the lifecycle

- **State:** Done
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md) and [WP-274](wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md), and the owner's go at the gate of 2026-11-16
- **Related:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md), [WP-281](wp-281-rehearse-every-demo-and-workshop-end-to-end.md)
- **Target:** v0.16
- **Estimated files touched:** ~35: `docs/demo/blender-3d.md`, `docs/demo/world-model.md`, their directories, `evaluations/blender/install_addon.sh`

> Why: the only two demos with real add-ons, which give `install` and `uninstall` their meaning (ADR-0616 clause 6) and carry the infrastructure guard (clause 7).

## Goal

Every demo of this brief is prepared and played through `make demo`, in both versions, with its page saying what is
left to the presenter after each action and step.

## Steps

For each demo below, in the order given:

1. Page: replace `## Before you start` by `## Presenter lifecycle` with its six `###` sections. Move every checklist
   item into the section where the presenter needs it (sign-ins and warm-ups under Start, the probe under Check), and
   write "Nothing to do." where the file leaves nothing to the presenter. Keep the steps' tables unchanged unless a row
   names a command the file now runs for the presenter; then say so in the Do cell.
2. Files under `ansible/demos/<id>/`: fill `status.yml` and `check.yml` from the reads of the page's status banner;
   fill `start.yml` and `stop.yml` when the page asks for a preparation or a clean-up that a script can do; declare
   every changing unit in `demo.yml`; check every step file against its row (reads run, the rest in `not_run`).
3. Rehearse: `make demo rehearse <id> 5` and `make demo rehearse <id> 15`. A demo whose manifest declares a changing
   unit is rehearsed only after the owner's named go for that demo, with `DEMO_CONFIRM=<id>`. Space out the demos that
   run probes, so persona budgets do not reach 429.
4. Attach each rehearsal report to the Result of this brief, and fix the page or the files until it ends with
   `RESULT: PASS` or with failures the page explains.

## The demos

- `blender-3d`: Install = the add-on on the presenter's workstation (`evaluations/blender/install_addon.sh`), the platform entry verified (`zuno_ai_gateway_workstation_entry`, the HTTPRoute, AuthPolicy and RateLimitPolicy); Uninstall = `install_addon.sh --remove` only, by the owner's decision of 2026-11-14 (closing the platform entry needs a git push and is printed as an owner action); Appendix C moves into the lifecycle sections; Check = probe `blender`.
- `world-model`: Install refuses until `zuno_world_model_enabled: true` is on `origin/devel`, then runs `make d0 install world-model-gpu` and `make d2 install world-model` as local playbooks, with the owner's double approval printed for the GPU node; Uninstall reverses it and never scales `zuno-gpu-a`. By the owner's decision of 2026-11-14 the demo is implemented, not rehearsed in full while no GPU capacity exists: its rehearsal covers status, check, the read-only steps and a no-op uninstall, and the page keeps "not show-ready". The zuno-worldmodels session may move the GPU to another instance type; coordinate before editing `world-model.md`.

## Acceptance

- The catalogue test passes with every demo of this brief counted as moved.
- Each demo has a 5-minute and a 15-minute rehearsal report ending with `RESULT: PASS`, or failures the page explains.
- Every "Nothing to do." and "Nothing to run." is deliberate.

## Result (2026-11-15)

Files by zuno-demo-reorg-coder, pages reviewed against them by zuno-demo-reorg-writer, rehearsals by
zuno-demo-reorg-demo333. Both demos passed both rehearsals, 4 of 4 `RESULT: PASS`
([evidence](../evidence/wp-279-blender-world-model-rehearsals-2026-11-15.md)), with the units the owner decided not to
rehearse reported as skipped:

- `blender-3d`: install and uninstall run `install_addon.sh` on the presenter's workstation, so a rehearsal skips both.
- `world-model`: install is skipped; it only verifies and prints the owner's actions, and never creates the GPU node.
  Uninstall removes nothing and prints the owner's three actions.

The `world-model` PASS does not make the demo show-ready: it is switched off (`zuno_world_model_enabled: false`), with
no GPU node and no application, and its check passes because the probe reports the demo as roadmap. The rehearsal
proves that the files and the page play; the page keeps "not show-ready" until a rehearsal with the GPU node, which
needs the owner's double approval.
