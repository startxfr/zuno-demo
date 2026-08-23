# ADR-0204: Generalize the RAG platform to multiple isolated knowledge domains

- **Status:** Partially implemented (multi-domain retrieval core, bindings, per-domain databases and source adapters merged; WP-21's live provisioning confirmed 2026-08-17 - tech+sales domains live with distinct credentials, `make d1 check rag` reports installed after fixing a stale precheck.yml Job lookup; the Salesforce/Aramis source-adapter mapping bullets below are superseded by [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) — see the 2026-08-23 note)
  <!-- 2026-08-15: WP-22 merged part 2 - the source-adapter interface
  (fetch-redhat/fetch-confluence refactored, fetch-salesforce/fetch-aramis/
  load-sxa-dump added), per-domain pipeline targeting and ADR-0105 cadences.
  Only the operator provisioning/live-run follow-up (WP-21+WP-22 briefs)
  separates this from Implemented. -->
- **Target:** v0.2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0330 implemented the first production-shaped ingestion path for the technical corpus and created a dedicated `rag-tech` database on the shared PGO cluster. The new logical model requires four knowledge domains, but logical separation must not force four copies of every ingestion, embedding and retrieval component.

At the same time, sharing one undifferentiated vector store/credential across technical, sales, ADV and legacy data would weaken isolation and make later backend migration difficult.

## Decision

Generalize the existing `rag-service`/`rag-ingestion` implementation into a **shared RAG platform capability** that can serve several logical knowledge domains through configuration and bindings.

The default physical topology is:

- shared reusable ingestion framework/code;
- shared reusable retrieval service implementation;
- shared embedding-serving capability where classification/model policy permits;
- shared PostgreSQL operator/cluster by default;
- **dedicated database (or equivalently strong isolated storage binding), credentials, schema lifecycle and policy per logical knowledge domain**.

Initial bindings:

```text
knowledge.tech       -> rag-tech
knowledge.sales      -> rag-sales
knowledge.adv        -> rag-adv
knowledge.sxa-legacy -> rag-sxa-legacy
```

The logical identifiers above are stable; the right-hand side is environment/platform binding data. `knowledge.sxa-legacy` may later move to a dedicated PostgreSQL cluster or different vector backend without changing agent OKF.

Create a knowledge-backend binding layer (for example under `platform/bindings/knowledge/`) mapping each domain to retrieval provider, database/collection identity, embedding provider and ingestion configuration. Secrets/endpoints are referenced from platform secret/config mechanisms, never copied into domain or agent definitions.

The same generic ingestion framework supports different source adapters:

- web + Confluence -> `knowledge.tech`;
- Salesforce -> `knowledge.sales`;
- Aramis -> `knowledge.adv`;
- validated SQL dump -> `knowledge.sxa-legacy`.

## Superseded (2026-08-23)

[ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md)
supersedes the `Salesforce -> knowledge.sales` and `Aramis -> knowledge.adv`
bullets in the source-adapter list above: Aramis is dropped as an objective
entirely (the service will not be provisioned), and Salesforce's batch
ingestion cadence is deferred to an unscheduled backlog. The `knowledge.sales`
domain/database binding itself (WP-21, live since 2026-08-17) is unaffected —
only the automated ingestion adapter for it is deferred. The `web + Confluence
-> knowledge.tech` and `validated SQL dump -> knowledge.sxa-legacy` adapters
are unaffected. See ADR-0218 for the full decision.

## Consequences

Zuno can add knowledge domains without duplicating the entire RAG stack, while preserving storage-level blast-radius reduction and future provider portability.

Deployment/configuration becomes domain-aware and needs independent health/freshness metrics per binding.

## Security considerations

Credentials are domain-specific. Cross-domain queries require explicit multi-domain authorization from ADR-0203 and are performed by the routing layer, not by granting one database user access to every corpus. C3 domains such as unreviewed SXA legacy must be isolatable on stronger physical boundaries without contract changes.

## Operational considerations

Backup/restore, schema migration, ingestion lag, vector counts and failure recovery are observable independently per domain. A failed `rag-sales` ingestion must not block `rag-tech` retrieval.

## Acceptance criteria

- At least two domains can run on the same reusable RAG code without sharing database credentials.
- Moving one domain to a different backend requires changing only knowledge binding/deployment configuration.
- Agent OKF and knowledge policy contain no physical database/service endpoints.
- Cross-domain retrieval occurs only when the active task is authorized for every requested domain.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md)
- [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
- [ADR-0202](0202-introduce-logical-knowledge-domains.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0218](0218-drop-aramis-adapter-and-defer-salesforce-ingestion-cadence.md) — supersedes this ADR's Salesforce/Aramis adapter-mapping bullets
