# Data Architecture

Two major data domains are deliberately separated:

1. business/transactional data, including the migrated SXA PostgreSQL schema;
2. knowledge/vector data using PostgreSQL with pgvector and full-text search.

The SXA source schema is MySQL 5.0-era and is treated only as a migration source. The PostgreSQL target must preserve the `affaire -> devis -> commande -> facture` business chain and line-item economics.

Private Google Drive documents are vectorized only when useful for long-lived work context. Internal and public RAG corpora remain logically separated.

Both domains are served by a single PostgreSQL cluster (PGO-managed, 1 primary + 2 async replicas with Patroni failover) fronted by PgBouncer transaction pooling. TimescaleDB and pgvector extensions are preloaded on the same cluster. Backups land on a local PVC by default, with S3 backup wired but disabled by default (`docs/platform/prerequisites.md`).
