# WP-275: Move the experience demos to the lifecycle

- **State:** Done (2026-11-15)
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md) and [WP-274](wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md), and the owner's go at the gate of 2026-11-16
- **Related:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md), [WP-281](wp-281-rehearse-every-demo-and-workshop-end-to-end.md)
- **Target:** v0.16
- **Estimated files touched:** ~60: six pages under `docs/demo/scenarios/experiences/` and their directories

> Why: the six experience clients are the demos most often shown; each has a golden-path probe and, except Lightspeed and the UnifAI agents, a browser check, so their `check` is the first to reuse ADR-0605 and ADR-0606 for one demo.

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

- `dify`: Start = the Keycloak and Dify sign-ins (human; Dify's own password from Vault `zuno/dify/admin`, typed off screen), each imported app run once (the warm-up can go through the token proxy); Check = probes `dify`, `tools`, browser `dify`.
- `kagent`: Start = the "Skip wizard" screen (human) and one warm-up question; Check = probe `kagent`, browser `kagent`.
- `lightspeed`: Start = the console sign-in (human), `gpt-oss-20b` Ready; Check = probe `lightspeed` (its question stays a manual checklist step).
- `openclaw`: Start = two browser profiles and the Control UI passwords (read by the file from their Secrets and never printed; the page names where they are), one warm-up per assistant, `oc get claw`; Check = probe `openclaw`, browser `openclaw`.
- `open-webui`: Start = two profiles, a new chat, one warm-up; Check = probes `open-webui`, `zuno-code`, browser `open-webui`.
- `unifai-agents`: Start = two profiles and one warm-up; Check = probe `unifai-tekos`, browser `unifai`; the cluster-tools contrast at 3:00 has no probe and stays a rehearsal point.

## Acceptance

- The catalogue test passes with every demo of this brief counted as moved.
- Each demo has a 5-minute and a 15-minute rehearsal report ending with `RESULT: PASS`, or failures the page explains.
- Every "Nothing to do." and "Nothing to run." is deliberate.

## Result (2026-11-15)

Files by zuno-demo-reorg-coder, pages reviewed against them by zuno-demo-reorg-writer, rehearsals by
zuno-demo-reorg-demo333 with the owner's go. Each status reads what its page names (the Lightspeed `OLSConfig`
conditions, the UnifAI stack, team, bundle and workflow, the kagent Agent and RemoteMCPServer, both Claws, the
ExternalSecrets); each start wakes the model with the demo's own golden-path moment; no unit changes the cluster.
The six demos passed both rehearsals, 12 of 12 `RESULT: PASS`, no failed or skipped unit
([evidence](../evidence/wp-275-experiences-rehearsals-2026-11-15.md)).

