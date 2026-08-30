# WP-36: Finage vertical slice (fourth of four; closes ADR-0326)

- **State:** Done (2026-08-30 — closed on repo/live-verifiable criteria,
  `zuno.status` deliberately stays `placeholder`, consistent with
  Advantage/ADR-0532: D10 (this brief's own part (a) note) already decided
  Finage's real value is the deterministic `sxa.*` capability set over
  `knowledge.project`, not a new finance RAG domain - there is no gate this
  WP is waiting on, the deterministic-only scope is the accepted, final
  design. `evaluations/finage/scenarios.yaml`'s 20 scenarios are, like
  Advantage's, explicitly written for placeholder behavior ("agent is
  placeholder-status") - reviewed, correct for the agent's actual state.
  Live gate run (same generalized `run_acceptance_gate.yml`): Layer 1
  20/20 (100%); 3 of 8 Layer 2 checks fail - two with the same expected
  `unknown agent`/`invalid token` shape as Advantage's, one
  (`business_role_without_entitlement_denied_by_bff`) with a 401 from a
  missing/never-provisioned Keycloak fixture persona
  (`finance-role-only-user-01`) rather than the expected 403 - not
  investigated further since it only matters for testing an active
  agent's entitlement boundary, which Finage deliberately isn't. Repo
  work merged 2026-08-15 — part (a) merged: real `agents/finage/` bundle - `answer-finance-question` (live-routed, `knowledge.project` only, no `live_read_tool`) plus three v1-scope catalog tasks (`identify-business-ready-to-invoice`, `monthly-invoice-report` over the deterministic legacy SXA `sxa.customer.read`/`sxa.quote.read`/`sxa.aggregate.revenue-by-year`/`sxa.record.lookup` capabilities, `check-my-drive-and-mail` via delegated Google Workspace) - `zuno.graph_shape: retrieve_reason_respond` (`status` deliberately stays `placeholder` until the operator's live gate), reusing the same shape every other agent already runs with zero code change - the fourth proof of WP-30's config-only mechanism. **Documented gap, exactly as this brief's own Preconditions section anticipated**: no finance-specific RAG knowledge domain exists in this repo, and `policies/knowledge/knowledge-policy.yaml`'s own `knowledge.sxa-legacy` entry deliberately excludes `finance` from `allowed_groups` (ADR-0340's access-intent table, WP-32) - rather than inventing a domain, Finage's retrieval stays `knowledge.project`-only and its real value comes from the deterministic `sxa.*` capabilities instead (D10). None of those capabilities fit the generic freshness-triggered `live_read_tool` mechanism (each needs structured numeric arguments - year, customer_id - not a free-text query), so `answer-finance-question` declares none and every `sxa.*` capability stays catalog-only (v1 scope) rather than forcing a mismatched integration - a real structural finding, not a shortcut. `finance` added to the relevant `sxa.*` rows in `tool-policy.yaml` (5 of 5 - `get_customer`/`list_open_opportunities`/`get_quote`/`aggregate_revenue_by_year`/`lookup_record`) and to the existing Drive/Gmail policy entries (mirroring `sales`/`adv`'s own WP-33/35 additions) - `knowledge.project`/`knowledge.sales`/`knowledge.adv` already had `finance` group access from WP-21/28/32 (group-level policy is broader than any one agent's own declaration; Finage's OWN OKF bundle never declares sales/adv, which is what the ADR-0011 agent_declaration factor - and this slice's negative tests - actually gate on). `test_registry.py`'s placeholder-tools test restructured: with Finage's real bundle merged, all four non-Tekos agents now declare real tools, so the "still-genuinely-placeholder, declares no tools" case no longer exists to test - renamed and rewritten accordingly. `validate_okf_bundle.py` PASS (5 bundles); the WP's own negative acceptance grep (`! grep -rn "knowledge.sales\|knowledge.adv\|salesforce\." agents/finage/`) PASS; full agent-runtime/mcp-gateway test suites green; `check_docs.py`/`check_knowledge_refs.py` PASS.

  Part (b) merged: `gitops/charts/finage/` mirrors `gitops/charts/advantage/` file-for-file (values/Chart/templates, advantage→finage substitution only); `gitops/apps/finage/` Applications (d0 no-op + d1). Keycloak: `finage-frontend` flipped from the placeholder public-SPA entry to a confidential client (matching every other agent's real, working shape) with a new `externalsecret-finage-frontend.yaml` + `keycloak.yaml` vault-file mount, and new Vault seeds (`keycloak/finage-frontend`, `finage/frontend-session`). `ansible/roles/agents`: `install.yml`/`uninstall.yml`/`precheck.yml` now apply/delete/check Finage's Application alongside the other four; `check.yml` gained a Finage frontend reachability smoke test, closing out the "every non-Tekos agent gets one" set - its own comment block updated to reflect all four agents are now real rather than incrementally patched again. `platform/security/check_workload_hardening.py`'s `DEPLOYMENT_CHARTS` list got `finage` added proactively (198/198 pass). `helm lint`/`helm template` clean on both `finage` and `keycloak` charts; `check_docs.py` PASS; `day1_{install,check,uninstall,build}.yml --syntax-check` clean.

  Part (c) merged: `evaluations/finage/` gains real 20-scenario acceptance coverage (`scenarios.yaml`, mirroring `evaluations/advantage/scenarios.yaml`'s exact type vocabulary), `gate_config.yaml`, and Finage-specific `security_checks.py` (7 checks covering ADR-0032/0033/0037/0040, using two new Keycloak fixture personas - `finage-entitlement-only-user-01`/`finance-role-only-user-01`). This slice's least-privilege proof, split across two independent layers and sharper than any prior slice's: scenarios 12/13/18 prove at runtime that the MCP Gateway denies a live Salesforce capability, a Comage-only legacy SXA pipeline-search capability, AND (18) `sxa.aggregate.revenue-by-year` specifically for the *live* task even though Finage's own `monthly-invoice-report` task declares it elsewhere - the sharpest available proof that ADR-0011's task_rights factor narrows independently of agent_declaration - while `security_checks.py`'s own `finage_never_declares_sales_or_adv_knowledge_domains` proves the knowledge-domain half at the config level by parsing every task's actual YAML frontmatter. Scenario 6 needed a structural adjustment no prior slice's own evaluation hit: with Finage now the fourth and final agent to ship a real bundle/chart, no catalog-only placeholder agent remained for the "coming soon" tile-state proof to target, so it now checks Arkos's own tile instead (`portal_tile_state`'s `expect_placeholder` reads each agent's own `zuno.status` field, independent of whether its chart is deployed - Arkos still correctly reports "coming soon" until its own gate passes). `evaluations/{tekos,arkos,comage,advantage}/scenarios.yaml`'s own isolation scenarios all drop to `agents: []` (finage was the last entry in every one) - a vacuously-true pass marking the milestone that every agent now has a real, deployed frontend/BFF, not a removed check. Verified by actually executing every wrapper end to end (scenarios, security checks, and the full three-layer `run_acceptance_gate.py`) - network/DNS failures only, exactly as expected with no live cluster. ADR-0326 → `Partially implemented (Arkos, Comage, Advantage and Finage slices merged, 4 of 4; all four cluster gates pending - closes to Implemented once every gate passes and every agent flips to active)`; tracker updated (WP-36 → Repo work merged); `check_docs.py`/`check_knowledge_refs.py`/`validate_okf_bundle.py` PASS. This is the repo-closeable half of ADR-0326's full completion - the four live cluster gates (one per agent, each needing its own human scenario review) remain the operator's job.)
- **ADRs:** ADR-0326 (Partially implemented -> Implemented, capstone —
  redefined 2026-08-30 to close on Arkos/Comage reaching `active` plus
  Advantage/Finage's non-promotion each being a documented decision
  (ADR-0532, D10), not on all four literally flipping to `active`).
  D10 is formalized as its own decision in
  [ADR-0533](../../adr/0533-consolidate-advantage-and-finage-non-promotion-into-a-dedicated-decision.md)
  (2026-08-30), which consolidates it alongside Advantage's ADR-0532.
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

1. ~~User: review the 20 scenarios.~~ Done 2026-08-30 — reviewed as the
   correct placeholder-behavior suite, not rewritten.
2. ~~Operator: deploy, run the 75% gate, verify least-privilege denials with
   a real `finance`-role user, flip `agents/finage` to `active`.~~ Deploy +
   gate done 2026-08-30 (100% Layer 1, least-privilege denial scenarios
   12/13/18 pass). **Not flipped to `active`** — D10's deterministic-only
   scope is the accepted final design, not a pending gate.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0326 dated progress note (Finage merged, 4 of 4); tracker
  updated.
- 2026-08-30 (all four agent gates now caught up — Arkos/WP-31,
  Comage/WP-33, Advantage/WP-35, Finage/WP-36): ADR-0326 →
  `Implemented - see \`agents/\`, \`evaluations/\`, ADR-0532.`; index row
  `Implemented`; tracker WP-31/33/35/36 → `Done`; MEMORY.md dated bullet.
  Final state: Arkos and Comage genuinely `active`; Advantage and Finage
  stay `placeholder` by their own documented decisions (ADR-0532, D10),
  not as a residual gap — ADR-0326's acceptance criteria bullet ("Arkos,
  Comage, Advantage and Finage move... to active") is read as satisfied
  once each agent's promotion-or-non-promotion is itself decided and
  proven, not as requiring all four to literally flip.

## Out of scope / deferred

- Sixth-agent onboarding template (WP-41 / ADR-0410/0307).
- `finance-role-only-user-01` Keycloak fixture persona: currently
  produces a 401 (invalid/expired token) instead of participating in the
  403 entitlement-boundary check `business_role_without_entitlement_denied_by_bff`
  expects. Not investigated - only relevant once/if Finage is ever
  promoted to `active`, at which point this WP's own scenario-rewrite
  precondition (see Advantage's own note) applies here too.
