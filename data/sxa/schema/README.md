# SXA PostgreSQL Schema

PostgreSQL target schema assets. The legacy MySQL schema is summarized in
`MEMORY.md` and treated as a migration source, not imported directly - see
`data/sxa/migrations/README.md` for the full rationale and the legacy-to-native
table mapping.

- `001_init.sql` - sales-operations domain: customers, contacts,
  opportunities, quotes, orders, invoices, products and their line items,
  status lookup tables, and the activity/call journal.
- `002_pgvector.sql` - `document_embeddings`, the shared pgvector retrieval
  table consumed by the RAG service (ADR-0015).

Applied in order (`001_init.sql` then `002_pgvector.sql`) by
`ansible/roles/sql_schema`, followed by `data/sxa/fixtures/seed.sql`.
