# WP-101: Provision a real Salesforce sandbox credential

- **State:** Not started (2026-08-30).
- **ADRs:** ADR-0512 (residual gap owner), ADR-0528 (its deferred live pass),
  ADR-0218 (the `fetch-salesforce` v0.7 cadence this also unblocks).
- **Depends on:** none in-repo - this is an operator/infra provisioning task.
  Every consumer already exists and is inert pending the credential.
- **Unblocks:** WP-33's deferred live Comage gate (one freshness read + one
  write against the real org), ADR-0528/WP-090's live Salesforce three-cause
  pass (404/403/503), and ADR-0218's `fetch-salesforce` cadence for
  `domains.sales` (currently shipped `enabled: false`).
- **Target:** v0.7.
- **Estimated files touched:** 0 in the application tree; 1 inventory
  secrets file (operator-held, not committed).

> Execute this brief as a standalone task from the repository root.

## Goal

Every piece of Salesforce-consuming code in this repository already exists,
is already tested against mocks, and is already wired to activate itself the
moment real credentials appear - there is nothing left to build. What is
missing is the credential itself: a real (sandbox is sufficient) Salesforce
org, a technical user, and its OAuth access token. This WP is the single
place that tracks obtaining that credential and running the confirming live
passes it unblocks, replacing three separate "blocked on sandbox" notes
scattered across WP-22, WP-33 and WP-090 with one owned follow-up.

## Why this wasn't done already

`ansible/roles/vault/tasks/install.yml` seeds `zuno/salesforce/technical`
in Vault only when `zuno_salesforce_url`/`zuno_salesforce_access_token`
differ from their `xxxxxx` placeholder default (lines ~909-914, ~970). They
never have, in any environment this repository has been installed into -
there is no Salesforce org anywhere in this cluster's history, sandbox or
otherwise. That is a genuine external dependency (an operator must obtain
sandbox access from Salesforce, or stand up a compatible mock endpoint),
not a repo defect, which is why it has sat as a residual note on ADR-0512
since it was authored and was recently found (2026-08-30) to have no owning
WP at all - `fetch-salesforce`'s v0.7 deferral (ADR-0218) mentions the same
credential gap but doesn't track obtaining it either.

## Operator / human follow-up (not executable by the model)

1. Obtain a Salesforce sandbox (or full) org and a technical/integration
   user with API access. Record its base URL and a long-lived OAuth access
   token (or a refresh flow - `components/mcp-servers/salesforce/` expects
   a bearer token; if the org only offers refresh tokens, that adaptation is
   this step's problem to solve, not a repo change).
2. Set `zuno_salesforce_url` and `zuno_salesforce_access_token` in the
   operator's inventory secrets (never committed - same handling as every
   other credential this playbook seeds).
3. Re-run the Vault-seeding play (`ansible/roles/vault`, `install.yml`).
   Confirm `zuno/salesforce/technical` now holds real `url`/`access_token`
   keys (`vault kv get zuno/salesforce/technical`).
4. Confirm the `salesforce-technical-credentials` ExternalSecret syncs
   (`SecretSyncedError` was WP-22's 2026-08-17 finding for the empty-Vault
   case; it should clear once step 3 lands).
5. Re-add the Salesforce MCP server to the install path: two
   `apply_gitops_app.yml` tasks were removed from
   `ansible/roles/mcp/tasks/install.yml` on 2026-08-23 specifically pending
   this credential (see WP-33's "Out of scope / deferred" section) - restore
   them and confirm `zuno-mcp-salesforce-d0`/`-d1` ArgoCD Applications sync.
6. Run the three passes this credential unblocks, each against the real org:
   - **WP-33 (Comage):** one live freshness read via `check-deal-status`'s
     `salesforce.opportunity.read` fallback, and one live write via
     `update-opportunity-status`. Flip `agents/comage` to `active` once
     confirmed (WP-33's own remaining Status-updates step).
   - **ADR-0528/WP-090:** set a real opportunity id on a test project via
     `POST`/`PUT /v1/projects` under an identity with `salesforce.opportunity.read`
     access; confirm the success path stamps `salesforce_verified_at`. Then
     force each of the three failure causes and confirm the mapped status
     code: an unknown/mistyped id -> 404, an id the caller's own identity
     cannot read -> 403, and (hardest to force live - a temporary network
     policy deny or a revoked token against the sandbox is the usual trick)
     an unreachable org -> 503.
   - **ADR-0218 (`fetch-salesforce`):** flip `domains.sales.enabled: true`
     in the RAG-ingestion chart, confirm one real KFP run completes and
     `knowledge.sales` gains fetched rows, then decide the recurring cadence
     per ADR-0105's hours-scale target.
7. If `finance` needs `salesforce.opportunity.read` by this point, that is
   still the standalone reviewed policy decision WP-090 already declined
   (2026-08-29) for lack of a backend - revisit it here now that one exists,
   per WP-090's own "Revisit when WP-22/WP-33 lands a sandbox" note.

## What NOT to touch

- No application code changes are anticipated. If the real org's auth flow,
  pagination, or SOQL quirks don't match `components/mcp-servers/salesforce/`'s
  fixture-derived assumptions, file that as its own bug/WP rather than
  folding a code fix into this credential-provisioning brief.

## Status updates (then re-run check_docs.py)

- After step 6's three passes all confirm: ADR-0512's residual-gap note ->
  resolved; WP-33 -> `Done` (agent flipped `active`); WP-090/ADR-0528 gain a
  dated live-pass confirmation note (their `Done`/`Implemented` status does
  not change - it was already reached without this); ADR-0218's
  `fetch-salesforce` cadence decision revisited; a dated `MEMORY.md` bullet
  recording that the standing sandbox gap is finally closed.

## Out of scope / deferred

- Building a mock/fake Salesforce endpoint as a permanent substitute for a
  real org - the acceptance criteria across WP-33/WP-090/ADR-0218 all
  specifically want a real-org pass, not a better fixture.
- Any Salesforce ingestion cadence beyond activating `fetch-salesforce`
  (ADR-0105's recurring-schedule tuning is a separate concern once live data
  volume is known).
