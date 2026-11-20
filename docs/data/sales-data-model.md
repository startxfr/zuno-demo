# Sales Data Model

Last reviewed: 2026-11-20

The authoritative source reference is the supplied legacy SXA schema. It documents the business flow `affaire -> devis -> commande -> facture` and its line-item tables as they stood in the pre-2021 record.

This is a *reference for reading the corpus*, not a migration target. ADR-0219 retired the PostgreSQL/MariaDB structured stores this file once described: the raw SXA dump stays in the shared source bucket and is served through retrieval only. No `knowledge.sxa-legacy` policy entry exists in the agents release since 0.9.0 (WP-185), and RAG now runs on Qdrant (ADR-0568), not pgvector. See `MEMORY.md` for source-derived schema details.
