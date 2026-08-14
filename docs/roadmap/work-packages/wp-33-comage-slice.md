# WP-33: Comage vertical slice (second of four)

- **State:** Not started
- **ADRs:** ADR-0326 (Partially implemented, 2 of 4)
- **Depends on:** WP-31 (merged — the slice template), WP-22, WP-23, WP-32, WP-24
- **Blocks:** WP-34 (Comage is the first LoRA candidate), WP-35
- **Estimated files touched:** ~22 (three parts a/b/c, mirroring WP-31)

> Execute this brief as a standalone task from the repository root.
> **This slice is pattern-relative: mirror WP-31's Arkos structure
> file-for-file**, substituting Comage's persona. Where this brief says
> "as in WP-31", open the corresponding Arkos file and replicate its shape.
> Refresh this brief against the merged Arkos slice before starting if
> anything conflicts.

## Goal

Make Comage (sales agent) the third active agent, proving the
indexed-read/live-action pattern: `knowledge.sales` preferred semantic
reads, live Salesforce MCP for freshness-sensitive reads and every write,
explicit `knowledge.sxa-legacy` access, delegated Google Workspace.

## ADR references

- [docs/adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md](../../adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
  — Comage bullet (verbatim): "Comage proves `knowledge.sales` preferred
  reads, live Salesforce freshness/write actions, delegated Google Workspace
  access and explicit legacy SXA access." Plus the mandatory common
  completion pattern (same as WP-31).
- ADR-0205/ADR-0206 (the routing/separation this slice must exercise for
  real), ADR-0340 (sales role scoping).

## Preconditions (verify before starting)

- WP-31 merged and its cluster gate passed (Arkos is the proven template).
- WP-22 (Salesforce adapter), WP-23 (SXA capabilities), WP-24 (freshness
  routing), WP-32 (roles) merged.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: the merged Arkos slice end to end (`agents/arkos/**`,
  `gitops/charts/arkos/`, `evaluations/arkos/**`, its graph shape module);
  `docs/agents/comage.md` (persona); `components/mcp-servers/sales-db/`.

## Repo changes (pattern-relative to WP-31)

1. **Part (a):** real `agents/comage/` bundle (tasks: deal-status Q&A from
   `knowledge.sales`; current-value check triggering live Salesforce read;
   opportunity update via write capability; historical comparison via
   `knowledge.sxa-legacy` deterministic capabilities). Graph shape: reuse an
   existing shape if the flow genuinely fits, else add one named shape (do
   not force novelty — ADR-0342's mechanism bullet is already discharged).
   `zuno.allowed_knowledge: [knowledge.sales, knowledge.sxa-legacy,
   knowledge.project]`; logical capabilities only
   (`salesforce.opportunity.read|create|update`, `drive.*`, `gmail.*` per
   persona; SXA capabilities from WP-23).
2. **Salesforce live MCP server:** template
   `components/mcp-servers/salesforce/` from WP-02's Confluence server
   (same structure, REST → Salesforce API), auth mode per ADR-0208 chosen
   explicitly in the binding (`service-identity` with server-side subject
   scoping unless delegated is available), binding entries + build-matrix +
   chart wiring exactly as WP-02 did.
3. **Part (b):** `gitops/charts/comage/` + app wiring + Keycloak
   entitlement `agent_comage` and `sales` role mappings — as in WP-31.
4. **Part (c):** `evaluations/comage/` — 20 scenarios (structure mirrors
   `evaluations/tekos/scenarios.yaml`), including: indexed-vs-live routing
   scenarios (ADR-0205 bullets exercised through a real agent), SXA
   role-denial security scenarios, C1/C2/C3 + external-eligibility
   scenarios. **Human review checkpoint before the gate run counts.**

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Arkos/Tekos slices; shared services (no forks).
- SXA write paths (Salesforce writes never target SXA — WP-23 invariant;
  add the negative test at the slice level too).
- `gitops/apps/*` `targetRevision`; immutable-tag rule applies (post-WP-04).

## Acceptance checks (run from repo root; all must pass)

- Same check set as WP-31 with `comage` substituted, plus:
- `python3 -m pytest components/mcp-servers/salesforce/tests/ -q`
- `! grep -rn "salesforce.com\|my.salesforce" agents/comage/` (no endpoints)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. User: review the 20 scenarios.
2. Operator: Salesforce credentials in Vault (path documented in the
   binding), deploy, run the acceptance gate at 75%, exercise one live
   freshness read + one write against the real (sandbox) Salesforce org,
   delegated Google Workspace action, and the SXA role-denial with a real
   user.
3. Operator: flip `agents/comage` to `active` after the gate passes.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0326 dated progress note (Comage merged, 2 of 4); status
  stays `Partially implemented`; tracker updated.
- After gate: progress note (Comage active); tracker → `Done`; MEMORY.md
  dated bullet.

## Out of scope / deferred

- LoRA adapter for Comage (WP-34 — needs this bundle as training target).
- Advantage/Finage (WP-35/36).
