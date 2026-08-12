# rag_ingestion_build

Day 1 `build` component (ADR-0056, `make day1|d1 build rag-ingestion`).
Builds `rag-ingestion` via native OpenShift `BuildConfig`/`ImageStream`
in `zuno-ai-build` - see `ansible/tasks/apply_openshift_build.yml` for
the shared mechanism.

No `precheck.yml`/`install.yml` - this is a build-only role, distinct
from the `rag_ingestion` Day 1 `run` component
(`ansible/roles/rag_ingestion`), which deploys the already-built image.
