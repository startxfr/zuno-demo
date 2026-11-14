# WP-277: Move the RHOAI demos to the lifecycle

- **State:** Not started
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md) and [WP-274](wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md), and the owner's go at the gate of 2026-11-16
- **Related:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md), [WP-281](wp-281-rehearse-every-demo-and-workshop-end-to-end.md)
- **Target:** v0.16
- **Estimated files touched:** ~70: seven pages under `docs/demo/scenarios/rhoai/` and their directories

> Why: the RHOAI demos are mostly terminal and console tours, so most of their steps become reads run by the step file; two of them create or need objects that a session must clean up.

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

- `evaluation-trustyai-evalhub`: Check = EvalHub `Ready`, its route and RoleBinding, the last Complete evaluation Jobs (LMEvalJobs are off on 3.6 EA, say so).
- `external-models`: the `export MAAS=...` of the page becomes a variable resolved by the step file from the route; Check = the ExternalModels, MaaSModelRefs, subscriptions and auth policies.
- `genai-playground`: Start = two browser windows (human); Check = the OGXServer, `genai-pgvector`, the MCP server entry, the DSC conditions.
- `lora-pipeline-mlflow-kueue`: Check = the DSPA (its `Ready=False` of 2026-11-13 is a known failure the page names), `trainjob_evidence`, MLflow; the day-before `make d3 run mlops` is a changing unit, run only with the owner's go.
- `maas-portal-api-keys`: the live key creation at 1:00 is the demo's proof, so Start creates no key (corrected 2026-11-14 against the page: the page is the source of truth); the paste into `MAAS_API_KEY` stays manual; Stop tells the presenter to revoke by hand the key created live; Check = MaaS conditions and `gpt-oss-20b` Ready.
- `model-catalog-registry`: Check = the catalog reads; the registry part stays "not show-ready" while no `ModelRegistry` exists.
- `model-serving-llmd-mig`: every step is a read; `make d2 reconcile models` is owner-only and never on stage (`not_run`).

## Acceptance

- The catalogue test passes with every demo of this brief counted as moved.
- Each demo has a 5-minute and a 15-minute rehearsal report ending with `RESULT: PASS`, or failures the page explains.
- Every "Nothing to do." and "Nothing to run." is deliberate.
