# ADR-0017: Access sales data through controlled MCP tools

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Prevent direct LLM-to-database freedom by exposing deterministic sales operations through policy-controlled MCP tools.

## Evolution (2026-08-13)

ADR-0205 and ADR-0206 split commercial access into two complementary paths: indexed `knowledge.sales` is the preferred read path for semantic/historical questions over asynchronously ingested Salesforce content, while live Salesforce reads and every Salesforce write use controlled MCP capabilities. Legacy SXA remains separately accessible through `knowledge.sxa-legacy` and deterministic structured-query tools; arbitrary LLM-generated SQL remains outside the trusted contract.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
