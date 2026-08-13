# ai_gateway_build

Day 1 `build` component (ADR-0056, `make day1|d1 build ai-gateway`).
Builds `ai-gateway` via native OpenShift `BuildConfig`/`ImageStream` in
`zuno-ai-build` - see `ansible/tasks/apply_openshift_build.yml` for the
shared mechanism.

Added after the original mcp/rag/agent build trio: ADR-0056 flagged
`ai-gateway` as not covered by any Day 1 build component yet, intended to
be built by the existing GitHub Actions pipeline (ADR-0115) instead. On a
fresh cluster with no CI-published image, that leaves every `ai-gateway`
pod in permanent `ImagePullBackOff` - found via live-cluster testing on
api.demo222.startx.fr. This role closes that gap using the same in-cluster
build mechanism as the other three, rather than requiring the GitHub
Actions pipeline as a hard prerequisite for a working demo install.

No `precheck.yml`/`install.yml` - this is a build-only
role, distinct from the `ai-gateway` Day 1 `run` component
(`ansible/roles/ai_gateway`... if/when one exists), which deploys the
already-built image via `gitops/apps/ai-gateway`.
