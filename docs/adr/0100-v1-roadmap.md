# v1 roadmap decisions (ADR-0101 – ADR-0112)

- **Status:** Proposed
- **Target:** v1
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

Consolidated from 12 individual ADR files. Each entry below is its own immutable decision record, citable as `ADR-0NNN`; only the Decision line is unique per entry - [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

### ADR-0101: Provide HA for shared agent platform services

Run shared runtime, gateway, identity, data and observability services with production-oriented availability.

### ADR-0102: Target 99.9 percent platform availability

Adopt 99.9 percent as the industrialized service objective.

### ADR-0103: Persist resumable long-running agent workflows

Persist workflow checkpoints so document-generation jobs survive browser disconnects and service restarts.

### ADR-0104: Introduce controlled semantic caching

Reduce latency and cost without leaking cross-user or cross-classification content.

### ADR-0105: Automate monthly knowledge ingestion

Run scheduled ingestion monthly while retaining manual refresh support and source-specific freshness controls.

### ADR-0106: Enforce OKF bundle signing and validation

Verify signatures and schema/policy validity before promoting agent definitions.

### ADR-0107: Introduce automated model quality gates

Block promotion when model or agent regression breaches agreed thresholds.

### ADR-0108: Automate model evaluation with LM-Eval

Use OpenShift AI evaluation capabilities where appropriate to compare candidate local models.

### ADR-0109: Implement source freshness and trust scoring

Use provenance/freshness metadata to rank knowledge and signal stale content.

### ADR-0110: Automate document ACL synchronization

Keep private vector indexes aligned with current source authorization and remove inaccessible content.

### ADR-0111: Strengthen SecNumCloud-oriented security controls

Harden deployment, supply chain, identity, network and data controls toward SecNumCloud-oriented expectations.

### ADR-0112: Implement production-grade backup and recovery

Define backup, restore and recovery objectives for PostgreSQL, configuration and critical state.
