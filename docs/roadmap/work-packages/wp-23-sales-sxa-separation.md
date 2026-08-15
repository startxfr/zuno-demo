# WP-23: Sales vs SXA-legacy separation

- **State:** Operator pending (2026-08-15 — repo work merged: `sales.*` capabilities renamed to `sxa.*` in `platform/bindings/tools/tool-bindings.yaml`/`policies/tools/tool-policy.yaml` (legacy tool-name aliases kept, `sales.*` namespace vacated for WP-33); two new deterministic structured-query tools (`aggregate_revenue_by_year`, `lookup_record`, no raw-SQL path, `sxa.aggregate.revenue-by-year`/`sxa.record.lookup`, Sales+Direction/`board` only, C3 by default per `policies/knowledge/knowledge-policy.yaml`'s already-merged `knowledge.sxa-legacy` entry); `load-sxa-dump` idempotent re-index verified by test; binding-layer write-path guard test proving no `sales.*` capability resolves. Awaiting the operator follow-up below: real approved SXA snapshot load, live role-denial check with real Keycloak users, and the user's scheduling of the C3 field-level data review.)
- **ADRs:** ADR-0206 (To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-20 (merged), WP-21 (merged); WP-22's `load-sxa-dump` adapter
- **Blocks:** WP-33 (Comage needs both domains)
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root.

## Goal

Make `knowledge.sales` (current, Salesforce-sourced) and
`knowledge.sxa-legacy` (historical, dump-sourced) behave as separate
authorities: distinguishable metadata/citations, deterministic
structured-query capabilities for exact SXA aggregations (no LLM-generated
SQL), C3-by-default classification, and versioned snapshot discipline.

## ADR references

Primary: [docs/adr/0206-separate-current-salesforce-knowledge-from-legacy-sxa.md](../../adr/0206-separate-current-salesforce-knowledge-from-legacy-sxa.md)

Acceptance criteria: Salesforce records never become indistinguishable from SXA legacy records in metadata/citations; an authorized semantic question can search SXA schema plus historical data through `knowledge.sxa-legacy`; exact aggregations use deterministic structured-query capabilities, never arbitrary SQL; users without explicit Sales/Direction legacy authorization cannot retrieve SXA chunks or structured-query results; Salesforce writes never target the SXA database.

Key constraints from the ADR body: `knowledge.sxa-legacy` has two semantic
layers (schema knowledge; authorized historical records with lineage to
source table/row where feasible); retain the structured PostgreSQL SXA
representation and expose deterministic, policy-controlled query
capabilities; classify conservatively C3 by default until a field-level
review justifies lower; each import is a versioned snapshot (timestamp,
checksum/provenance, validation report), idempotent re-indexing; public
fixtures stay synthetic (ADR-0025).

## Preconditions (verify before starting)

- WP-21 merged (per-domain DBs); WP-22's `load-sxa-dump` adapter exists (or
  land this WP's policy/capability parts first and note the dependency).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `data/sxa/` (schema + what ADR-0016 migrated),
  `components/mcp-servers/sales-db/server.py` (the deterministic-query
  precedent — parameterized tools over the sales DB),
  `policies/knowledge/knowledge-policy.yaml`, `knowledge/sxa-legacy/domain.yaml`,
  `policies/data-classification/` (how C3 defaults are expressed).

## Repo changes (step by step)

1. **Policy:** in `policies/knowledge/knowledge-policy.yaml`, restrict
   `knowledge.sxa-legacy` to the Sales and Direction business roles;
   classification default C3. Ensure `knowledge.sales` and
   `knowledge.sxa-legacy` entries are distinct with their own constraints.
2. **Deterministic query capabilities:** extend
   `components/mcp-servers/sales-db/` (or a sibling server if the SXA DB is
   separate — check where the SXA structured data physically lives) with
   parameterized aggregation/lookup tools (e.g.
   `sxa.aggregate.revenue-by-year`, `sxa.record.lookup`) registered as
   logical capabilities in `platform/bindings/tools/tool-bindings.yaml` and
   `policies/tools/tool-policy.yaml`, restricted to Sales/Direction. No tool
   accepts raw SQL.
3. **Metadata/citations:** verify (and enforce in tests) that sales chunks
   and sxa-legacy chunks carry distinct `domain`, `source_type` and
   provenance metadata end to end, and citations render the domain
   distinction; add the snapshot fields (`snapshot_id`, import timestamp,
   checksum) to sxa-legacy metadata per WP-20's schema.
4. **Snapshot discipline:** in WP-22's `load-sxa-dump` adapter, enforce
   versioned-snapshot metadata + idempotent re-index (same snapshot loaded
   twice → no duplicates); validation report artifact per import.
5. **Write-path guard:** test that Salesforce write capabilities cannot
   resolve to the SXA database binding (fail closed in the binding layer).
6. **Tests:** one per acceptance bullet (fixtures; role-based denial via the
   WP-20 intersection).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Real commercial data (ADR-0025: public fixtures stay synthetic).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/mcp-servers/sales-db/tests/ components/rag-service/tests/ components/rag-ingestion/ -q`
- `python3 platform/docs/check_knowledge_refs.py` (exit 0)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `! grep -rn "SELECT" agents/` (no raw SQL in agent contracts)

## Operator / human follow-up (not executable by the model)

1. Operator: load one approved real SXA dump snapshot on cluster via the
   adapter; verify lineage/citation behavior and role-based denial with real
   Keycloak users.
2. User: schedule the field-level data review that could lower the C3
   default (record outcome as a policy change, not an ADR edit).

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0206 →
  `Partially implemented (policy, deterministic query capabilities, metadata separation and snapshot discipline merged; live snapshot load pending)`;
  index row to match; tracker → `Operator pending`.
- After operator load: ADR-0206 →
  `Implemented - see \`policies/knowledge/\`, \`components/mcp-servers/sales-db/\`.`;
  index row `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Live Salesforce MCP write tools (WP-33 / Comage slice, ADR-0208 auth mode).
- Freshness routing between `knowledge.sales` and live Salesforce (WP-24).
