# WP-21: Multi-domain RAG platform core

- **State:** Not started
- **ADRs:** ADR-0204 part 1 (To be implemented -> Partially implemented; Implemented together with WP-22)
- **Depends on:** WP-20 (merged)
- **Blocks:** WP-22, WP-23, WP-24, WP-25, WP-28
- **Estimated files touched:** ~9

> Execute this brief as a standalone task from the repository root. ADR-0204
> is split: this WP is the retrieval/storage core; WP-22 is the ingestion
> source adapters. The ADR flips to Implemented only when both are done.

## Goal

Generalize `rag-service` from single-database retrieval to binding-resolved
multi-domain retrieval: a knowledge-backend binding layer under
`platform/bindings/knowledge/`, per-domain databases with dedicated
credentials on the shared PostgreSQL cluster, and domain-routed queries —
all behind the unchanged retrieval contract.

## ADR references

Primary: [docs/adr/0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md](../../adr/0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)

Acceptance criteria: at least two domains run on the same reusable RAG code without sharing database credentials; moving a domain to a different backend needs only knowledge binding/deployment config; agent OKF and knowledge policy contain no physical database/service endpoints; cross-domain retrieval occurs only when the active task is authorized for every requested domain.

Initial bindings from the ADR (left side stable contract, right side
environment binding data): `knowledge.tech -> rag-tech`,
`knowledge.sales -> rag-sales`, `knowledge.adv -> rag-adv`,
`knowledge.sxa-legacy -> rag-sxa-legacy`.

## Preconditions (verify before starting)

- WP-20 merged: `test -d knowledge && test -f policies/knowledge/knowledge-policy.yaml`.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/rag-service/app/` (connection handling, `search.py`),
  `gitops/charts/postgresql/values.yaml` (the `ragTechDatabase` block —
  ADR-0330's precedent for adding a database/role to the shared
  `zuno-postgresql` PGO cluster), `gitops/charts/rag-service/values.yaml`,
  `ansible/roles/rag/` (schema-apply kustomize path),
  `platform/bindings/tools/` (WP-01's registry — mirror its layout).

## Repo changes (step by step)

1. **Binding layer:** create `platform/bindings/knowledge/bindings.yaml` +
   README, mirroring `platform/bindings/tools/`: each domain maps to
   retrieval provider, database identity (name/secret reference — the secret
   itself stays in Vault/ESO), embedding provider, and ingestion config
   reference. Include all four domains; `rag-tech` reflects the existing
   ADR-0330 reality.
2. **Databases:** add `ragSalesDatabase`, `ragAdvDatabase`,
   `ragSxaLegacyDatabase` blocks to `gitops/charts/postgresql` mirroring the
   `ragTechDatabase` block exactly (dedicated owner roles `ragsales`,
   `ragadv`, `ragsxalegacy`).
3. **Schema lifecycle:** per-domain schema-apply following the existing
   pattern (`gitops/charts/rag-service/templates/job-schema-apply.yaml`,
   `ansible/roles/rag/kustomize/schema/`) parameterized by domain database;
   reuse `data/rag/schema/` DDL.
4. **rag-service routing:** replace the single connection with a
   binding-resolved per-domain connection pool; the query path takes the
   (already policy-authorized, WP-20) domain set and fans out only to
   authorized domains. The retrieval contract (request/response shape,
   citations, metadata) must not change.
5. **Secrets:** per-domain credentials via the existing External Secrets
   pattern in `gitops/charts/rag-service` — one secret per domain, never a
   shared superuser.
6. **Tests:** two fixture domains on the same code with distinct credentials
   (assert cross-domain isolation: connection for domain A cannot read
   domain B); binding-config-only backend move (point a fixture domain at a
   second schema and prove zero code diff); unauthorized-domain query
   denied.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- The retrieval contract consumed by Agent Runtime (must stay stable —
  ADR-0322's provider abstraction sits behind the same contract).
- Ingestion source adapters (WP-22).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/rag-service/tests/ -q`
- `helm lint gitops/charts/postgresql gitops/charts/rag-service`
- `helm template gitops/charts/postgresql` renders the three new database/role blocks
- `python3 platform/docs/check_knowledge_refs.py` (exit 0)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `! grep -rn "rag-sales\|rag-adv\|rag-sxa-legacy" agents/ policies/` (physical names stay out of contracts)

## Operator / human follow-up (not executable by the model)

1. Operator: sync the postgresql chart (new DBs/roles reconcile on the PGO
   cluster), run schema-apply for each domain, `make d1 check rag`.
2. Operator: confirm two live domains serve queries with distinct
   credentials (discharges acceptance bullet 1 on cluster).

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0204 →
  `Partially implemented (multi-domain retrieval core, bindings and per-domain databases merged; source adapters (WP-22) and live provisioning pending)`;
  index row to match; tracker → `Operator pending`.
- ADR-0204 flips to `Implemented - see \`platform/bindings/knowledge/\`,
  \`components/rag-service/app/\`.` only after WP-22's merge + operator
  provisioning; then index row, tracker `Done`, MEMORY.md dated bullet.

## Out of scope / deferred

- Source adapters + cadences (WP-22 / ADR-0204 part 2 + ADR-0105).
- `rag-project` binding (WP-28 / ADR-0209).
- Freshness metadata enforcement (WP-24).
