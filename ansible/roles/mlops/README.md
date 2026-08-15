# mlops

A Day 1 component (ADR-0056) with a documented no-op `install.yml` d0
half - no operator dependency of its own, same pattern as
`ansible/roles/rag_ingestion` (ADR-0302 point 1 reuses that exact
mechanism: a KFP pipeline running on the existing
`DataSciencePipelinesApplication`/`aipipelines` OpenShift AI component).
Depends on `postgresql` (read-only access to `document_embeddings`),
`openshift_ai` (the `aipipelines` component, for the
DataSciencePipelinesApplication/Pipeline CRDs) and `mlops_build` (the
image this role deploys) having run first.

1. Applies `gitops/apps/mlops` (`gitops/charts/mlops`): a
   `DataSciencePipelinesApplication` plus a KFP `Pipeline` CR, wired to
   S3 artifact storage and read-only Postgres access, in `zuno-ai-build`.
2. Waits for the `mlops-dspa` `DataSciencePipelinesApplication` to report
   Ready.
3. Best-effort confirms the `mlops` pipeline is registered on the DSPA's
   v2beta1 KFP API - UNVERIFIED against a live cluster, failure here
   doesn't block the rest of the install.

Unlike `rag_ingestion`, this role does **not** attempt to activate a
recurring run: MLOps training runs are triggered manually by the operator
per candidate (ADR-0302's own scope is "one pipeline run produces one
candidate adapter for human-reviewed promotion", not a continuously
recurring re-ingestion the way RAG content needs). `make d1 check mlops`
becomes meaningful once this is implemented, rather than the previous
`mlops` precheck's placeholder "contract registered... pending" message
(ADR-0302's own Operational considerations).

## Not covered by this role

- **Building the runtime image** - a separate day1-build component,
  `ansible/roles/mlops_build` (`make d1 build mlops`), distinct from this
  run component, same split as `rag_ingestion`/`rag_ingestion_build`.
- **Running the pipeline** - an operator action
  (`oc create` a KFP run against the DSPA API, or the OpenShift AI
  dashboard), not something this role does on install. This repository's
  sandbox has no GPU to run a real training job in.
- **Promoting a trained adapter to serving** - a human-reviewed GitOps PR
  updating `gitops/charts/models/values.yaml` (ADR-0302 point 7); this
  role, and the pipeline itself, never write to that file.

The four pipeline CLI stages themselves
(`components/mlops/src/mlops.py`) are implemented - see
`gitops/charts/mlops/README.md` for what each one does and what remains
unverified against a live cluster/real GPU/real Model Registry.
