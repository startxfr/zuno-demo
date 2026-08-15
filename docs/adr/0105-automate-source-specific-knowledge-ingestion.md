# ADR-0105: Automate source-specific knowledge ingestion

- **Status:** Partially implemented (per-source adapters and cadence configuration merged; live scheduled runs pending)
- **Target:** v0.1
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Run scheduled ingestion according to each source's freshness objective
rather than one global monthly cadence. Technical web/Confluence
knowledge must be refreshable at least weekly, operational Salesforce
knowledge is expected to refresh on an hours-scale cadence, and
immutable legacy sources may be loaded on demand. Retain manual refresh
support.

Cadences are configured per domain in `knowledge/<domain>/domain.yaml`
(the freshness objective) and realized as per-source KFP recurring-run
schedules in `gitops/charts/rag-ingestion/values.yaml` (the top-level
`schedule` block for `knowledge.tech`, each `domains.<name>.schedule`
block for the others), rendered as one schedule ConfigMap per scheduled
domain that `ansible/roles/rag_ingestion/tasks/install.yml` turns into
KFP recurring runs. Manual refresh remains
`make d1 install rag-ingestion`, triggering an immediate run.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0204](0204-generalize-the-rag-platform-to-multiple-isolated-knowledge-domains.md)
  — the multi-domain RAG platform these per-source adapters feed.
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
  — the freshness policy that consumes each source's cadence objective.
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
  — the Day 1 ingestion pipeline these cadences schedule.
