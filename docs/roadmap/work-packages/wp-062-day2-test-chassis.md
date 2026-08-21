# WP-062: Day 2 test/stresstest chassis (delivers ADR-0057)

- **State:** Done (2026-08-21) - executed with three
  file-path refinements over this brief's original sketch (acceptance
  criteria unchanged): the per-agent availability-check loop lives at
  `ansible/tasks/day2_availability_check.yml` (shared, not inside any
  role, matching this repo's existing home for cross-role snippets like
  `resolve_cluster_base_domain.yml`) rather than
  `ansible/roles/agents/tasks/availability_check.yml`, since it needed to
  be `include_tasks`-able from both `check.yml` (the `agents` role) and
  the new Day 2 playbooks; the `platform` Job and the `test`/`stresstest`
  dispatch tasks live in a new `ansible/roles/day2/` role, not inside
  `agents`, since they aren't agent-specific; and
  `ansible/inventories/demo/group_vars/all.yml` does not exist as a
  single file - `day2_report_format: text` was added to
  `ansible/inventories/demo/group_vars/all/main.yml` instead. The
  `platform` Job's shared-service URL list was confirmed against each
  service's actual `gitops/charts/*/templates/service.yaml` (Service
  name/port/namespace) rather than assumed from `SERVICE_HEALTH_URLS`
  alone, and includes `ai-gateway` (not present in that Python map).
  `platform/testing/day2_report.py` also grew a small `--format`/stdin
  CLI (beyond this brief's library-only sketch) so Ansible/Jinja-built
  results can be rendered without duplicating renderer logic in YAML.

  **First live-cluster run (2026-08-21)** found and fixed two
  false-positive sources, plus a real bug (both documented as findings
  from this WP's own "Operator / human follow-up" step, not a change of
  scope): (1) the agents component originally checked every discovered
  `agents/*/agent.okf.md` bundle, including `soursage`/`cognos` -
  identity-footprint-only per ADR-0349 §6, no chart/deployment at all -
  which always 503'd; discovery now intersects with
  `gitops/charts/<agent>/` existing (same pattern
  `ansible/roles/day2/tasks/stresstest_job.yml` already uses), excluding
  them today and auto-including either the moment a real chart lands.
  (2) The platform component originally also probed the four MCP servers
  (confluence, git-forge, sales-db, salesforce) directly; live-confirmed
  every one of their `NetworkPolicy` resources accepts ingress only from
  `app.kubernetes.io/name: mcp-gateway` (ADR-0037) - this Job's
  `acceptance-gate` identity was never going to reach any of them, by
  design, so they were dropped from the target list entirely (their real
  reachability is proven the authorized way, through
  `make d2 stresstest`'s scenario checks, instead). (3) The early-abort
  bug in `ansible/roles/day2/tasks/test.yml` (an agents-only fail task
  aborted the play before the platform check ever ran) was fixed
  separately by introducing `ansible/tasks/day2_render_and_fail.yml`, a
  shared report-then-decide-once step both this command and
  `ansible/roles/agents/tasks/check.yml` now use.

  A second live-cluster confirmation run after these fixes is the
  remaining operator step.

  **Second live-cluster confirmation (2026-08-21):** ran `make d2 test`
  against the real cluster - `14/14 passed overall - PASS`. All six
  deployed agent frontends (advantage/arkos/comage/finage/naveo/tekos)
  and all four platform services (agent-runtime, ai-gateway, mcp-gateway,
  rag-service, healthz+readyz) passed; `soursage`/`cognos` correctly
  absent from the agent list and no individual MCP server rows appeared,
  confirming both false-positive fixes hold. `check.yml`'s consolidated
  loop-driven task list is confirmed live-equivalent to the old
  six-block form. ADR-0057's acceptance criteria are now fully
  discharged - flipped to Done/Implemented.
- **ADRs:** ADR-0057
- **Depends on:** WP-31 (agent-parameterized `run_scenarios.py`, the
  precedent this generalizes further), WP-43 (agent maturity model / OKF
  bundle discovery idiom)
- **Blocks:** WP-063
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root. Read
> the referenced ADR sections before editing. If the repository state
> contradicts a step, stop and report instead of improvising.

## Goal

Add `make day2|d2 test|stresstest [agents|platform|all]`, dispatching to
new `ansible/playbooks/day2_test.yml` / `day2_stresstest.yml`. Fully wire
`test` (availability only) end-to-end; leave `stresstest`'s real content as
a runnable stub for WP-063 to fill in. Build the shared
`platform/testing/day2_report.py` report engine (text/json/csv). Refactor
`ansible/roles/agents/tasks/check.yml`'s six per-agent `/healthz` blocks
into one loop-driven task list, reused by both `make day1 check agents` and
the new `make d2 test agents`.

## ADR references

ADR-0057 decisions 1-6 in full. Decision 6 (the `check.yml` refactor) is
the one step that touches existing, currently-passing behavior - see "What
NOT to touch" below for the parts of `check.yml` that must survive
unchanged.

## Preconditions (verify before starting)

- Read: `Makefile` (the full `DAY0_RECIPE`/`DAY1_RECIPE` `define` blocks,
  to copy the idiom exactly); `ansible/roles/agents/tasks/check.yml`
  (all six per-agent `/healthz` blocks plus the OKF/Arkos-CR checks that
  must be left alone); `ansible/roles/agents/tasks/run_acceptance_gate.yml`
  (the in-cluster Job pattern this WP's `platform` Job reuses);
  `evaluations/tekos/run_scenarios.py`'s `SERVICE_HEALTH_URLS` map;
  `evaluations/tekos/run_acceptance_gate.py` (the text-table + trailing
  JSON-line convention `day2_report.py` extends);
  `platform/supply-chain/validate_okf_bundle.py`'s `AGENTS_DIR.iterdir()`
  discovery idiom.
- Confirm `git status` is clean on `Makefile`, `ansible/`, `platform/`
  before editing (parallel sessions commit mid-turn in this repository).
- `python3 platform/docs/check_docs.py` exits 0 before starting.

## Repo changes (step by step)

1. `Makefile`: add `DAY2_VERBS := test stresstest`, `DAY2_COMPONENTS :=
   agents platform`, a `DAY2_RECIPE` `define` block mirroring
   `DAY0_RECIPE`/`DAY1_RECIPE` exactly (verb/component read from
   `MAKECMDGOALS` words 2/3, `day2`/`d2` targets sharing the recipe,
   component defaults to `all`, unsupported verb/component errors match
   the existing style). Add `day2`/`d2`/`test`/`stresstest`/`agents`/
   `platform` to the no-op `.PHONY` token list (skip any name already
   present, e.g. `agents` may already be a DAY1 token). Extend the `help`
   target's printf block with the new commands.
2. `platform/testing/day2_report.py` (new): `Day2Result` dataclass
   (`agent: str, layer: str, id: str, category: str, passed: bool, detail:
   str = "", duration_ms: float = 0.0`); `render_text(results) -> str`
   (table + per-category counts + overall N/M line, matching
   `run_acceptance_gate.py`'s existing style); `render_json(results,
   summary) -> str`; `render_csv(results) -> str`; a `write_report(results,
   summary, report_format, component) -> pathlib.Path | None` that writes
   to `evaluations/day2-reports/<timestamp>-<component>.<ext>` when
   `report_format` is `json` or `csv` (returns `None` for `text`, since
   text is only ever printed, not filed).
3. `ansible/inventories/demo/group_vars/all.yml`: add `day2_report_format:
   text`.
4. `ansible/roles/agents/tasks/availability_check.yml` (new): discover
   every `agents/*/agent.okf.md` bundle (Ansible `find`/`set_fact` loop,
   translating the Python `AGENTS_DIR.iterdir()` idiom), then loop a single
   `uri` task (`GET https://<agent>.{{ cluster_base_domain }}/healthz`,
   `status_code: 200`, `timeout: 10`, `failed_when: false`) per discovered
   agent, accumulating pass/fail into a fact list, then one `fail` task
   summarizing any that didn't respond 200 - functionally identical output
   to today's six blocks, structurally one loop.
5. `ansible/roles/agents/tasks/check.yml`: replace the six per-agent
   `/healthz` blocks (Tekos through Naveo) with `include_tasks:
   availability_check.yml`. Leave the OKF bundle validation, the
   catalog-only structural checks, the Keycloak CA ConfigMap check, the
   Arkos AIAgent CR condition check, and the final `run_acceptance_gate.yml`
   include exactly as they are.
6. `ansible/roles/agents/tasks/platform_health_check.yml` (new): a
   lightweight in-cluster Job (same ServiceAccount/NetworkPolicy
   allow-list posture as `run_acceptance_gate.yml`'s Job, but no
   ConfigMap-bundled test scripts, no credentials) that curls
   `/healthz` and `/readyz` for the shared service map mirroring
   `run_scenarios.py`'s `SERVICE_HEALTH_URLS` (agent-runtime,
   mcp-gateway, ai-gateway, rag-service, mcp-servers/*), collects results,
   and prints them via `day2_report.py`'s text renderer (pass the results
   out through the Job's stdout, fetched by `k8s_log` the same way
   `run_acceptance_gate.yml` already does).
7. `ansible/playbooks/day2_test.yml` (new): resolves
   `target_component`/`report_format`, dispatches to
   `include_role: agents, tasks_from: availability_check` for `agents`,
   to the new platform Job task file for `platform`, or both for `all`.
8. `ansible/playbooks/day2_stresstest.yml` (new): accepts
   `target_component`/`report_format`/`bulk_interactions`, currently a
   single `debug` task ("Day 2 stresstest content lands in WP-063 -
   ADR-0058") - a real, runnable no-op so the Makefile verb and dispatch
   path are provable end-to-end now, not merely stubbed in prose.
9. `evaluations/README.md` and `tests/README.md`: add one short sentence
   each pointing to the new `make d2 test`/`make d2 stresstest` commands.
   `Makefile` help text already covers the command reference; keep these
   additions to a pointer, not a duplicate description.

## What NOT to touch

Standard list; plus: `evaluations/tekos/run_acceptance_gate.py` and
`run_acceptance_gate.yml` (WP-063's territory - generalizing them from
Tekos-only is ADR-0058 decision 2, not this WP); any `stress_test.py`
content; any agent's `scenarios.yaml`/`security_checks.py`/`gate_checks.py`;
`policies/`; the OKF bundle validation, catalog-only structural checks,
Keycloak CA ConfigMap check, and Arkos AIAgent CR condition check inside
`check.yml` (only the six `/healthz` blocks are replaced).

## Acceptance checks (run from repo root; all must pass)

- `make d2 test agents`, `make d2 test platform`, `make d2 test` (all) run
  against a live cluster and print a text table by default.
- `EXTRA_VARS="-e report_format=json" make d2 test agents` and the same
  with `report_format=csv` each produce the corresponding artifact under
  `evaluations/day2-reports/`.
- `make day1 check agents` still passes with output unchanged in substance
  after the `check.yml` refactor.
- `make d2 stresstest` (any component) runs the WP-063 stub without
  erroring.
- `python3 platform/docs/check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

Run `make d2 test` against the real cluster once merged; confirm the
refactored `check.yml` still gates `make day1 check agents` correctly and
that the new `platform` component's Job reaches every shared service.

## Status updates (then re-run check_docs.py)

On merge with the operator confirmation above still outstanding: ADR-0057
→ `Partially implemented - repo work merged (Makefile/Ansible dispatch,
report engine, availability checks); live cluster confirmation pending
(WP-062)`. On operator confirmation: ADR-0057 → `Implemented - see
platform/testing/day2_report.py, ansible/playbooks/day2_test.yml,
ansible/roles/agents/tasks/availability_check.yml`. Update
`docs/adr/README.md`'s version-0 table, the roadmap Phase 7 tracker
(`docs/roadmap/v0.1-v0.3-implementation-roadmap.md`), and `MEMORY.md`
accordingly.

## Out of scope / deferred

- Real `d2 stresstest` content (contract/scenario/security/gate/
  stress_test aggregation, the acceptance-gate Job generalization, bulk
  interaction mode) - all WP-063 (ADR-0058).
