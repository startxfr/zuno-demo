# WP-33: Comage vertical slice (second of four)

- **State:** Repo work merged (2026-08-15 — part (a) merged: real `agents/comage/` bundle - `check-deal-status` (live-routed: prefers `knowledge.sales`, falls back to a live `salesforce.opportunity.read` search when a mutable field's current value is asked for) plus three v1-scope catalog tasks (`update-opportunity-status`, `compare-historical-deals` over `knowledge.sxa-legacy`, `check-my-drive-and-mail` via delegated Google Workspace) - `zuno.graph_shape: retrieve_reason_respond` (`status` deliberately stays `placeholder` until the operator's live gate, per this brief's own Status-updates section), reusing Tekos's exact shape module rather than adding a new one (ADR-0326's "reuse if it genuinely fits" - the strongest available proof of WP-30's config-only mechanism). Reuse required generalizing `components/agent-runtime/app/graph/nodes.py`'s Tekos-hardcoded `retrieve_node`/`tool_call_node`/`reason_node` into `_make_*(agent, task)` closure factories, plus new `primary_task`/`live_read_tool` OKF fields so `GraphFactory` knows which task and live-read tool a shared shape binds to per agent, plus generalizing the context/citation helpers (`_build_context_block`, `_compute_source_mode`, `respond_node`) to read `tool_results` by whichever key is present rather than a hardcoded `search_confluence` literal. `components/mcp-servers/salesforce/` (templated from WP-02's confluence server): `read_opportunity` is deliberately query/search-shaped (matches `search_pages`'s own `{query, results: [{title,url,excerpt}], count}` contract) rather than an exact-id lookup, since that's what lets the generalized context/citation code work unmodified for a second agent; SOQL `LIKE` query escapes the one metacharacter that would otherwise break out of the string literal. `salesforce.opportunity.read/create/update` wired through bindings/policy (`sales`/`board` only - deliberately narrower than the `sxa.*` legacy rows, so Advantage never inherits current-Salesforce access implicitly per ADR-0326's own boundary); `sales` added to the existing Drive/Gmail policy entries for delegated Google Workspace access. New MCP server's build/deploy/vault-seed surface wired through the same `ansible/roles/mcp(+_build)` components confluence uses.
+
+  Part (b) merged: `gitops/charts/comage/` mirrors `gitops/charts/arkos/` file-for-file (values/Chart/templates, arkos→comage substitution only); `gitops/apps/comage/` Applications (d0 no-op + d1). Keycloak: `comage-frontend` flipped from the placeholder public-SPA entry to a confidential client (`publicClient: false` + vault-sourced secret + `clientAuthenticatorType: client-secret`, matching Tekos/Arkos's own real, working shape) with a new `externalsecret-comage-frontend.yaml` + `keycloak.yaml` vault-file mount, and new Vault seeds (`keycloak/comage-frontend`, `comage/frontend-session`) mirroring Tekos/Arkos's own idempotent-seed pattern. `ansible/roles/agents`: `install.yml`/`uninstall.yml`/`precheck.yml` now apply/delete/check Comage's Application alongside Tekos's/Arkos's; `check.yml` gained a Comage frontend reachability smoke test (deliberately not its behavioral acceptance gate - that needs part (c)'s human scenario review first). Also closed a real coverage gap while at it: `arkos` was never added to `platform/security/check_workload_hardening.py`'s `DEPLOYMENT_CHARTS` list when WP-31 part (b) shipped it, so its container `securityContext` was never actually being checked - added `arkos`, `comage` and `mcp-salesforce` now (162/162 pass, confirming the hardening was correct all along, just unverified).
+
+  Part (c) merged: `evaluations/comage/` gains real 20-scenario acceptance coverage (`scenarios.yaml`, mirroring `evaluations/arkos/scenarios.yaml`'s exact type vocabulary), `gate_config.yaml`, and Comage-specific `security_checks.py` (7 checks covering ADR-0032/0033/0034/0037/0040, using two new Keycloak fixture personas - `comage-entitlement-only-user-01`/`sales-role-only-user-01` - mirroring Arkos's own pattern). The signature proof this slice adds beyond Arkos's: scenarios 7/10 exercise ADR-0205's indexed-vs-live routing pair for real (an ordinary deal-status question stays indexed-only; a current-value question triggers a live `salesforce.opportunity.read` search visible in citations - Arkos's own live call is unconditional, so it never needed this distinction), and scenario 18 proves the ADR-0011 task_rights factor narrows independently of agent_declaration (`sxa.opportunity.search` denied for `check-deal-status` even though Comage's other task, `compare-historical-deals`, declares it - sharper than a tool no task declares at all). `evaluations/tekos/run_scenarios.py`'s `chat_triggers_tool` handler gained an `expect_source_contains` scenario field (default `confluence`, unchanged for Tekos/Arkos) so it can also recognize Salesforce-sourced citations; `SERVICE_HEALTH_URLS`/`SALESFORCE_MCP_URL` added for scenario 20. `evaluations/{tekos,arkos}/scenarios.yaml`'s own isolation scenarios dropped `comage` from their zero-pod placeholder lists (Comage's frontend/BFF are now genuinely deployed). Found and fixed a real latent bug while testing: `security_checks.py`'s `AGENT` constant resolves at import time from `run_scenarios.py`, but neither Arkos's nor (until now) Comage's own `security_checks.py` set it before that import - a bare `python3 security_checks.py` (this file's own README-documented invocation) would have silently defaulted to `AGENT=tekos` and failed on the wrong client-secret env var name; both now set it explicitly. Verified by actually executing every wrapper end to end (scenarios, security checks, and the full three-layer `run_acceptance_gate.py`) - network/DNS failures only, exactly as expected with no live cluster, confirming the AGENT-specific env var names, URLs and dynamic security-checks dispatch all resolve correctly. ADR-0326 → `Partially implemented (Arkos and Comage slices merged, 2 of 4; both cluster gates pending)`; tracker updated (WP-33 → Repo work merged); `check_docs.py`/`check_knowledge_refs.py`/`validate_okf_bundle.py`/`check_build_matrix.py` PASS; `helm lint`/`helm template` clean on `comage`/`keycloak`; full agent-runtime/mcp-gateway/salesforce test suites green.)
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
  — Comage must prove `knowledge.sales` preferred reads, live Salesforce
  freshness/write actions, delegated Google Workspace access and explicit
  legacy SXA access, plus the mandatory common completion pattern (same as
  WP-31).
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
