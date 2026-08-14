# ADR-0103: Persist resumable long-running agent workflows

- **Status:** Implemented - see `components/agent-runtime/app/graph/`, `components/agent-runtime/app/main.py` (lifespan-managed checkpointer, `_resolve_run_id`), `gitops/charts/postgresql/` (`checkpointDatabase`).
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Persist Agent Runtime workflow state with the LangGraph PostgreSQL
checkpointer, using a dedicated schema/role on the shared
`zuno-postgresql` cluster (mirroring ADR-0315's dedicated-database
pattern). Every long-running workflow run is identified by a stable
run ID returned to the caller; a disconnected or restarted client can
resume by run ID, and a restarted runtime pod resumes in-flight runs
from the last checkpoint. Checkpoints carry the initiating subject and
effective classification so resumption re-enforces authorization
(fail closed when the resuming subject differs). Raw conversation
persistence beyond checkpoints remains out of scope (ADR-0209).

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0045](0045-stream-responses-end-to-end-with-sse.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md)
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md)
