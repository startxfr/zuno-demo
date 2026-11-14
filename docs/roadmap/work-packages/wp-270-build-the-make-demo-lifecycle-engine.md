# WP-270: Build the make demo lifecycle engine

- **State:** Done (2026-11-14)
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-269](wp-269-record-the-demo-lifecycle-decision-and-page-contract.md)
- **Related:** [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [WP-238](wp-238-golden-path-check-freeze-protocol-and-demo-day-runbook.md), [WP-243](wp-243-browser-tests-for-every-experience.md)
- **Target:** v0.16
- **Estimated files touched:** ~25: `platform/demo/*.py` and its tests, `ansible/playbooks/demo_run.yml`, `ansible/demos/_lib/*.yml`, the Makefile, `.github/workflows/lint.yml`

> Why: ADR-0616 clauses 1, 2, 3, 5, 7, 8 and 12 need one engine that every demo directory plugs into, so the rollout is
> only data and page text.

## Goal

`make demo <verb>` works for any demo whose directory exists under `ansible/demos/`: it runs the Ansible file of the
action or step locally, prints its result, then prints the matching page section, with the session, the guards and the
freeze marker of ADR-0616.

## Steps

1. **Python package `platform/demo/`** (stdlib, plus PyYAML which ships with Ansible):
   - `catalogue.py`: find the demos (scenario pages under `docs/demo/scenarios/*/` plus `unifai-live-rag.md`,
     `blender-3d.md`, `world-model.md`; workshops under `docs/demo/workshops/` plus `three-experiences.md` and
     `five-experiences.md`); the id is the file stem. Parse `##`/`###` sections fence-aware, with the GitHub slug rule of
     `platform/docs/check_docs.py` (`markdown_anchors`). Steps are the rows of the table whose header is
     `| Time | Do | Say | You should see |` inside `## 5-minute version` and `## 15-minute version`, with a first cell
     matching `^\d{1,2}:\d{2}$`. Split cells on `|` not preceded by `\`, then unescape `\|`. The 15-minute version is
     the 5-minute rows then the 15-minute rows; assert the line "Run the 5-minute version, then:" and unique, ascending
     times. `EXCLUDED_BLOCKS` names the four known extra blocks (routing `### The coding pair: C1 and C3`, the Blender
     `Order | Prompt | Measured | What the audience sees` table, the quotas "Optional replay" list, the world-model
     prose); any other table in a version section is an error.
   - `session.py`: `~/.config/zuno/demo-session.json` (`demo`, `version`, `position`, `total`) and
     `~/.config/zuno/demo-freeze.json` (who, when).
   - `guard.py`: changing actions and steps print a summary, then ask to type the demo id; without a TTY, refuse unless
     `DEMO_CONFIRM` equals the id; refuse `install`, `uninstall` and `rehearse` while the freeze marker exists; print the
     owner's double-approval requirement for any unit whose manifest declares `infra: true`.
   - `readonly.py`: the allowlist of ADR-0616 clause 5 (`oc get|describe|logs|explain|whoami|api-resources|version|
     auth can-i|adm top`, `oc set env ... --list`; pipes into `grep awk sort uniq head tail wc cut jq`; `git log|show`;
     GET-only `curl` with `$(oc whoami -t)` resolved in-process and masked; `make help`, `[ONLY=x] make demo
     golden-path`, `make dN check [c]`, `make d3 admit agents` without `UPDATE_LOCK`). Deny Secret reads other than
     `-o name`, `-w`/`--watch`/`-f`/`--follow`, redirects, `;`, `&&`, backticks, other `$(`, `xargs`. Run pipelines with
     `subprocess` and no shell; 120 s timeout (600 s for `make`). A `make dN check X` runs its local playbook
     (`ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/dayN_check.yml -e target_component=X`),
     never through AAP.
   - `runner.py`: write a vars file under `$XDG_RUNTIME_DIR` (`demo_units`, `demo_confirmed`, `demo_results_path`), run
     `ansible-playbook -i ansible/inventories/demo/hosts.yml ansible/playbooks/demo_run.yml -e @<file>` locally, read the
     results JSON. Steps and `status` keep the Ansible output in `~/.cache/zuno/demo/logs/`; the other actions stream it
     (`VERBOSE=1` always streams).
   - `render.py`: section text for a terminal (links stripped to their text, tables of 2 to 4 columns as blocks,
     wrapped); a step prints a header (`<id> · 15-minute · step 8/14 · 7:30`), the RESULT block (each command and 40
     lines of output, or "Nothing to run."), Do / Say / You should see, then `Next: ...` or `Last step done: make demo
     stop`. On a failure: `FAILED`, then the page's `If something goes wrong` rows, those citing the step time first.
   - `rehearse.py`: status, check, install, start, every step, stop, uninstall without pauses; changing steps are
     recorded `SKIPPED (mutating)`; a report `~/.cache/zuno/demo/rehearsals/<id>-<version>-<date>.md` and `RESULT:
     PASS|FAIL`.
   - `presenter.py`: the command line; exit 0 ok, 1 failed, 2 usage or refused; `--ids` for completion.
