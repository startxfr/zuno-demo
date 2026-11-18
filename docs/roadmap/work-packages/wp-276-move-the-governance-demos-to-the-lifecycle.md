# WP-276: Move the governance demos to the lifecycle

- **State:** Done
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md) and [WP-274](wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md), and the owner's go at the gate of 2026-11-16
- **Related:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md), [WP-281](wp-281-rehearse-every-demo-and-workshop-end-to-end.md)
- **Target:** v0.16
- **Estimated files touched:** ~60: six pages under `docs/demo/scenarios/governance/` (guardrails is WP-273) and their directories

> Why: the governance demos carry the platform's message (sovereignty, routing, tools, budgets, delegation, identity); several run a probe on stage or change shared state while preparing, which the lifecycle must make explicit.

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

- `a2a-delegation-approval`: Check = probe `delegation-approval` (it proves the request and a refusal, as `eval-consultant-01`); the approval clicked by consultant-02 and the AAP job stay human steps; respect the AAP launch limit of 2 per 900 s between rehearsals.
- `ai-gateway-routing`: the `### The coding pair: C1 and C3` block is excluded from the steps (ADR-0616 clause 2); Check = probe `zuno-code`.
- `ai-gateway-sovereignty`: the 1:00 row runs `ONLY=sovereignty make demo golden-path` (allowed read); Check = probes `sovereignty`, `trace` with `unifai-tekos`.
- `identity-personas`: no probe; Start = the OpenShift sign-in of each persona whose group is missing (human: a first sign-in creates the OpenShift user and group); Check = reads of the Keycloak CR, the realm import, the OAuth provider, the RoleBindings.
- `mcp-tools-by-group`: the 5:00 row runs the `tools` probe; Check = probes `tools`, `open-webui`.
- `quotas`: no probe; Start spends sale-01's budget hours before the session, a changing unit declared in the manifest; the 15-minute "Optional replay" list is excluded from the steps and stays a printed owner action.

## Acceptance

- The catalogue test passes with every demo of this brief counted as moved.
- Each demo has a 5-minute and a 15-minute rehearsal report ending with `RESULT: PASS`, or failures the page explains.
- Every "Nothing to do." and "Nothing to run." is deliberate.

## Result (2026-11-15)

Files by zuno-demo-reorg-coder, pages reviewed against them by zuno-demo-reorg-writer, rehearsals by
zuno-demo-reorg-demo333 with the owner's go. The six demos passed both rehearsals, 12 of 12 `RESULT: PASS`, no failed
or skipped unit ([evidence](../evidence/wp-276-governance-rehearsals-2026-11-15.md)). Every report used is from after
the Argo CD restore of 02:06 and outside the image rebuild of 02:35 to 03:30, and ran with the status check that fails
on a dead or stale Argo CD. `quotas` is the only demo with a changing unit: its `start` spends token budget through
sale-01's and consultant-02's OpenClaw assistants and is not undone; it ran with the owner's named go. `guardrails`,
the seventh governance demo, is [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md).
