# ADR-0502: Formalize the two-stage agent maturity model

- **Status:** Implemented - see `agents/*/README.md` and `platform/templates/agent/PROMOTION.md` (WP-43, 2026-08-18)
- **Target:** OKF v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

The eight bundles under `agents/` exhibit four different directory shapes
today, only one of which was ever deliberately designed:

- **Tekos** — the full ADR-0038 skeleton (`README.md`, `agent.okf.md`,
  `tasks/`, `prompts/`, `policies/`, `rag/`, `tools/`, `deployment/`,
  `tests/`), `zuno.status: active`, the only agent with a live Agent
  Runtime route — but its `policies/`, `rag/`, `tools/`, `deployment/` and
  `tests/` directories each contain a single one-line stub README.
- **Arkos, Comage, Advantage, Finage** — the same full skeleton with the
  same one-line stubs, `zuno.status: placeholder`, real multi-task bundles
  (ADR-0326 slices, all four merged). Arkos and the operator complicate the
  picture: Arkos is CR-managed live (`gitops/charts/arkos/`, WP-38's
  migration proof) while its bundle still says `placeholder` — directory
  shape and actual maturity have already diverged.
  `agents/finage/tasks/README.md` still describes a `coming-soon.md` that
  was replaced by four real task files — evidence that hand-maintained
  structure drifts silently.
- **Naveo** — the lean shape `platform/templates/agent/scaffold_agent.py`
  (ADR-0307, WP-41) generates: `agent.okf.md`, one real task + prompt,
  `keycloak-fragment.json`, `NEXT_STEPS.md`, a CR-managed chart and an
  evaluations skeleton — no top-level README, no `deployment/`,
  `policies/`, `rag/`, `tools/` or `tests/` directories at all.
- **Cognos, Soursage** — an identity footprint only (ADR-0349):
  `agent.okf.md` plus a `coming-soon` task with `allowed_tools: []`;
  neither the full skeleton nor the generator shape.

Nothing states which of these shapes a new agent should take, what
"placeholder → active" concretely requires, or which directories are
mandatory at which point. `NEXT_STEPS.md` (the generator's human
checklist) is the closest thing to a promotion path, but it exists only
for Naveo and is not a named contract.

## Decision

1. **Exactly two sanctioned agent shapes exist, named stages.**
   - **Stage 1 — "scaffolded"**: the `scaffold_agent.py` output, verbatim:
     `agent.okf.md` (`zuno.status: placeholder`), at least one real task
     and prompt, `keycloak-fragment.json`, `NEXT_STEPS.md`, a CR-managed
     GitOps chart (`gitops/charts/<name>/` rendering one `AIAgent` CR),
     `gitops/apps/<name>/` Applications and an `evaluations/<name>/`
     skeleton. No `README.md`, `deployment/`, `policies/`, `rag/`,
     `tools/` or `tests/` directories — Stage 1 deliberately has nothing
     real to put in them.
   - **Stage 2 — "promoted"**: the full ADR-0038 skeleton with **real
     content** in every directory it adds: a `README.md` stating stage and
     evolution, `deployment/` holding the ADR-0503 generated deployment
     snapshot, `tests/` holding the ADR-0504 structure, and
     `zuno.status: active` only after the ADR-0027/0028 evaluation gate.
     Empty stub directories are not Stage 2 — they are drift.

2. **Stage is determined by criteria, never by directory shape.** An agent
   is Stage 2 when and only when: (a) its bundle has passed the 20-scenario
   /75 % evaluation gate; (b) it is CR-managed (an `AIAgent` CR is its
   deployment interface — Tekos, the deliberate plain-manifest coexistence
   proof of ADR-0350/ADR-0308, is grandfathered); (c) its `deployment/` and
   `tests/` content exists per ADR-0503/ADR-0504; (d) `zuno.status:
   active`. Everything else is Stage 1, whatever directories it happens to
   have.

3. **The promotion path is a named, versioned checklist**,
   `platform/templates/agent/PROMOTION.md`, superseding the ad-hoc tail of
   `NEXT_STEPS.md` (steps 7–8 in Naveo's): human scenario review → operator
   deploy via CR → evaluation gate → grow the Stage-2 directories with the
   ADR-0503/0504 generated content → flip `zuno.status` to `active` →
   update the agent README. The generator emits `NEXT_STEPS.md` referencing
   this checklist instead of restating it.

4. **Current classification** (recorded here as of 2026-08-18, maintained
   thereafter in each agent's README, not by editing this ADR): Tekos —
   Stage 2 (grandfathered on criterion b). Arkos, Comage, Advantage,
   Finage — Stage 1 with reserved Stage-2 structure (a legacy shape:
   the empty directories are retained, not deleted, and gain real content
   at promotion). Naveo — Stage 1 (canonical). Cognos, Soursage — below
   Stage 1; each is brought to Stage-1 parity by running the real
   generator against its existing identity (same `zuno.name`, groups and
   Keycloak client, no new capabilities).

5. **Every agent README must state its stage, its actual evolution
   (CR-managed or not, live route or not, evaluation state) and its next
   promotion step.** Agents without a README (Naveo, Cognos, Soursage)
   get one; stale structure descriptions (Finage's tasks README) are
   corrected as part of the same alignment.

## Consequences

The scaffold generator and its CI test (`test_scaffold_validate_discard.py`)
become the single source of the Stage-1 shape; any change to the shape is a
generator change, never a per-agent edit. The four legacy full-skeleton
placeholders stop implying more maturity than they have. WP-43 executes the
alignment; ADR-0503 and ADR-0504 define the content that makes Stage 2 real
rather than structural.

## Security considerations

Bringing Cognos and Soursage to Stage-1 parity must not widen any grant:
the generator composes existing capabilities only, and both agents keep
`allowed_tools: []` until real tasks are authored through the normal review
path. Stage classification is documentation — it grants nothing;
`zuno.access.groups`, the policy files and the evaluation gate remain the
only authorization and promotion authorities (ADR-0040, ADR-0011,
ADR-0027/0028).

## Operational considerations

Stage is auditable from the repository alone (criteria a, c, d) plus one
cluster fact (criterion b's gate run, recorded in the evaluation
artifacts). `make day1 check agents` (the ADR-0053 gate) continues to
validate structure; the stage criteria give its findings a vocabulary.

## Acceptance criteria

- `platform/templates/agent/PROMOTION.md` exists and `NEXT_STEPS.md`
  output references it.
- All eight agent READMEs state stage, evolution and next step; Cognos and
  Soursage match the generator's Stage-1 output.
- `validate_okf_bundle.py`, `check_knowledge_refs.py` and
  `python3 platform/docs/check_docs.py` pass after the alignment.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0038](0038-use-standards-compliant-okf-v0-2-markdown-bundles.md)
- [ADR-0307](0307-support-self-service-agent-onboarding.md)
- [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
- [ADR-0349](0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md)
- [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md)
- [ADR-0410](0410-expand-the-agent-catalog-beyond-the-initial-five-agents.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0504](0504-define-the-agent-tests-directory-structure-and-promotion-gate.md)
