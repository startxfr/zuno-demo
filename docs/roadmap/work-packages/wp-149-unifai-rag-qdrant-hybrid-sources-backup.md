# WP-149: UnifAI RAG on Qdrant with hybrid search, Confluence and git sources, and backup

- **State:** Done (2026-10-24)
- **ADRs:** [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)
- **Depends on:** none
- **Related:** [ADR-0046](../../adr/0046-make-rag-retrieval-metadata-aware-and-bilingual.md), [ADR-0105](../../adr/0105-automate-source-specific-knowledge-ingestion.md), [ADR-0330](../../adr/0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md), [ADR-0519](../../adr/0519-parallelize-and-shortcut-the-rag-ingestion-fetch-stages.md), [WP-151](wp-151-deploy-unifai-on-zuno-via-argocd.md), [WP-156](wp-156-retire-zuno-agent-and-rag-code.md)
- **Target:** v0.11
- **Estimated files touched:** ~30 in `startx-unifai` — Qdrant repository and query path, two new source connectors, embedding dimension plumbing, a new `UnifaiRAGSource` kind and controller, `spec.backup` on `UnifaiStack`, tests; ~4 in `zuno-demo` (a Day-3 backup/restore role for UnifAI stores).

> The largest fork-side WP. It moves retrieval to Qdrant with hybrid search,
> teaches UnifAI the two sources the zuno corpus comes from, and makes the
> new stores recoverable. A green dump is not a restore: the drill is part
> of acceptance.

## Goal

UnifAI ingests Confluence spaces and git repositories incrementally, embeds
them with `qwen3-embedding-0.6b` served by RHOAI (dimension 1024), answers
with dense+sparse hybrid search over Qdrant, and its Qdrant and Mongo data
can be backed up to S3 and restored.

## Progress (2026-10-17)

All in startx-unifai `devel` (generic parts on feature branches from `main`).

- **Hybrid search** (`9485e3bb8`): `QDRANT_HYBRID_ENABLED` creates
  `<name>_hybrid` collections with a named dense vector and an IDF sparse
  vector from a hashing BM25 encoder (no model download, works offline);
  queries fuse both by RRF with the same filters. Stable point ids fix a
  pre-existing defect (re-running a pipeline duplicated every chunk);
  collection and embedding dimension mismatches now fail loudly.
- **Shared sources by OIDC group** (`decac72c2`, user decision): a source can
  be `shared` with ACL groups; only `RAG_SHARED_PUBLISHERS` may publish one;
  the caller's groups come from the session token or a forwarded user token
  verified against `OIDC_ISSUER_URL`; no group means own sources only.
  MAS `docs_rag` gains `forward_user_token` (`fc0770be6`) and `source_type`
  (`954782278`); RAG gains `/api/sources/query.match` (`7aaeac1ae`).
