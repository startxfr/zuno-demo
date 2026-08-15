# WP-35: Advantage vertical slice (third of four)

- **State:** Repo work in review (2026-08-15 — part (a) merged: real `agents/advantage/` bundle - `answer-project-question` (live-routed, `knowledge.adv` + `knowledge.project`, no `live_read_tool` since no live Aramis MCP capability exists yet - WP-22 built a batch ingestion adapter, not a real-time query tool) plus three v1-scope catalog tasks (`identify-new-business-with-po`, `monthly-sales-report`, `check-my-drive-and-mail` via delegated Google Workspace) - `zuno.graph_shape: retrieve_reason_respond` (`status` deliberately stays `placeholder` until the operator's live gate, per this brief's own Status-updates section), reusing the same shape Tekos/Comage already run with zero code change - a third proof of WP-30's config-only mechanism. Signature proof: no task declares Comage's own current-sales knowledge domain or any live-CRM/legacy-SXA capability - the cross-domain boundary is explicit omission from Advantage's own OKF declaration (ADR-0011/ADR-0203 agent_declaration factor), never a runtime filter. `adv` added to the existing Drive/Gmail policy entries for delegated Google Workspace access (mirroring `sales`'s own WP-33 addition) - `knowledge.adv`/`knowledge.project` already had `adv` group access from WP-21/22/28, no policy change needed there. `test_registry.py`'s placeholder-tools test extended for Advantage's own real `declared_tools()`. `validate_okf_bundle.py` PASS (5 bundles); the WP's own negative acceptance grep (`! grep -rn "knowledge.sales\|salesforce\." agents/advantage/`) PASS; full agent-runtime/mcp-gateway test suites green; `check_docs.py`/`check_knowledge_refs.py` PASS.

  Part (b) merged: `gitops/charts/advantage/` mirrors `gitops/charts/comage/` file-for-file (values/Chart/templates, comage→advantage substitution only); `gitops/apps/advantage/` Applications (d0 no-op + d1). Keycloak: `advantage-frontend` flipped from the placeholder public-SPA entry to a confidential client (`publicClient: false` + vault-sourced secret + `clientAuthenticatorType: client-secret`, matching Tekos/Arkos/Comage's own real, working shape) with a new `externalsecret-advantage-frontend.yaml` + `keycloak.yaml` vault-file mount, and new Vault seeds (`keycloak/advantage-frontend`, `advantage/frontend-session`) mirroring the prior slices' own idempotent-seed pattern. `ansible/roles/agents`: `install.yml`/`uninstall.yml`/`precheck.yml` now apply/delete/check Advantage's Application alongside the other three; `check.yml` gained an Advantage frontend reachability smoke test. `platform/security/check_workload_hardening.py`'s `DEPLOYMENT_CHARTS` list got `advantage` added proactively this time (180/180 pass), rather than repeating the arkos/comage registration gap found and fixed in WP-33 part (b). `helm lint`/`helm template` clean on both `advantage` and `keycloak` charts; `check_docs.py` PASS; `day1_{install,check,uninstall,build}.yml --syntax-check` clean.

  Part (c) merged: `evaluations/advantage/` gains real 20-scenario acceptance coverage (`scenarios.yaml`, mirroring `evaluations/comage/scenarios.yaml`'s exact type vocabulary), `gate_config.yaml`, and Advantage-specific `security_checks.py` (7 checks covering ADR-0032/0033/0037/0040, using two new Keycloak fixture personas - `advantage-entitlement-only-user-01`/`adv-role-only-user-01` - mirroring the prior slices' own pattern). This slice's signature proof, split across two independent layers: scenarios 12/13 prove at runtime that the MCP Gateway denies a live Salesforce capability and a legacy SXA/sales capability (403, agent_declaration factor - Advantage never declares either), while `security_checks.py`'s own `advantage_never_declares_the_sales_knowledge_domain` proves the same fact at the config level by parsing every task's actual YAML frontmatter (never Markdown-body prose, which may legitimately reference other agents' capabilities by name - a real false positive this check's first draft hit and was corrected before commit). `evaluations/{tekos,arkos,comage}/scenarios.yaml`'s own isolation scenarios drop `advantage` from their zero-pod placeholder lists (Advantage's frontend/BFF are now genuinely deployed) - Finage is now the only agent left in any of those lists. Verified by actually executing every wrapper end to end (scenarios, security checks, and the full three-layer `run_acceptance_gate.py`) - network/DNS failures only, exactly as expected with no live cluster. ADR-0326 → `Partially implemented (Arkos, Comage and Advantage slices merged, 3 of 4; all three cluster gates pending)`; tracker updated (WP-35 → Repo work merged); `check_docs.py`/`check_knowledge_refs.py`/`validate_okf_bundle.py` PASS.)
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
