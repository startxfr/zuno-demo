# Data Documentation

The data layout of the platform (PostgreSQL, MariaDB, Redis, Qdrant, S3 buckets and backups) is in
[data architecture](../architecture/data-architecture.md). The pages here describe the data models and their rules.

- [Sales data model](sales-data-model.md): the legacy SXA schema the commercial record follows.
- [Vector data model](vector-data-model.md): knowledge collections in Qdrant, hybrid search, access filter.
- [RAG data flow](rag-data-flow.md): from a source to a cited answer, in the UnifAI stack.
- [Data retention](data-retention.md): how long prompts, responses and authorization data are kept.
