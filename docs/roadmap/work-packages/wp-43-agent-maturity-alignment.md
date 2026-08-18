# WP-43: Agent maturity alignment (promotes ADR-0502)

- **State:** Not started
- **ADRs:** ADR-0502
- **Depends on:** none (opens the OKF stream's Phase 1)
- **Blocks:** WP-44, WP-45, WP-46, WP-48
- **Estimated files touched:** ~14

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

Apply ADR-0502's two-stage maturity model to all eight agents: author the
promotion checklist, bring Cognos and Soursage to Stage-1 parity with the
real generator, and give every agent a README stating its stage, its
actual evolution and its next promotion step.

## ADR references

ADR-0502 (full file, no stub promotion needed): two sanctioned stages —
Stage 1 "scaffolded" (the `scaffold_agent.py` shape), Stage 2 "promoted"
(full skeleton with real content, `active` after the gate); stage
determined by criteria, never directory shape; classification as of
2026-08-18 recorded in the ADR's clause 4.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: ADR-0502; `platform/templates/agent/scaffold_agent.py` and its
  docstring; `agents/naveo/NEXT_STEPS.md`; one full-skeleton agent
  (`agents/finage/`).
- Confirm WP-27's MIG work and any parallel session's uncommitted state
  do not touch `agents/` (re-check `git status` immediately before
  editing — parallel sessions commit mid-turn in this repository).

## Repo changes (step by step)

1. `platform/templates/agent/PROMOTION.md` — the ADR-0502 clause-3
   checklist: scenario review → CR deploy → ADR-0027/0028 gate → grow
   Stage-2 directories (ADR-0503/0504 content) → flip `zuno.status` →
   update README. Update the generator so emitted `NEXT_STEPS.md`
   references it instead of restating steps 7–8.
2. Run the generator for **cognos** and **soursage** against their
   existing identities (same `zuno.name`, `access.groups`, Keycloak
   client; keep each agent's current `preferred_classification` and
   prose). Merge generator output with the existing `agent.okf.md`
   body text; keep `allowed_tools: []` semantics by keeping their
   `coming-soon`-equivalent task until real tasks are authored. Do NOT
   touch `realm-zuno.json` or `policies/` — both agents' identities
   already exist (ADR-0349).
3. Author/refresh all eight `agents/<name>/README.md` per the ADR-0503
   Stage templates' outline (hand-written here; the generated matrix
   pointer lands in WP-44): stage, evolution facts (CR-managed?, live
   route?, evaluation state), next promotion step. Fix
   `agents/finage/tasks/README.md`'s stale `coming-soon.md` description.
4. Run `python3 platform/okf/validate_okf_bundle.py` (all bundles),
   `python3 platform/docs/check_knowledge_refs.py`,
   `python3 platform/docs/check_docs.py` — all must pass.

## What NOT to touch

Standard list; plus: no `zuno.status` flips (no agent is promoted by
this WP); no policy or realm edits; no `gitops/` changes (Cognos/
Soursage get charts only when someone chooses to deploy them — out of
scope); `agents/*/tests/` untouched (WP-46).

## Acceptance checks (run from repo root; all must pass)

- All eight agents have a README whose stage line matches ADR-0502
  clause 4's classification.
- `agents/cognos/` and `agents/soursage/` contain
  `keycloak-fragment.json` + `NEXT_STEPS.md` and validate as bundles.
- The three validators above exit 0.

## Operator / human follow-up (not executable by the model)

None — documentation/structure only; no cluster state changes.

## Status updates (then re-run check_docs.py)

On merge: ADR-0502 → `Implemented - see agents/*/README.md and
platform/templates/agent/PROMOTION.md.` (no operator dependency); index
row + okf-roadmap tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Authorization matrices and deployment snapshots (WP-44/WP-45).
- `tests/` structure (WP-46). Any agent promotion.
