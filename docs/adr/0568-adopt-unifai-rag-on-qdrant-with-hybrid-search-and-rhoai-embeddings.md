# ADR-0568: Adopt UnifAI RAG on Qdrant with hybrid search and RHOAI embeddings

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0202](0202-introduce-logical-knowledge-domains.md), [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md), [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md), [ADR-0112](0112-implement-production-grade-backup-and-recovery.md), [ADR-0518](0518-modernize-local-models-qwen36-chat-qwen3-embeddings-qwen35-training.md), [ADR-0546](0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md), [ADR-0524](0524-integrate-openshift-lightspeed-with-the-zuno-ai-platform.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0569](0569-close-unifai-parity-gaps-generically.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

Zuno's RAG is two components. `components/rag-service` serves hybrid search
(pgvector cosine plus PostgreSQL full-text) with deterministic
`product`/`version` filters, a language boost, a `stale_after` penalty and a
fail-closed `acl_groups` filter keyed on the caller's groups (ADR-0046,
`app/search.py`). `components/rag-ingestion` is a KFP pipeline (fetch,
detect-changes, normalize, chunk, embed, index, validate, S3 between stages)
whose fetch adapters are `fetch-oss-docs` (a crawler over documentation
sites: 18 scheduled technology families under `techSources` in
`gitops/charts/rag-ingestion/values.yaml`), `fetch-confluence` (space SXSI,
persona-scoped page trees, ADR-0330), `load-sxa-dump` (the SXA mysqldump from
S3, ADR-0219) and a disabled `fetch-salesforce`. Each logical domain has its
own database and credentials on the shared PGO cluster (ADR-0204). Embeddings
come from `qwen3-embedding-0.6b`, 1024 dimensions, served by KServe as
`embeddings-predictor.zuno-ai-run.svc:8080` (`gitops/charts/rag-service/values.yaml`,
ADR-0518). The mcp-gateway also proxies `knowledge.tech` to Lightspeed as the
`knowledge.tech.search` capability through the in-process `rag_query`
handler (`platform/bindings/tools/tool-bindings.yaml`, ADR-0524).

ADR-0561 adopts UnifAI. Its RAG service (`rag/` in the fork) is a Flask API
plus Celery workers over RabbitMQ, Mongo for documents and pipelines, and
Qdrant for vectors. Its starting point is narrower than zuno's:

- **Dense only.** `rag/infrastructure/qdrant/qdrant_vector_repository.py`
  creates one unnamed cosine vector per collection, with payload indexes on
  `source_type`, `channel_name`, `source_id` and `owner_id`. No sparse
  vector, no full-text ranking.
- **No ACL.** Retrieval (`GET /query.match` in `rag/infrastructure/http/docs.py`)
  filters by `docIds` and `tags` only. Nothing restricts a chunk by the
  caller's groups.
- **Two sources.** `rag/infrastructure/sources/` holds `document` (upload)
  and `slack`. No Confluence, git, documentation crawl or SQL dump.
- **Remote models.** The upstream image has neither docling nor
  sentence-transformers. The operator deploys docling-serve (CPU) and Text
  Embeddings Inference with `all-MiniLM-L6-v2`, 384 dimensions, by default,
  and `UnifaiStack.spec.rag.embedding` already accepts `mode: remote` with
  `url`, `model` and `dimension` (`unifaistack_types.go`).
- **Ingestion is per document.** `UnifaiRAGPipeline` uploads documents and
  dispatches the pipeline, retried by annotation
  (`fork/unifai-operator/README.md`).
- **No backup.** `UnifaiStack` has no backup field; `deletionPolicy: Retain`
  only keeps the volumes.

The corpus to move is not small. ADR-0525 measured `knowledge.tech` at about
69,000 chunk rows (2026-08-30) and `knowledge.sxa-legacy` at 310,537 source
documents, of which about 113,000 chunk rows took 66 minutes to index. The
embedding predictor sits in `zuno-ai-run`, whose `zuno-ai-run-gpu-cap`
ResourceQuota was fully consumed on 2026-09-04 (`mig-1g.24gb` 3/3,
`mig-2g.48gb` 2/2).

## Decision

