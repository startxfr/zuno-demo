# WP-46: Agent tests target structure (promotes ADR-0504)

- **State:** Done (2026-08-18). Structure landed for the five agents
  with `tests/` dirs (tekos, arkos, comage, advantage, finage): three
  subdirs each with a keep-file README defining its suite scope, main
  README stating the three-layer boundary + PROMOTION.md pointer. The
  runner enforces the per-subdir READMEs as structure (a first draft
  only checked dirs + main README — the brief's own delete-a-README
  acceptance test caught it; fixed and re-proven: violation → exit 1).
  Zero test content, as briefed (What-NOT-to-touch honored). Stage-1
  agents untouched. PROMOTION.md step 4 already named ADR-0504 —
  brief step 3 satisfied by WP-43, no edit needed. Lint gains the
  blocking ADR-0504 step.
- **ADRs:** ADR-0504
- **Depends on:** WP-43
- **Blocks:** WP-48
- **Estimated files touched:** ~12

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

Land ADR-0504's target structure in every existing `agents/<name>/tests/`
directory (tekos, arkos, comage, advantage, finage) — `contract/`,
`tasks/`, `prompts/` plus a README stating how the suite runs and the
three-layer boundaries — and wire the (currently empty) suite runner
into the lint chain. **Zero test content**: filling suites is
promotion-time work per PROMOTION.md.

## ADR references

ADR-0504 clauses 1–4. Layer boundaries: schema/structural
(platform-wide validators) — contract (this structure, repo-side) —
behavioral (`evaluations/<name>/`, ADR-0027/0028, untouched).

## Preconditions (verify before starting)

- WP-43 merged (PROMOTION.md exists to reference).
- Read: ADR-0504; `.github/workflows/lint.yml`'s policy-as-code job;
  `evaluations/naveo/` layout (for the boundary statement, not to copy).
- `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. `platform/okf/run_agent_contract_tests.py` — discovers
   `agents/*/tests/{contract,tasks,prompts}/` content and runs it;
   with zero content present it reports per-agent "structure present,
   no suites yet" and exits 0. Structure violations (a `tests/` dir
   missing the three subdirectories or README) exit non-zero.
2. In each of the five existing `tests/` directories: create
   `contract/`, `tasks/`, `prompts/` (each with a one-paragraph README
   stating what belongs there per ADR-0504 clause 1 — these READMEs
   are the keep-files) and replace the stub `tests/README.md` with the
   runner invocation, the layer boundaries, and the PROMOTION.md
   pointer.
3. Update `platform/templates/agent/PROMOTION.md`'s Stage-2 criteria
   to name "fill `tests/` per ADR-0504" explicitly (if WP-43 didn't
   already word it so).
4. Wire the runner into `.github/workflows/lint.yml`'s policy-as-code
   job as a blocking step.

## What NOT to touch

Standard list; plus: **no test content** — not even one example test
(the first real suites belong to whichever WP promotes an agent);
`evaluations/` untouched; Stage-1 agents (naveo, cognos, soursage) get
no `tests/` directory.

## Acceptance checks (run from repo root; all must pass)

- `python3 platform/okf/run_agent_contract_tests.py` exits 0 on the
  current tree; deleting one subdirectory README makes it exit
  non-zero (restore after proving).
- No `tests/` directory contains the old one-line stub text.
- `check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

None.

## Status updates (then re-run check_docs.py)

On merge: ADR-0504 → `Implemented - see
platform/okf/run_agent_contract_tests.py and agents/*/tests/.` (the
ADR defines structure, not content — structure merged is the decision
in effect). Index + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- All test content. Moving the suite to `zuno-okf` (rides WP-48/WP-50
  with the rest of `agents/` + `platform/okf/`).
