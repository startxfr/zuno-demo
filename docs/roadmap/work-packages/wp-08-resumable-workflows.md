# WP-08: Resumable long-running workflows (promotes ADR-0103)

- **State:** Not started
- **ADRs:** ADR-0103 (Proposed -> To be implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** —
- **Estimated files touched:** ~7

> Execute this brief as a standalone task from the repository root. Read the
> referenced files before editing. If the repository state contradicts a
> step, stop and report instead of improvising.

## Goal

Promote stub ADR-0103 to a full record, then persist Agent Runtime workflow
checkpoints in PostgreSQL so long-running jobs survive browser disconnects
and service restarts, proven by tests that kill and resume a run.

## ADR references

Stub (verbatim, from `docs/adr/0100-v0.1-roadmap.md`): "Persist workflow
checkpoints so document-generation jobs survive browser disconnects and
service restarts."

Related: ADR-0039 (runtime executes OKF contract), ADR-0015 (PostgreSQL
platform), ADR-0045 (SSE streaming — reconnect semantics), ADR-0209 (session
history is a *different* concern, owned by WP-28 — do not merge them).
Acceptance criteria: Standard clauses (docs/adr/README.md#standard-clauses).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/agent-runtime/app/` (locate the LangGraph graph build —
  `app/graph/build.py` — and any existing state handling / `AgentState`),
  `components/agent-runtime/requirements.txt`,
  `gitops/charts/agent-runtime/values.yaml`,
  `data/rag/schema/` + `gitops/charts/sql-schema/` (how schema DDL ships),
  `.github/workflows/lint.yml` (service-container precedent for a Postgres
  in CI, if present).

## Step 0 — ADR promotion

1. Create `docs/adr/0103-persist-resumable-long-running-agent-workflows.md`
   with the standard header block (`- **Status:** To be implemented`,
   Target `v0.1`, today's date, `Zuno Demo architecture team`) and this
   Decision:

   > Promote this decision from a one-line v0.1-roadmap entry
   > (`0100-v0.1-roadmap.md`) to a full record.
   >
   > Persist Agent Runtime workflow state with the LangGraph PostgreSQL
   > checkpointer, using a dedicated schema/role on the shared
   > `zuno-postgresql` cluster (mirroring ADR-0315's dedicated-database
   > pattern). Every long-running workflow run is identified by a stable
   > run ID returned to the caller; a disconnected or restarted client can
   > resume by run ID, and a restarted runtime pod resumes in-flight runs
   > from the last checkpoint. Checkpoints carry the initiating subject and
   > effective classification so resumption re-enforces authorization
   > (fail closed when the resuming subject differs). Raw conversation
   > persistence beyond checkpoints remains out of scope (ADR-0209).
   >
   > See [Standard clauses](README.md#standard-clauses) for Alternatives
   > considered, Consequences, Security/Operational considerations,
   > Acceptance criteria and Review evidence.

   Related ADRs list: 0015, 0039, 0045, 0209, 0315.
2. In `docs/adr/0100-v0.1-roadmap.md`: KEEP the `### ADR-0103: …` heading;
   replace the body with
   `Promoted to a full decision record: see [ADR-0103](0103-persist-resumable-long-running-agent-workflows.md) (WP-08 implementation).`
3. In `docs/adr/README.md`: flip the ADR-0103 row link from the roadmap
   anchor to the new file; status `Proposed` → `To be implemented`.
4. `python3 platform/docs/check_docs.py` must exit 0 before continuing.

## Repo changes (step by step)

1. Add the LangGraph PostgreSQL checkpointer dependency to
   `components/agent-runtime/requirements.txt` (use the checkpoint package
   matching the pinned LangGraph version already in the file).
2. Wire the checkpointer into the graph compilation in
   `components/agent-runtime/app/graph/build.py` (or wherever compile
   happens), keyed by run ID; configuration (DSN from env/External Secrets)
   follows how the runtime reaches other services today. In-memory behavior
   must remain the default when no DSN is configured (tests, local dev).
3. Schema/role provisioning: add the checkpoint database/role following the
   `ragTechDatabase` precedent in `gitops/charts/postgresql` (see ADR-0330
   sub-decision 3) and the schema-apply Job pattern
   (`gitops/charts/rag-service/templates/job-schema-apply.yaml`) if DDL is
   needed beyond what the checkpointer auto-creates.
4. Expose run ID in the runtime API responses and accept it on resume;
   follow the existing route/response conventions in
   `components/agent-runtime/app/main.py`.
5. Tests (`components/agent-runtime/tests/`): checkpoint written per step;
   resume-by-run-ID returns the same state after simulated restart
   (new process/graph instance, same DB); security-negative: resume with a
   different subject is refused. Use a real Postgres service container if
   the CI precedent exists, else `pytest-postgresql`-style fixture.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Session/conversation-history persistence and memory extraction (WP-28).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile` on touched runtime files
- `python3 -m pytest components/agent-runtime/tests/ -q`
- `helm lint gitops/charts/agent-runtime gitops/charts/postgresql`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

Optional confirmation only (kill a runtime pod mid-run on cluster and resume)
— the decision is repo-provable, so ADR-0103 can go straight to Implemented
on merge; record the cluster drill as an operational note when performed.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0103 body status →
  `Implemented - see \`components/agent-runtime/app/graph/\`.`; index row
  `Implemented`; tracker → `Done`; this file's State; MEMORY.md dated bullet.

## Out of scope / deferred

- Project-scoped durable memory (`knowledge.project`) — WP-28 / ADR-0209.
- Frontend reconnect UX beyond the existing SSE behavior.