**RAG moves to UnifAI's RAG service on Qdrant.** At cutover, rag-service,
rag-ingestion and the pgvector RAG schema (`data/rag/schema/`) are retired
(WP-156). rag-service also serves project memory
(`/v1/project-memory/write`, migrations `005_project_memory.sql` and
`008_project_membership_projection.sql`); that endpoint and those
migrations are retired only once ADR-0569 has moved project memory. The logical contract does not move: knowledge domains (ADR-0202),
their authorization intersection (ADR-0203) and the indexed-read versus
live-tool rule (ADR-0205) bind the new implementation unchanged.

**One Qdrant collection per logical domain.** `knowledge.tech`,
`knowledge.sxa-legacy` and any later domain each get their own collection;
the domain identifier is the binding, the collection name is binding data,
never OKF content. Qdrant's per-collection access control (JWT with
collection-scoped claims) is used to give each consumer only the
collections it is entitled to if WP-149 confirms it works on the deployed
Qdrant (`docker.io/qdrant/qdrant:v1.16.0`, operator default); otherwise the
loss of per-domain credentials is recorded as an accepted regression from
ADR-0204.

**Hybrid search with named dense and sparse vectors.** Collections are
created with a named dense vector and a named sparse vector, and queries
fuse both with Qdrant's query API (reciprocal-rank fusion), behind a
configuration switch that keeps today's dense-only behaviour as the default.
Sparse encoding must handle French and English, which ADR-0046's per-row
`content_tsv` configuration handles today; ADR-0046's bilingual fixtures
(`data/rag/fixtures/seed.sql`) are the acceptance test. This is generic and
written for upstream (ADR-0575).

**The metadata contract becomes Qdrant payload, ACL included.** Every chunk
carries ADR-0202's common fields (`domain`, `source`, `source_type`,
`language`, `classification`, `acl_groups`, `provenance`,
`source_modified_at`, `indexed_at`, `stale_after`) and the domain fields
(`technology`, `product`, `version`, ...), with payload indexes on the
filtered ones. Retrieval accepts the caller's groups and applies
`acl_groups` **fail-closed**: an empty group list excludes every restricted
chunk. The groups come from the identity UnifAI holds for the session
(ADR-0562, ADR-0563), never from a request field a client can set. A
generic, upstreamable form of this filter is part of WP-149. **No retrieval
path without it is eligible for cutover**, because persona-scoped Confluence
content (ADR-0330) would otherwise be readable by every user.

**Embeddings stay on RHOAI.** Every zuno `UnifaiStack` sets
`rag.embedding.mode: remote`, `model: qwen3-embedding-0.6b`,
`dimension: 1024` and the URL of the existing predictor. The operator's
in-namespace TEI and MiniLM are not used. Conversion uses
`rag.docling.mode: remote` against a shared docling-serve; whether RHOAI
3.5 ships a supported docling-serve is unverified, and until it is shown to,
the remote target is a single docling-serve deployed by zuno.

**Sources are a new kind, `UnifaiRAGSource`, beside `UnifaiRAGPipeline`.**
It declares a domain, a source type, its configuration, a credentials Secret
selector and a cron schedule, and it runs incremental fetches with change
detection. Its source types must cover everything rag-ingestion fetches
today before rag-ingestion is retired: `confluence` and `git` as approved,
plus `web` (the documentation crawler, with conditional GET as in ADR-0519)
and `sql-dump` (the S3 dump of ADR-0219). The connectors are generic and
upstreamable; the zuno source list and schedules are cluster data. The
existing per-source cadences in `values.yaml` carry over as `UnifaiRAGSource`
schedules.

**Backup is a stack feature in the Day-3 tier.** `UnifaiStack` gains
`spec.backup` (WP-149): a scheduled Qdrant snapshot of every collection and a
Mongo dump, both written to the per-cluster backups bucket under a `unifai/`
prefix (`zuno-<cluster>-backups`, ADR-0546), plus a restore path. `make d3
backup|restore|check unifai` drives it like `postgresql` today
(`DAY3_BACKUP_COMPONENTS` in the `Makefile`). A restore drill on `demo333`
is executed and recorded before this ADR is claimed implemented, as ADR-0112
requires.

**Lightspeed keeps `knowledge.tech.search`.** The capability is rebound from
the `rag_query` handler to UnifAI retrieval by a binding change only
(ADR-0116), whichever path ADR-0571 takes.

## Planned supersession

At cutover (WP-156), per `docs/adr/README.md` "How a decision changes":

