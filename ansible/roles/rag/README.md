# rag

A **Day 2** component (`make d2 install rag`, `make d2 check rag`) - ADR-0060
moved it out of Day 1 along with namespaces/llm/models/content-ingestion. Older
work packages and this file's own history still call it Day 1; they are stale.

`install.yml` has no operator dependency and applies nothing directly: it
applies two GitOps Applications and lets ArgoCD do the rest.

1. `zuno-rag-d0` - carries no content today (kept so the d0/d1 phase pair
   stays uniform across components).
2. `zuno-rag-d1` (`gitops/charts/rag-service`) - pgvector + hybrid search
   (`components/rag-service`), and the whole schema path below.

Depends on `postgresql` (Day 1) having run first, for the per-domain databases
and roles. It does **not** depend on `sql_schema` any more - ADR-0219 deleted
that component, and `document_embeddings` is created by this chart's own
`002_pgvector.sql`.

## The schema is applied by the chart, not by this role

The `zuno-rag-schema` ConfigMap used to be built here (Kustomize) and applied
out-of-band, entirely outside GitOps - editing a SQL file had no live effect
until someone re-ran this role by hand. It is now rendered by
`gitops/charts/rag-service/templates/configmap-schema.yaml`, so it moves with
the Job that consumes it.

That Job (`templates/job-schema-apply.yaml`) is an ArgoCD **`Sync`** hook at
wave 41 - *not* a `PreSync` hook, whatever ADR-0313 originally said. The Sync
phase only starts once every PreSync hook has succeeded, so a PreSync consumer
of a Sync-phase credential deadlocks; the template's own comment carries the
incident note. With `hook-delete-policy: BeforeHookCreation`, every sync
deletes the previous Jobs and creates fresh ones, which is why the SQL chain
has to stay re-runnable (see `004_rag_chunking.sql`'s guard, and
`components/rag-service/tests/test_schema_idempotence.py`).

One Job is rendered **per enabled `knowledgeDomains` entry**, not one fixed
Job: `zuno-rag-schema-apply-<domain>`. Each applies `002` → `008` against its
own database. `precheck.yml` therefore matches on the
`app.kubernetes.io/name=rag-service` label rather than a fixed name, and
requires *every* returned Job to have succeeded - plus both Applications
Synced+Healthy - before reporting the component installed.

## Where the SQL lives

`data/rag/schema/` is the canonical human-readable copy; the chart's
`files/sql/` is the deployed one (Helm's `.Files.Get` is chart-root-relative
and cannot traverse out of the chart). The two are **synced by hand**, so
`test_schema_idempotence.py` fails on drift between them. `002_pgvector.sql`
is the one exception: it has only ever existed in the chart.

The demo fixture corpus is `data/rag/fixtures/seed.sql`.
