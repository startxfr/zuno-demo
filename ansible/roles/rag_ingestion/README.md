# rag_ingestion

A Day 1 component (ADR-0056) with a documented no-op `install.yml` d0 half
- no operator dependency of its own. Depends on `postgresql` (the
`rag-tech` database), `models` (the `embeddings` InferenceService),
`keycloak` (the `confluence-{archi,build,run}-<tech>` ACL groups) and
`openshift_ai` (the `aipipelines` component, for the
DataSciencePipelinesApplication/Pipeline CRDs) having run first.

1. Applies `gitops/apps/rag-ingestion` (`gitops/charts/rag-ingestion`):
   a `DataSciencePipelinesApplication` plus a KFP `Pipeline` CR wired to
   the shared `zuno-postgresql` cluster's `rag-tech` database, the
   `embeddings` InferenceService, and S3 corpus storage - all in
   `zuno-ai-build`.
2. Waits for the `rag-dspa` `DataSciencePipelinesApplication` to report
   Ready.

## Not covered by this role

- **Building the runtime image** - a separate day1-build component,
  `ansible/roles/rag_ingestion_build` (`make d1 build rag-ingestion`),
  distinct from this run component, same split as `rag`/`rag_build`.
- **Activating the KFP recurring run** (`schedule.cron` in
  `values.yaml`) - this RHOAI/DSP version doesn't expose a
  Kubernetes-native `RecurringRun` CRD, only the KFP v2beta1 HTTP API.
  See `gitops/charts/rag-ingestion/README.md`'s "Scheduling" section.
- **The eight ingestion stage implementations themselves**
  (`components/rag-ingestion/src/rag_ingestion.py`) - intentionally
  guarded until the remaining environment-specific values (real
  Confluence spaces/directories, confirmed Red Hat doc version strings)
  are fixed.
