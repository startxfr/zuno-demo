# WP-36: Finage vertical slice (fourth of four; closes ADR-0326)

- **State:** Repo work in review (2026-08-15 — part (a) merged: real `agents/finage/` bundle - `answer-finance-question` (live-routed, `knowledge.project` only, no `live_read_tool`) plus three v1-scope catalog tasks (`identify-business-ready-to-invoice`, `monthly-invoice-report` over the deterministic legacy SXA `sxa.customer.read`/`sxa.quote.read`/`sxa.aggregate.revenue-by-year`/`sxa.record.lookup` capabilities, `check-my-drive-and-mail` via delegated Google Workspace) - `zuno.graph_shape: retrieve_reason_respond` (`status` deliberately stays `placeholder` until the operator's live gate), reusing the same shape every other agent already runs with zero code change - the fourth proof of WP-30's config-only mechanism. **Documented gap, exactly as this brief's own Preconditions section anticipated**: no finance-specific RAG knowledge domain exists in this repo, and `policies/knowledge/knowledge-policy.yaml`'s own `knowledge.sxa-legacy` entry deliberately excludes `finance` from `allowed_groups` (ADR-0340's access-intent table, WP-32) - rather than inventing a domain, Finage's retrieval stays `knowledge.project`-only and its real value comes from the deterministic `sxa.*` capabilities instead (D10). None of those capabilities fit the generic freshness-triggered `live_read_tool` mechanism (each needs structured numeric arguments - year, customer_id - not a free-text query), so `answer-finance-question` declares none and every `sxa.*` capability stays catalog-only (v1 scope) rather than forcing a mismatched integration - a real structural finding, not a shortcut. `finance` added to the relevant `sxa.*` rows in `tool-policy.yaml` (5 of 5 - `get_customer`/`list_open_opportunities`/`get_quote`/`aggregate_revenue_by_year`/`lookup_record`) and to the existing Drive/Gmail policy entries (mirroring `sales`/`adv`'s own WP-33/35 additions) - `knowledge.project`/`knowledge.sales`/`knowledge.adv` already had `finance` group access from WP-21/28/32 (group-level policy is broader than any one agent's own declaration; Finage's OWN OKF bundle never declares sales/adv, which is what the ADR-0011 agent_declaration factor - and this slice's negative tests - actually gate on). `test_registry.py`'s placeholder-tools test restructured: with Finage's real bundle merged, all four non-Tekos agents now declare real tools, so the "still-genuinely-placeholder, declares no tools" case no longer exists to test - renamed and rewritten accordingly. `validate_okf_bundle.py` PASS (5 bundles); the WP's own negative acceptance grep (`! grep -rn "knowledge.sales\|knowledge.adv\|salesforce\." agents/finage/`) PASS; full agent-runtime/mcp-gateway test suites green; `check_docs.py`/`check_knowledge_refs.py` PASS. Parts (b)/(c) still pending - ADR status/tracker updates land with part (c) per this brief's own instruction.)
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
— Finage must prove finance-scoped knowledge/tool access without
inheriting broad Sales/ADV access. Completion requires: Arkos, Comage,
Advantage and Finage move from `status: placeholder` to active only after
their complete common acceptance pattern passes, and all five agents meet
the evaluation/security gates required by existing ADRs.

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
