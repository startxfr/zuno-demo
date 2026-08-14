# WP-28: Project-scoped agent memory

- **State:** Not started
- **ADRs:** ADR-0209 (To be implemented -> Partially implemented; Implemented after WP-31's cross-agent test)
- **Depends on:** WP-20, WP-21 (merged)
- **Blocks:** WP-31 (Arkos slice runs the cross-agent acceptance test)
- **Estimated files touched:** ~12 (sequence carefully; keep Go tests green at every commit)

> Execute this brief as a standalone task from the repository root. This WP
> touches the BFF OpenAPI contract — sequence step 3 as an atomic change
> (spec + Go code + contract test together).

## Goal

Introduce `knowledge.project` as the fifth logical domain with a mandatory
`project_id`: propagated BFF → Agent Runtime, a `rag-project` binding and
database, the session-history vs durable-memory split with an explicit
extraction step (local-only models for C2/C3), and a PostgreSQL
project-membership table enforced fail closed at retrieval.

## ADR references

Primary: [docs/adr/0209-introduce-project-scoped-agent-memory.md](../../adr/0209-introduce-project-scoped-agent-memory.md)
(read fully — it is the most detailed v0.2 ADR).

Acceptance criteria: with Tekos, a user states project `demo-001` facts (OpenShift 4.22, AWS, three clusters, C2 local-only) and the session ends; a new `demo-001` session lets Tekos retrieve these facts without the user repeating them; Arkos, in the same or a later session, retrieves the same permitted `demo-001` facts through the identical `knowledge.project` contract with different task prompts/capabilities than Tekos; a user without `demo-001` project membership cannot retrieve any of its memories, structured state, or semantic chunks; raw conversation turns are not persisted into `knowledge.project` unless they pass through the extraction step; unit tests cover the extraction step's fact/decision identification and the membership fail-closed check, plus an end-to-end acceptance test for the full scenario above.

Key body constraints: `project_id` propagates following the ADR-0032/0033
identity pattern; extends ADR-0054's BFF OpenAPI contract with a new
optional field; membership is data in a PostgreSQL table, deliberately NOT
per-project Keycloak groups (the realm is static GitOps); memory extraction
for C2/C3 conversations runs against a local-only model (ADR-0035); memories
inherit source classification, never silently downgraded; retrieved memory
feeds ADR-0034 effective-classification aggregation, monotonic escalation
only.

## Preconditions (verify before starting)

- WP-20/WP-21 merged; `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/agent-bff/openapi.json` + `main.go` + `contract_test.go`
  (the contract change surface), `platform/api/lint_openapi.py` (conventions
  the spec edit must satisfy), `components/agent-runtime/app/` (`AgentState`,
  request context propagation), `knowledge/` + `platform/bindings/knowledge/`
  (WP-20/21 patterns to extend), `gitops/charts/postgresql/values.yaml`
  (database-block pattern).

## Repo changes (step by step)

1. **Domain + binding:** add `knowledge/project/domain.yaml` (contract per
   ADR-0202 + mandatory `project_id` metadata field);
   `knowledge.project -> rag-project` entry in
   `platform/bindings/knowledge/bindings.yaml`; `ragProjectDatabase` block in
   `gitops/charts/postgresql` (owner role `ragproject`); knowledge-policy
   entry (any entitled agent may declare it; membership decides access).
2. **Schema:** project schema DDL in `data/rag/schema/` — structured project
   state (rows/JSONB), semantic memory chunks (pgvector, WP-20 metadata +
   `project_id`), and the membership table (`project_id` → member
   subject/group); schema-apply per the WP-21 pattern.
3. **Contract (atomic commit):** add optional `project_id` to the chat/
   session request in `components/agent-bff/openapi.json`, the Go request
   handling, and `contract_test.go` together; run
   `python3 platform/api/lint_openapi.py` and `go test ./...` in the same
   change.
4. **Propagation:** BFF forwards `project_id` to Agent Runtime following the
   identity-propagation pattern (ADR-0032/0033 — same header/claim style);
   runtime carries it in `AgentState` and passes it on every RAG/memory
   call.
5. **Retrieval enforcement:** rag-service checks membership (fail-closed
   `acl_groups`-style intersection against the membership table) before any
   `knowledge.project` read; no membership row → deny.
6. **Extraction step:** runtime session-end/checkpoint hook producing
   durable facts/decisions only (not raw turns); model selection respects
   ADR-0035 (C2/C3 → local-only); extracted memories inherit the
   conversation's classification. Session history persistence itself stays
   out of `knowledge.project` (it is continuity/audit data — if WP-08's
   checkpointer is present, reuse its store; do not mix the two concerns).
7. **Tests:** unit — extraction identification, membership fail-closed,
   classification inheritance (no downgrade); end-to-end (single-runtime) —
   the Tekos `demo-001` store-and-retrieve scenario with mocked model. The
   Arkos cross-agent bullet is executed by WP-31 and stays open here.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Keycloak realm (`gitops/charts/keycloak/files/realm-zuno.json`) — the ADR
  explicitly forbids per-project groups.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 platform/api/lint_openapi.py` (exit 0)
- `cd components/agent-bff && go build ./... && go test ./...`
- `python3 -m pytest components/agent-runtime/tests/ components/rag-service/tests/ -q`
- `helm lint gitops/charts/postgresql gitops/charts/rag-service`
- `python3 platform/docs/check_knowledge_refs.py` && `python3 platform/docs/check_docs.py` → PASS

## Operator / human follow-up

None specific to this WP (cluster provisioning of `rag-project` rides the
WP-21 operator step). The remaining acceptance bullet (Arkos cross-agent)
belongs to WP-31.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0209 →
  `Partially implemented (domain, propagation, membership enforcement, extraction and Tekos end-to-end merged; cross-agent Arkos scenario pending WP-31)`;
  index row to match; tracker → `Repo work merged`.
- After WP-31's cross-agent test passes: ADR-0209 →
  `Implemented - see \`knowledge/project/\`, \`components/agent-runtime/app/\`.`;
  index row `Implemented`; tracker → `Done`; MEMORY.md dated bullet.
  (WP-31's brief carries this same instruction — whichever lands second
  performs it.)

## Out of scope / deferred

- Cross-project or cross-user memory sharing (ADR-0404, v0.4 — none here).
- Multiple graph shapes consuming the memory (WP-30/WP-31).
