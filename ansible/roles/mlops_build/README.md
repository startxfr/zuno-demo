# mlops_build

Day 1 `build` component (ADR-0056, `make day1|d1 build mlops`). Builds
`mlops` via native OpenShift `BuildConfig`/`ImageStream` in
`zuno-ai-build` - see `ansible/tasks/apply_openshift_build.yml` for the
shared mechanism.

No `precheck.yml`/`install.yml` - this is a build-only role, distinct
from the `mlops` Day 1 `run` component (`ansible/roles/mlops`), which
deploys the already-built image.

Unlike `rag_ingestion_build` (the role this mirrors), the `mlops` image
is also published through `.github/workflows/build-publish.yml`'s build
matrix (WP-34's own explicit instruction) - the OpenShift `BuildConfig`
this role drives and the GitHub Actions workflow both build from the same
`components/mlops/Containerfile`, independently.
