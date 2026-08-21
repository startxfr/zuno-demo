# WP-44: OKF authorization matrix (promotes ADR-0503, matrix half)

- **State:** Done (2026-08-18, Parts A+B in two commits). The generator
  emits the matrix between HTML markers in the agent.okf.md body (never
  the frontmatter, so the three service parsers are untouched); the
  lint step runs `--check --all` (every agent must carry a current
  section). Tamper test proven (edited cell → exit 1 → regenerated).
  Notable finding: zero `(no groups — unusable)` rows across all 8
  agents — every declared tool/domain has a non-empty `allowed_groups`,
  so no policy gap needed recording. Cognos/Soursage render the honest
  zero-capability sentence instead of an empty table. Quota column is
  `standard (implicit)` pending WP-54, as briefed.
- **ADRs:** ADR-0503 (with WP-45 completing its deployment half)
- **Depends on:** WP-43
- **Blocks:** WP-48, WP-54; soft-blocks WP-061 (prompt-example schema
  rides the same validator; WP-47, its abandoned predecessor, carried the
  same soft-block)
- **Estimated files touched:** ~6 (Part A) + ~6 (Part B)

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

Every `agent.okf.md` carries a generated, CI-validated
`## Authorization matrix` section rendering the complete
who × what × for-what × policy intersection, derived from the
frontmatter and policy YAML sources — drift fails lint.

## ADR references

ADR-0503 clauses 1–2 (matrix + generator/validator); clause 5 of
ADR-0511 adds the quota column *when quota policy exists* — until WP-54
lands, the generator renders the column as `standard (implicit)`.

## Preconditions (verify before starting)

- WP-43 merged (READMEs state stages; the matrix pointer slot exists).
- Read: `policies/tools/tool-policy.yaml` and
  `policies/knowledge/knowledge-policy.yaml` headers (the intersection
  formula), `platform/okf/schema/*.json`, one existing validator
  (`platform/docs/check_knowledge_refs.py`) for the repo's
  policy-as-code style.
- `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

**Part A — generator + exemplars (independently committable):**
1. `platform/okf/generate_authorization_matrix.py` — reads an agent's
   `agent.okf.md` + `tasks/*.md` + the three policy files; emits the
   matrix section per ADR-0503 clause 1 (one row per task × tool and
   task × knowledge pair; WHO/WHAT/FOR WHAT/POLICY columns; header
   paragraph with classification ceiling and `access.groups`; explicit
   `(no groups — unusable)` marker rows). `--check` mode diffs the
   committed section against regeneration and exits non-zero on drift.
2. Generate and commit the matrix into `agents/tekos/agent.okf.md` and
   `agents/naveo/agent.okf.md` (append as a body section — frontmatter
   untouched, so bundle validation is unaffected; verify with
   `validate_okf_bundle.py`).
3. Wire `--check` (all agents with a matrix section) into
   `.github/workflows/lint.yml`'s policy-as-code job as a blocking step.

**Part B — remaining six agents:**
4. Generate matrices for arkos, comage, advantage, finage, cognos,
   soursage (the last two render honestly: zero tool rows, matching
   their `allowed_tools: []`).

## What NOT to touch

Standard list; plus: the matrix is never read by any service — no
component code changes; no policy YAML edits (if generation exposes a
policy gap, record it in the WP state log for a follow-up, don't fix it
silently here).

## Acceptance checks (run from repo root; all must pass)

- `python3 platform/okf/generate_authorization_matrix.py --check` exits
  0; hand-editing one matrix cell makes it exit non-zero.
- Editing a `tool-policy.yaml` `allowed_groups` entry without
  regenerating fails the check (restore after proving).
- `validate_okf_bundle.py`, `check_knowledge_refs.py`,
  `check_docs.py` all pass.

## Operator / human follow-up (not executable by the model)

None.

## Status updates (then re-run check_docs.py)

After Part B merges **and** WP-45 merges: ADR-0503 →
`Implemented - see platform/okf/generate_authorization_matrix.py and
agents/*/deployment/.` If WP-45 lags, ADR-0503 →
`Partially implemented (matrix merged; deployment snapshots pending
WP-45)`. Index + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Deployment snapshots (WP-45). Quota column values beyond the implicit
  default (WP-54 re-runs generation).
