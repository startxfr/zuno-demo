"""Environment-driven configuration. No secret is ever hardcoded (ADR-0024)
-- database credentials arrive as individual env vars mapped from the
Kubernetes Secret populated by the ExternalSecret this service's chart
registers against `secret/zuno/postgresql/app` (the same `zunoapp`
credential the vault role already generates -- see
ansible/roles/vault/tasks/configure.yml).
"""

from __future__ import annotations

import os

# zuno-postgresql-primary is PGO's own auto-created Service for the
# zuno-postgresql PostgresCluster - there is no plain "postgresql"
# Service, and no "-rw"-suffixed one either (that was CloudNativePG's
# convention - see ansible/roles/postgresql/README.md).
PGHOST = os.getenv("PGHOST", "zuno-postgresql-primary.zuno-data.svc")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "zuno")
PGUSER = os.getenv("PGUSER", "zunoapp")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PG_POOL_MIN_SIZE = int(os.getenv("PG_POOL_MIN_SIZE", "1"))
PG_POOL_MAX_SIZE = int(os.getenv("PG_POOL_MAX_SIZE", "10"))

# Table assumed to be owned/migrated by another track (sql_schema /
# postgresql roles). Columns assumed per the Track D task brief:
# id, source, title, content, embedding vector, metadata jsonb.
DOCUMENT_EMBEDDINGS_TABLE = os.getenv("DOCUMENT_EMBEDDINGS_TABLE", "document_embeddings")

# OpenAI-compatible embeddings endpoint (e.g. a KServe/vLLM embedding
# InferenceService, or any other OpenAI-compatible embedding runtime). If
# unreachable, hybrid search degrades gracefully to full-text-search-only
# (see app/search.py).
EMBEDDING_SERVICE_URL = os.getenv(
    "EMBEDDING_SERVICE_URL",
    "http://embeddings-predictor.zuno-ai-run.svc:8080/v1/embeddings",
)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "bge-small-en-v1.5")
EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "10"))

DEFAULT_TOP_K = int(os.getenv("RAG_DEFAULT_TOP_K", "5"))
MAX_TOP_K = int(os.getenv("RAG_MAX_TOP_K", "20"))
