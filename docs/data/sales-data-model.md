# Sales Data Model

The authoritative source reference is the supplied legacy SXA schema. It documents the business flow `affaire -> devis -> commande -> facture` and its line-item tables as they stood in the pre-2021 record.

This is a *reference for reading the corpus*, not a migration target. ADR-0219 retired the PostgreSQL/MariaDB structured stores this file once described: SXA rows are parsed from the S3 dump straight into the `knowledge.sxa-legacy` pgvector index, one document per row, and served through retrieval only. See `MEMORY.md` for source-derived schema details.