2. **Runner playbook `ansible/playbooks/demo_run.yml`**: resolve credentials and the base domain
   (`ansible/tasks/load_k8s_auth_env.yml`, `resolve_cluster_base_domain.yml`), check `demo_confirmed` again for every
   unit the manifest declares changing, then `include_tasks` each unit's file and append results to
   `demo_results_path`.
3. **Shared task files `ansible/demos/_lib/`**: `nothing_to_run.yml`, `run_reads.yml` (calls `readonly.py`),
   `argo_apps.yml`, `workloads.yml`, `routes.yml`, `cr_ready.yml`, `trainjob_evidence.yml`, `queue_probes.yml`,
   `queue_browser.yml`, `flush_checks.yml` (one `golden_path_probe.py --only` run and one `browser/run.sh` with
   `ONLY=`), `render.yml` (through `ansible/tasks/day2_render_and_fail.yml`).
4. **Makefile**: `DEMO_VERBS := list use status check install start stop uninstall step freeze rehearse golden-path
   browser`; when the first goal is `demo`, every following word becomes a no-op target (filtered against the real
   targets, `help` and `completion` included); `demo:` calls `ZUNO_REPO_ROOT=$(CURDIR) python3
   platform/demo/presenter.py $(DEMO_ARGS)` and no longer depends on `credentials-check`; `golden-path` and `browser`
   keep their behaviour; completion offers the ids, `next 1..N`, `5 15`, `on off`; `help` shows the grammar.
5. **Tests** in `platform/demo/tests/`: `test_catalogue_parser.py` (the 30 pages parse; k5 and k15 counts; the four
   exclusions; an unknown table fails), `test_readonly.py` (allowed and denied commands, the token mask),
   `test_guard_session.py` (TTY, `DEMO_CONFIRM` per id, freeze refusals, session moves). Wire them into the docs job of
   `.github/workflows/lint.yml`, with a smoke test `HOME=$(mktemp -d) make demo list`.

## Acceptance

- The three test files pass locally and in CI; `ansible-playbook --syntax-check` passes on `demo_run.yml`.
- With one hand-made demo directory (from WP-271 or a fixture), `make demo use <id> 15`, `make demo status` and
  `make demo step next` print a result and the right section.
- `DEMO_CONFIRM=<other id>` does not unlock a demo; the freeze marker refuses `install`.

## Result (2026-11-14)

Built by the coder session (zuno-demo-18) under zuno-demo-reorg's coordination, reviewed and merged by
zuno-demo-reorg: `platform/demo/` (catalogue, session, guard, readonly, runner, render, rehearse, presenter),
`ansible/playbooks/demo_run.yml`, twelve `ansible/demos/_lib/` task files, the Makefile grammar (golden-path and
browser unchanged), completion and help, three test files (68 cases, Python 3.9 and 3.11) with a fixture demo, and the
CI wiring (docs job; the end-to-end fixture cases in the ansible job).

- The parser reads the 30 scenario pages into 157 steps (5-minute) and 275 (15-minute), the four excluded blocks, and
  the six workshops; `make demo list` shows the 36 demos.
- Review: the 152 `oc` commands of the Do cells, all run live by the demo333 session on 2026-11-14 (140 with output,
  11 empty as their pages expect, none failing), pass the allowlist except two; 55 hostile or borderline commands
  (Secret reads in every form, writes, redirects, chaining, `tee`, `xargs`, non-GET `curl`, awk `system`, jq `env`,
  `oc config view --raw`) are refused.
- Carried by WP-271 as its first commit: the `$(`/`${` check must ignore single-quoted text (it refuses vault-pki 1:00,
  `awk '{print $(NF-1)}'`); `strip_watch_flags` must return a refusal instead of raising; a placeholder with `:` or
  digits (`<a node of the 1:00 step>`) must be reported as a placeholder, not a redirect; `$NAME` arguments must be
  resolved from the step's variables or refused (the `curl $MAAS/...` rows of two RHOAI pages).

