# ADR-0101: Provide HA for shared agent platform services

- **Status:** Partially implemented (HA chart mechanics, SLO definition and alert rules merged; failover drill and live measurement pending, roadmap WP-12). Incident 2026-08-14: the explicit `topologySpreadConstraints` added to `gitops/charts/postgresql`'s PostgresCluster (`spec.instances` and `spec.proxy.pgBouncer`) duplicated a default PGO 5.8 already injects (hostname + zone, both `ScheduleAnyway`) - Kubernetes SSA keys this field on `(topologyKey, whenUnsatisfiable)`, so the duplicate zone entry made every generated StatefulSet patch invalid and broke PGO reconciliation entirely, including `spec.users`, which meant the `agent-checkpoints`/`ogx` databases were never created and `agent-runtime` crash-looped. Reverted; PGO's own defaults already provide the intended zone spread, confirmed live via `oc get sts -n zuno-data -o jsonpath='{.items[*].spec.template.spec.topologySpreadConstraints}'`.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Every shared platform service (Agent Runtime, AI Gateway, MCP Gateway,
rag-service, Keycloak, PostgreSQL, Redis, and the observability stack)
runs with production-oriented availability configuration: >=2 replicas
where the workload supports it (PostgreSQL via its operator's HA
mechanism), a PodDisruptionBudget, topology spread across nodes, and
liveness/readiness probes. Availability configuration is chart values,
per environment; the demo profile may scale down, but the chart defaults
document the HA-capable shape and CI checks enforce that the mechanisms
exist in every in-scope chart.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md)
- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0029](0029-instrument-model-usage-costs-and-distributed-traces.md)
- [ADR-0102](0102-target-99-9-percent-platform-availability.md)
- [ADR-0112](0112-implement-production-grade-backup-and-recovery.md) (recovery is this ADR's counterpart)
