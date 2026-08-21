# WP-063: Stresstest content aggregation + bulk-interaction mode (delivers ADR-0058)

- **State:** Not started
- **ADRs:** ADR-0058
- **Depends on:** WP-062 (Day 2 chassis, report engine and agent-discovery
  mechanism must exist first; this WP fills in the stub
  `ansible/playbooks/day2_stresstest.yml` WP-062 leaves behind)
- **Blocks:** none
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root. Read
> the referenced ADR sections before editing. If the repository state
> contradicts a step, stop and report instead of improvising.

## Goal

Make `make d2 stresstest` run every existing test layer per discovered
agent through WP-062's report engine, generalize the acceptance-gate Job
mechanism from Tekos-only to agent-parameterized, and add the
bulk-interaction load mode with its interactive-prompt/`BULK=N` UX and
load-analysis report section.

## ADR references

ADR-0058 decisions 1-4 in full. Decision 2 (Job generalization) must not
change ADR-0053's mandatory-gate semantics or thresholds - `make day1
check agents`'s existing Tekos-only mandatory-gate behavior stays exactly
as it is; only the mechanism becomes reusable by this WP's per-agent
stresstest loop.

## Preconditions (verify before starting)

- Confirm WP-062 is at least "Repo work merged" - `platform/testing/day2_report.py`,
  `ansible/playbooks/day2_test.yml`/`day2_stresstest.yml` (stub), and
  `ansible/roles/agents/tasks/availability_check.yml` must already exist.
- Read: `evaluations/tekos/run_acceptance_gate.py` (the layer-combining
  pattern this WP generalizes); `ansible/roles/agents/tasks/run_acceptance_gate.yml`
  in full (the Job/ConfigMap/credential-mounting mechanism to
  parameterize); `evaluations/tekos/stress_test.py`'s module docstring (the
  existing "informational, not mandatory" posture this WP's aggregation
  must preserve); `evaluations/tekos/scenarios.yaml` (the prompt corpus
  bulk mode replays); `platform/okf/run_agent_contract_tests.py`.
- Component test prerequisites per this repo's own convention: build a
  venv from `evaluations/tekos/requirements.txt` (not system/user-site
  python) if adding local tests for the new Python modules.
- `python3 platform/docs/check_docs.py` exits 0 before starting.

## Repo changes (step by step)

1. `platform/testing/day2_stresstest.py` (new, in-cluster entrypoint,
   generalizing `run_acceptance_gate.py`'s layer-combining pattern): for
   each agent discovered via WP-062's discovery mechanism, best-effort-run
   (catching exceptions into a failed `Day2Result`, same `_safe()` idiom as
   `stress_test.py`) contract tests, `run_scenarios.py`,
   `security_checks.py`, `gate_checks.py`, `stress_test.py` - whichever
   exist for that agent (file-presence check, no hardcoded agent list).
   Normalize every result into `Day2Result` and render via
   `platform/testing/day2_report.py`. An agent with none of these present
   yields one explicit `Day2Result(..., category="coverage", passed=True,
   detail="no test content yet")` row, never a failure.
2. `ansible/roles/agents/tasks/run_acceptance_gate.yml` and
   `evaluations/tekos/run_acceptance_gate.py`: generalize from the single
   hardcoded Tekos Job/env-vars to a per-agent parameterization (the
   `FRONTEND_URL`/`<AGENT>_FRONTEND_CLIENT_SECRET` pattern, mirroring how
   `run_scenarios.py` already reads an `AGENT` environment variable at the
   Python layer per ADR-0342/WP-31). Keep `make day1 check agents`'s own
   invocation pinned to Tekos only and behaviorally unchanged - only make
   the mechanism reusable with a different agent name, don't change what
   the mandatory gate itself runs.
3. `platform/testing/day2_bulk.py` (new): given an agent name and its
   `scenarios.yaml`/`stress_test.py` prompt corpus, replay prompts
   sequentially up to a requested count (cycling through the corpus if
   `count` exceeds its length), recording pass/fail (reusing each prompt's
   existing assertion where derivable, e.g. "reply non-empty", "status
   200") plus latency per call. Produce one `Day2Result`-shaped summary row
   per agent: `category="bulk_load"`, `detail` carrying interaction count,
   error rate, p50/p95/max latency.
4. `Makefile`: extend the `DAY2_RECIPE`'s `stresstest` branch to prompt
   interactively for a bulk count when `BULK` is unset and stdin is a TTY
   (`read -r -p "Bulk interaction count [10]: " BULK; BULK="${BULK:-10}"`),
   skipping the prompt when `BULK` is already set (env or `make d2
   stresstest BULK=25`) or stdin is not a TTY (default to the same
   fallback, e.g. 10, non-interactively). Forward `-e
   bulk_interactions=$$BULK` to the playbook call.
5. `ansible/playbooks/day2_stresstest.yml`: replace WP-062's stub `debug`
   task with the real dispatch - runs `platform/testing/day2_stresstest.py`
   (decision 1) and, when `bulk_interactions` is set and greater than 0,
   also `platform/testing/day2_bulk.py` (decision 3) - as an in-cluster Job
   reusing WP-062's `platform_health_check.yml` Job scaffolding plus
   decision 2's generalized credential/ConfigMap mounting, looped per
   discovered agent with real content. Renders the combined result set
   through `day2_report.py` per `report_format`.
6. Add a guardrail: refuse `bulk_interactions` above a documented ceiling
   (e.g. 200 per agent) unless an explicit `-e allow_large_bulk=true`
   override is also passed; document the ceiling and its rationale (shared
   GPU/model capacity) in `day2_stresstest.yml`'s header comment.

## What NOT to touch

Standard list; plus: ADR-0053's mandatory-gate threshold/semantics (75%
scenario pass rate, 100% security/gate checks - unchanged); the actual
content of any existing `scenarios.yaml`/`stress_test.py`/
`security_checks.py` (only invoked, never rewritten); CI wiring
(`.github/workflows/`) - `d2 stresstest` stays operator-invoked only, never
scheduled or run in CI.

## Acceptance checks (run from repo root; all must pass)

- `make d2 stresstest agents` runs and reports contract/scenario/security/
  gate/stress-test results for every agent that has them, and an explicit
  "no content yet" row for agents that don't.
- `make d2 stresstest` (interactive terminal) prompts for `BULK`; `make d2
  stresstest BULK=5` runs non-interactively and the resulting report's
  `bulk_load` rows reflect 5 interactions per agent in scope.
- `make day1 check agents` (the ADR-0053 mandatory gate) still passes,
  unchanged in behavior, after the Job generalization in step 2.
- A `bulk_interactions` value above the documented ceiling is refused
  without `allow_large_bulk=true`.
- `python3 platform/docs/check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

Live run of `make d2 stresstest` with a real `BULK` value against the
cluster; confirm load-analysis numbers (error rate, latency percentiles)
are sane and that the ADR-0053 mandatory gate remains unaffected by the Job
generalization.

## Status updates (then re-run check_docs.py)

On merge with the operator confirmation above still outstanding: ADR-0058
→ `Partially implemented - repo work merged (content aggregation, Job
generalization, bulk-interaction mode); live cluster confirmation pending
(WP-063)`. On operator confirmation: ADR-0058 → `Implemented - see
platform/testing/day2_stresstest.py, platform/testing/day2_bulk.py,
ansible/playbooks/day2_stresstest.yml`. Update `docs/adr/README.md`'s
version-0 table, the roadmap Phase 7 tracker
(`docs/roadmap/v0.1-v0.3-implementation-roadmap.md`), and `MEMORY.md`
accordingly.

## Out of scope / deferred

- Any new adversarial/security/load-specific prompt content - bulk mode
  strictly replays what `scenarios.yaml`/`stress_test.py` already define.
- Scheduling `d2 stresstest` in CI or as a recurring job - deliberately an
  operator-invoked-only command per ADR-0058's security considerations.