| ADR | Kind | Reason |
|---|---|---|
| ADR-0046 | full | Metadata fields, filters, bilingual ranking and hybrid search all migrate into this record's payload and hybrid clauses; nothing stays behind on pgvector. |
| ADR-0105 | full (its residual after ADR-0218) | Per-source cadences migrate into `UnifaiRAGSource` schedules; KFP recurring runs are retired. |
| ADR-0204 | full (its residual after ADR-0218) | The shared rag-service/rag-ingestion platform and per-domain databases are replaced; the isolation clause migrates into the per-domain collection clause. |
| ADR-0519 | full | Fetch-stage optimizations of `rag_ingestion.py`, which is retired. |
| ADR-0520 | full | detect-changes optimization of the retired pipeline. |
| ADR-0525 | full | pgvector batch writes and ivfflat sizing; no pgvector index remains. |
| ADR-0330 | in part | Clauses 1-4 (KFP component, build, `rag-tech` database, serving-side ACL in rag-service) are retired; clause 5 (the `confluence-*` persona groups in realm `zuno`) and clause 6 (the KServe embedding InferenceService, model since changed by ADR-0518) stay in force. |
| ADR-0322 | in part | The Zuno RAG provider interface and the OGX-backed provider in rag-service go; the OGX Operator activation in the `DataScienceCluster` stays. |
| ADR-0015 | in part | pgvector hybrid search leaves PostgreSQL; PostgreSQL as shared persistent state stays. |

Not superseded: ADR-0202, ADR-0203, ADR-0205 and ADR-0219 (logical
contracts and policy that this record implements); ADR-0050 (already
superseded by ADR-0322); ADR-0209, whose project-memory persistence is
ADR-0569's to settle, not this record's.

## Consequences

The platform stops maintaining about 5,000 lines of RAG service and
ingestion code (plus about 4,300 lines of tests) on its own
and gains a RAG service shared with upstream, at the price of contributing
four connectors, hybrid search, ACL filtering and backup to it.

**Every chunk is re-embedded.** Neither the vectors' store nor their payload
layout carries over, so the cutover re-ingests the whole corpus: about
69,000 `knowledge.tech` chunks and at least the 113,000 measured
`knowledge.sxa-legacy` chunks, likely about three times that for the full
dump (ADR-0525's projection). The source documents themselves are
re-fetched from Confluence, the documentation sites and the S3 dump, not
copied from pgvector. Embedding throughput of the predictor for this volume
has not been measured; WP-149 measures it on `knowledge.tech` before
estimating the rest.

**GPU quota risk.** The re-embed runs through the single `embeddings`
predictor that serves live retrieval. A second replica, or any larger slice,
is refused at admission while `zuno-ai-run-gpu-cap` is full; checking the
quota fresh before the run is mandatory, because it changes with every model
added or removed. The bulk re-ingestion is therefore scheduled outside demo
windows and throttled, and live query latency is watched during it. Moving
the embedding call through MaaS (ADR-0521) does not add capacity.

Until cutover, both stacks run side by side on `demo333` and the corpus
exists twice, in pgvector and in Qdrant.

## Security considerations

The ACL filter is the security boundary of the whole migration; its absence
fails the cutover gate above, not merely a test. Classification metadata on
retrieved chunks must still raise the turn's effective classification
([ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)),
so it is returned with every result.

Qdrant ships without authentication and the upstream charts create a public
Route for it (fork `MEMORY.md`). On zuno clusters Qdrant has no Route, an API
key or JWT is configured, and only the RAG service and the backup job reach
it through the `unifai-stack` NetworkPolicy.

Mongo dumps contain credentials encrypted with the stack's
`CREDENTIAL_ENCRYPTION_KEY`. That key is backed up in Vault, never in the
same bucket as the dump, so a leaked bucket yields no usable credentials and
a restored dump remains decryptable.

Source credentials (Confluence, git) are referenced by `UnifaiRAGSource`
through Secret selectors fed from Vault by `ExternalSecret`s, following the
`zuno/<provider>/...` convention.

## Operational considerations

Cross-namespace calls to the embedding predictor and to docling-serve need
explicit NetworkPolicy and, for mesh-enrolled namespaces, mesh allowlist
entries on both sides; verify with a real embedding request, not a TCP probe.

A restore drill is meaningful only if it would fail on an empty bucket:
restore into a scratch stack and compare collection point counts and a known
query's top results with the source stack.

Live work happens on `demo333`, which is powered off at the time of writing;
the user is asked to power it on first, and every `oc` command passes
`--context`. `demo222` is untouched until its own cutover (ADR-0573).