- **Confluence source** (`ba6d851ec`): space or page subtree, incremental by
  page version (manifest in the source's type_data), stale points deleted
  before storing. No git source: the current zuno ingestion has none
  (Confluence, documentation sites and the SXA dump are its sources).
- **Operator** (`0bca13a87`, `06acea665`, fix `f50a0963f`):
  `UnifaiStack.spec.rag.{hybrid,sharedPublishers,confluence}` rendered only
  when set (no rollout of existing stacks), kind `UnifaiRAGSource`
  (`syncInterval` instead of cron: the operator has no cron parser), and
  `spec.backup` (MongoDB dump + one Qdrant snapshot per collection to S3,
  retention). Released in 0.1.17 except the fix (needs 0.1.18).
- **Live on demo333, 2026-10-17** (`unifai-devel`, operator 0.1.17, rag
  image `devel-75c057d02`, the zuno Confluence credentials): a
  `UnifaiRAGSource` on `SXSI / Technologie : Satellite` ingested 90 pages into
  the hybrid collection; every later sync reported "0 new or changed, 90
  unchanged" (nothing re-embedded). Searches as another user: with
  `agent_tekos` the shared pages are returned, without it 0 hits; an exact
  identifier (`foreman-maintain`) and a paraphrase both found the relevant
  pages. **Incident:** 0.1.17 read the wrong response key and re-triggered
  the sync every 10 s; ~2,900 syncs were queued (each listing 90 pages on
  startxfr.atlassian.net) before the CR was deleted and `confluence_queue`
  purged; fixed in `f50a0963f` with a regression spec. Everything was
  deleted and the stack spec restored afterwards.
- **Backups** were exercised against Qdrant v1.16.0 by hand (three runs with
  retention 2, a deleted collection restored with all its points), not yet
  on the cluster.
- **Remaining:** release 0.1.18; step 8 (the zuno Day-3 `unifai` role) once
  WP-151 deploys UnifAI; a cluster backup and restore drill; the
  documentation-site and SXA sources if those corpora move to UnifAI.

## Progress (2026-10-22, demo333)

- Day-3 role `unifai` (`backup`, `check_s3_backup`, `restore`) is live: spec.backup
  on `zuno-unifai` with the PostgreSQL S3 identity, on-demand backup and check, and a
  restore drill into a scratch namespace that compared 501 Qdrant points and 18
  MongoDB collections with the live stores (evidence:
  `docs/roadmap/evidence/wp-154-tekos-pilot-phase-a.md`).
- The Confluence sources `tekos-satellite` (90 pages) and `tekos-openshift` (411 pages)
  are ingested with group ACLs; the second pass re-embeds nothing.

## Steps

Work in `/home/cl/ClaudeCode/startx-unifai`. Python changes (steps 1-4) are
generic: feature branches from `main` (`make feature-start`), merged into
`devel` (`make feature-to-devel`). Operator changes (steps 5-6) live under
`fork/unifai-operator/` and go to `devel`.

1. **Hybrid search (`feat/qdrant-hybrid`).** In
   `rag/infrastructure/qdrant/qdrant_vector_repository.py`, create collections
   with a named dense vector and a named sparse vector using Qdrant's `IDF`
   modifier (BM25-style); compute sparse vectors client-side (e.g. fastembed
   BM25 or a plain tokenizer — choose the lighter dependency and record why).
   Add a `mode` parameter (`dense` default, `hybrid`) to the query path and
   use Qdrant's Query API with prefetch on both vectors and RRF fusion.
   Existing dense-only collections must keep working unchanged. Unit tests
   in `rag/tests/unit/` with a mocked Qdrant client; one integration test
   against a real Qdrant container if the suite already runs one (check
   `rag/tests/conftest.py`).

2. **Embedding dimension (`feat/remote-embedding-dimension`).** Read
   `rag/infrastructure/embedding/embedders/remote_embedding_adapter.py` and
   `embedding_generator.py`. Make the vector size come from configuration
   (the operator already has `UnifaiStack.spec.rag.embedding.{mode,url,model,dimension}`
   in `fork/unifai-operator/api/v1alpha1/unifaistack_types.go`) instead of
   any MiniLM-384 default. Remote mode is the only mode zuno uses (the rag
   image has no sentence-transformers).

3. **Confluence and git sources (`feat/confluence-git-sources`).** Add
   `rag/infrastructure/sources/confluence/` and `rag/infrastructure/sources/git/`,
   each with `config.py`, `connector.py`, `chunker.py`, `validator/` on the
   model of `rag/infrastructure/sources/document/` and `.../slack/`. Port the
   logic, do not rewrite it: read `components/rag-ingestion/src/rag_ingestion.py`
   in zuno-demo (fetch, change detection, normalize, chunk) and carry over its
   incremental cursor/hash logic and deletion handling. Register both sources
   wherever `document` and `slack` are registered (grep for `slack` under
   `rag/infrastructure/` and `rag/bootstrap/`). Tests: fixtures with recorded
   API responses; an unchanged page is not re-embedded; a deleted page is
   removed from Qdrant.

4. **Docling remote.** Confirm the document converter path uses the remote
   `docling-serve` URL from `UnifaiStack.spec.rag.docling` (the stack already
   deploys docling-serve + TEI). No code change expected; note it if one is.

5. **`UnifaiRAGSource` kind (operator).** Add a sibling kind — do NOT change
   `UnifaiRAGPipeline` (it reconciles per document,
   `fork/unifai-operator/api/v1alpha1/workflow_types.go`,
   `internal/controller/ragpipeline_controller.go`). Spec: `type`
   (`confluence`|`git`), type-specific fields (base URL, space keys / repo URL,
   branch, paths), `schedule` (cron), `credentialsSecretRef`. Status: last
   sync time, cursor, counts, conditions. The controller triggers the RAG
   service's ingestion for that source on schedule via the API used by
   `internal/unifai/client.go`. `make generate manifests`, add an example
   under `fork/unifai-operator/examples/rag/`, envtest coverage in
   `internal/controller/` (follow `objects_test.go` and `fakemas_test.go`).

6. **`spec.backup` (operator).** Add `BackupSpec` to
   `fork/unifai-operator/api/v1alpha1/unifaistack_types.go` (`schedule`,
   S3 `endpoint`, `bucket`, `prefix`, `credentialsSecretRef`, `retention`)
   and reconcile two CronJobs from
   `internal/controller/unifaistack_controller.go`: Qdrant snapshot upload,
   and `mongodump --archive --gzip` upload. Add a matching on-demand restore
   procedure (a Job template or documented commands) in
   `fork/unifai-operator/README.md`. Existing StatefulSet claim templates and
   PVCs are reused verbatim; do not touch them. envtest for CronJob
   rendering.

7. **Operator release.** `make test` (envtest) in `fork/unifai-operator`,
   bump `VERSION` in `fork/unifai-operator/Makefile`, then coordinate with
   the startx-unifai session before running the release chain from the
   fork's `MEMORY.md` — OLM on demo333 rolls the new operator to both
   `unifai-devel` and `unifai-olm`, and a new collection layout must not
   break their existing data. Python images: `make images-devel`.

8. **zuno-demo Day-3 tier.** Add a `unifai` role with `tasks/backup.yml`,
   `tasks/restore.yml` and `tasks/check_s3_backup.yml` under
   `ansible/roles/`, on the model of `ansible/roles/postgresql/tasks/`, and
   add it to `day3_backup_components` in `ansible/playbooks/day3_backup.yml`
   and `ansible/playbooks/day3_restore.yml`, and to `DAY3_BACKUP_COMPONENTS`
   in the `Makefile`. The check reads the backup path
   from the live `UnifaiStack` CR, never from an Ansible default (lesson of
   the pgBackRest probe that read a stale path).

## Acceptance

Unit and envtest suites green; hybrid queries return results for both an
exact-identifier query (sparse wins) and a paraphrase (dense wins) on a test
corpus. Live acceptance, in [WP-154](wp-154-tekos-pilot-on-demo333.md):
the tekos Confluence corpus is ingested by a `UnifaiRAGSource`, a second
scheduled run re-embeds nothing, and a restore drill from S3 into a scratch
namespace returns the same hit count as the source. demo333 is powered off;
ask the user to power it on, and pass `--context` explicitly on every `oc`
command.

## Open questions

- Full re-ingestion of the corpus (`zuno-demo-rag-corpus`) costs embedding
  GPU time while the GPU quota is saturated. Throttle, or schedule off-hours?
- Should the sparse encoder run in the RAG service or be served (TEI sparse
  models)? Pick the one with no new GPU need.
- Metadata-aware, bilingual retrieval (ADR-0046): which filters must be
  carried into Qdrant payload indexes? List them from
  `components/rag-service/app/search.py` before step 1.

## Closure (2026-10-24)

Done: hybrid search, group ACL, incremental sync and the restore drill are proven on demo333. Evidence: [the closing evidence](../evidence/unifai-adoption-closure-2026-10-24.md).
