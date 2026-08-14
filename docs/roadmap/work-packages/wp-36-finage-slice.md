# WP-36: Finage vertical slice (fourth of four; closes ADR-0326)

- **State:** Not started
- **ADRs:** ADR-0326 (Partially implemented -> Implemented when all four agents pass their gates)
- **Depends on:** WP-35 (merged + gate passed)
- **Estimated files touched:** ~20 (three parts a/b/c)

> Execute this brief as a standalone task from the repository root.
> **Pattern-relative: mirror the merged Advantage slice file-for-file**,
> substituting the Finage persona. Refresh against the merged slices before
> starting.

## Goal

Make Finage (finance agent) the fifth active agent with strictly
finance-scoped knowledge/tool access — least privilege proven by negative
scenarios — completing ADR-0326's four-agent generalization.

## ADR references

[docs/adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md](../../adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
— Finage bullet (verbatim): "Finage proves finance-scoped knowledge/tool
access without inheriting broad Sales/ADV access." Completion bullets
(verbatim): "Arkos, Comage, Advantage and Finage move from
`status: placeholder` to active only after their complete common acceptance
pattern passes." / "All five agents meet the evaluation/security gates
required by existing ADRs."

## Preconditions

- WP-35 merged + gate passed; `python3 platform/docs/check_docs.py` exits 0.
- Read: merged slices as templates; `docs/agents/finage.md` (persona —
  derive the finance knowledge/tool scope from it; if the persona requires a
  finance knowledge domain that does not exist, declare only what exists
  today and record the gap in the PR description rather than inventing a
  domain — a new domain would need its own ADR-0202-style addition).

## Repo changes (pattern-relative)

1. **Part (a):** real `agents/finage/` bundle: finance-scoped tasks;
   `zuno.allowed_knowledge` limited to what the persona justifies (plus
   `knowledge.project`); explicitly no sales/adv/sxa-legacy domains and no
   Salesforce/Aramis capabilities.
2. **Part (b):** `gitops/charts/finage/` + app + Keycloak (`agent_finage`,
   `finance` role) — as in prior slices; immutable tag rule applies.
3. **Part (c):** `evaluations/finage/` — 20 scenarios including negative
   boundary scenarios (sales/adv denial). **Human review checkpoint.**

## What NOT to touch

Standard list: existing ADR Decision text; the ADR-0344 dirty set; other
agents' slices; shared services; `gitops/apps/*` `targetRevision`.

## Acceptance checks

Same check set as WP-35 with `finage` substituted, plus:
- `! grep -rn "knowledge.sales\|knowledge.adv\|salesforce\." agents/finage/`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

1. User: review the 20 scenarios.
2. Operator: deploy, run the 75% gate, verify least-privilege denials with a
   real `finance`-role user, flip `agents/finage` to `active`.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0326 dated progress note (Finage merged, 4 of 4); tracker
  updated.
- **After all four gates have passed:** ADR-0326 →
  `Implemented - see \`agents/\`, \`evaluations/\`.`; index row
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet noting all five
  agents active.

## Out of scope / deferred

- Sixth-agent onboarding template (WP-41 / ADR-0306/0307).
