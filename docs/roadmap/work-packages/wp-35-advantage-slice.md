# WP-35: Advantage vertical slice (third of four)

- **State:** Repo work in review (2026-08-15 — part (a) merged: real `agents/advantage/` bundle - `answer-project-question` (live-routed, `knowledge.adv` + `knowledge.project`, no `live_read_tool` since no live Aramis MCP capability exists yet - WP-22 built a batch ingestion adapter, not a real-time query tool) plus three v1-scope catalog tasks (`identify-new-business-with-po`, `monthly-sales-report`, `check-my-drive-and-mail` via delegated Google Workspace) - `zuno.graph_shape: retrieve_reason_respond` (`status` deliberately stays `placeholder` until the operator's live gate, per this brief's own Status-updates section), reusing the same shape Tekos/Comage already run with zero code change - a third proof of WP-30's config-only mechanism. Signature proof: no task declares Comage's own current-sales knowledge domain or any live-CRM/legacy-SXA capability - the cross-domain boundary is explicit omission from Advantage's own OKF declaration (ADR-0011/ADR-0203 agent_declaration factor), never a runtime filter. `adv` added to the existing Drive/Gmail policy entries for delegated Google Workspace access (mirroring `sales`'s own WP-33 addition) - `knowledge.adv`/`knowledge.project` already had `adv` group access from WP-21/22/28, no policy change needed there. `test_registry.py`'s placeholder-tools test extended for Advantage's own real `declared_tools()`. `validate_okf_bundle.py` PASS (5 bundles); the WP's own negative acceptance grep (`! grep -rn "knowledge.sales\|salesforce\." agents/advantage/`) PASS; full agent-runtime/mcp-gateway test suites green; `check_docs.py`/`check_knowledge_refs.py` PASS. Parts (b)/(c) still pending - ADR status/tracker updates land with part (c) per this brief's own instruction.)
- **ADRs:** ADR-0326 (Partially implemented, 3 of 4)
- **Depends on:** WP-33 (merged + gate passed), WP-22 (Aramis adapter for `knowledge.adv`)
- **Blocks:** WP-36
- **Estimated files touched:** ~20 (three parts a/b/c)

> Execute this brief as a standalone task from the repository root.
> **Pattern-relative: mirror the merged Comage/Arkos slices file-for-file**,
> substituting the Advantage persona. Refresh against the merged slices
> before starting.

## Goal

Make Advantage (ADV/bid agent) the fourth active agent, proving the
cross-domain authorization boundary: `knowledge.adv` from Aramis as its
primary domain, with any cross-domain access explicitly declared — and
provably NOT inheriting Comage/Sales capabilities.

## ADR references

[docs/adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md](../../adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
— Advantage must prove `knowledge.adv` from Aramis and must not inherit
broader Comage/Sales capabilities implicitly, plus the mandatory common
completion pattern (as in WP-31/WP-33).

## Preconditions

- WP-33 merged + gate passed; WP-22's Aramis adapter merged and
  `knowledge.adv` populated (at least fixtures).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: merged `agents/comage/**` + `agents/arkos/**` as templates;
  `docs/agents/advantage.md` (persona).

## Repo changes (pattern-relative)

1. **Part (a):** real `agents/advantage/` bundle: tasks over
   `knowledge.adv` (bid/project knowledge Q&A, proposal support);
   `zuno.allowed_knowledge: [knowledge.adv, knowledge.project]` — NO sales
   or sxa-legacy domains; logical capabilities per persona (Drive/Gmail
   delegated; no Salesforce). Reuse an existing graph shape unless the flow
   genuinely needs a new one.
2. **Part (b):** `gitops/charts/advantage/` + app + Keycloak
   (`agent_advantage`, `adv` role) — as in prior slices; immutable tag rule
   applies.
3. **Part (c):** `evaluations/advantage/` — 20 scenarios mirroring the
   established structure, **including the negative boundary scenarios**:
   an Advantage task attempting `knowledge.sales` or a Salesforce capability
   is denied (this is the slice's signature proof). **Human review
   checkpoint before the gate run counts.**

## What NOT to touch

Standard list: existing ADR Decision text; the ADR-0344 dirty set; other
agents' slices; shared services (no forks); `gitops/apps/*`
`targetRevision`.

## Acceptance checks

Same check set as WP-33 with `advantage` substituted, plus:
- `! grep -rn "knowledge.sales\|salesforce\." agents/advantage/` (no implicit
  sales inheritance)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

1. User: review the 20 scenarios.
2. Operator: deploy, run the 75% gate, verify the cross-domain denial with a
   real `adv`-role user, flip `agents/advantage` to `active`.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0326 dated progress note (Advantage merged, 3 of 4);
  tracker updated. After gate: progress note (active); tracker → `Done`;
  MEMORY.md dated bullet.

## Out of scope / deferred

- Finage (WP-36). Aramis live credentials/config ride the WP-22 operator
  step.
