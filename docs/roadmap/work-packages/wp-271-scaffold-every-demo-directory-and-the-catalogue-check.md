# WP-271: Scaffold every demo directory and the catalogue check

- **State:** Done (2026-11-15)
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-270](wp-270-build-the-make-demo-lifecycle-engine.md)
- **Related:** [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md), [WP-274](wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md)
- **Target:** v0.16
- **Estimated files touched:** ~530: `platform/demo/scaffold.py`, 36 directories under `ansible/demos/` (one manifest, six action files and one file per timed row each), `platform/demo/tests/test_demo_catalogue.py`, `.github/workflows/lint.yml`

> Why: ADR-0616 clause 3 makes every action and step file mandatory, and clause 14 makes CI keep them in step with the
> pages. Generating them from the pages leaves the rollout to fill in automation, not to create files.

## Goal

Every demo of the catalogue has its directory with all its files, most of them `nothing_to_run` or pre-filled reads,
and CI fails as soon as a page and its files disagree.

## Steps

1. Write `platform/demo/scaffold.py --write [--only <id>]`, idempotent, never overwriting a file:
   - `demo.yml`: `kind` (scenario or workshop), `page`, `probes` (from the banner phrase ``golden-path probe `x` `` and
     the README "Golden-path probe" column), `browser` (dify, open-webui, kagent, openclaw, unifai for the UnifAI pages),
     `mutations: {}`, and `steps:` metadata for rows marked optional or whose Do commands `readonly.py` rejects;
   - the six action files as an include of `_lib/nothing_to_run.yml`, with a comment naming the page section;
   - one `steps/MM-SS.yml` per timed row: Do commands accepted by `readonly.py` go into `run_reads` verbatim; the others
     are listed under `not_run` with the reason; a row with no command includes `nothing_to_run`.
2. Run it for the 30 scenarios. Workshop agendas are left to WP-280; create their directories with the six action
   files only.
3. Write `platform/demo/tests/test_demo_catalogue.py`:
   - every scenario page that has moved (has `## Presenter lifecycle`) holds exactly `### Status`, `### Check`,
     `### Install`, `### Start`, `### Stop`, `### Uninstall`, in that order, none empty;
   - every timed row has a step file and every step file a row; the six action files exist;
   - every file loads as a task list; a unit not declared changing uses only `_lib` reads, `kubernetes.core.k8s_info`,
     `debug`, `set_fact`, `assert` and `fail`; every `cmd` passes `readonly.py`;
   - every backticked `oc`, `make`, `curl` or `git` command of a Do cell is covered by a `cmd`, a `page_text` or a
     `not_run` entry;
   - only the world-model directory references a MachineSet, and nothing scales `zuno-gpu-a`;
   - every `make demo <verb>` written under `docs/` is a verb of `DEMO_VERBS`.
   Until WP-280, the lifecycle-section assertion is skipped for a page that has not moved; the list of moved pages
   shrinks to nothing by WP-281.
4. Add the test to the docs job of `.github/workflows/lint.yml`.

## Acceptance

- 36 directories exist; the test passes; removing one step file or adding one timed row to a page makes it fail.
- `make demo list` shows the 36 demos with their step counts.

## Result (2026-11-15)

Built by zuno-demo-reorg-coder, reviewed and merged by zuno-demo-reorg.

- First commit, the four review findings of WP-270: the `$(`/`${`/backtick check reads quotes like a shell (vault-pki
  1:00 `awk '{print $(NF-1)}'` runs), `strip_watch_flags` never raises, any `<...>` holding letters, digits or colons
  is a placeholder, and `$NAME` arguments come from the manifest's `env:`, the step's `demo_env` or a command's
  `env:` (passed in the environment, one argv element each, masked when the name holds KEY, TOKEN, PASSWORD or
  SECRET), else the read is refused. 149 of the 152 live-proven Do commands pass; the other three are resolved in
  their step files.
- `platform/demo/scaffold.py` (idempotent, never overwrites) generated 36 directories, 684 files: for each of the 30
  scenarios a manifest, six action files and one step file per timed row (432 steps); for each of the 6 workshops a
  manifest (`agenda: []`, WP-280) and six `nothing_to_run` actions. Status and check files are pre-filled from the
  demo333 session's live inventory of 2026-11-14 (Applications, workloads, Routes, Ready conditions with the `phase`,
  `state`, `parents` and `exists` modes, probes, browser checks); the DataScienceCluster's overall Ready and
  TrustyAIReady are never asserted (the parked `zuno-guardrails-smoke`). Step files carry the dry-run verdict of each
  read.
- `platform/demo/consistency.py` and `test_demo_catalogue.py` (18 tests, in CI) keep pages and files together: 0
  problems on devel and on the writer's migrated tree.
- Live, read-only: the 30 status files pass on demo333; `make demo rehearse service-mesh-kiali 5` ended `RESULT: PASS`.
- Follow-up carried by WP-272: the three operator CSV checks pin an exact version name; they move to a name-prefix
  check so an OLM upgrade does not fail them.

