# rag_build

Day 1 `build` component (ADR-0056, `make day1|d1 build rag`). Builds
`rag-service` via native OpenShift `BuildConfig`/`ImageStream` in
`zuno-ai-build` - see `ansible/tasks/apply_openshift_build.yml` for the
shared mechanism.

No `precheck.yml`/`install.yml` - this is a build-only
role, distinct from the `rag` Day 1 `run` component (`ansible/roles/rag`),
which deploys the already-built image.
