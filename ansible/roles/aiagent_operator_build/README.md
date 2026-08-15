# aiagent_operator_build

Day 1 `build` component (ADR-0056, `make day1|d1 build aiagent-operator`).
Builds `aiagent-operator` (ADR-0327/ADR-0308) via native OpenShift
`BuildConfig`/`ImageStream` in `zuno-ai-build` - see
`ansible/tasks/apply_openshift_build.yml` for the shared mechanism.
`operator/aiagent-operator/Dockerfile` is Kubebuilder's own generated
multi-stage build (Go build stage + a minimal non-root runtime stage),
adapted to this repo's restricted-security conventions the same way
`components/agent-bff/Dockerfile` was.

No `precheck.yml`/`install.yml` - this is a build-only role, distinct
from the `aiagent_operator` Day 1 `run` component
(`ansible/roles/aiagent_operator`), which deploys the already-built image.
