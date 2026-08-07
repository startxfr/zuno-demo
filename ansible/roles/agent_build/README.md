# agent_build

Day 1 `build` component (ADR-0056, `make day1|d1 build agent`). Builds
`agent-runtime`, `agent-bff` and `agent-frontend` via native OpenShift
`BuildConfig`/`ImageStream` in `zuno-ai-build` - see `ansible/tasks/
apply_openshift_build.yml` for the shared mechanism.

`ai-gateway` is deliberately not part of this component (or any named
Day 1 build component) - flagged as an open follow-up in ADR-0056's
Implementation state, still built via the existing GitHub Actions
pipeline (ADR-0051) for now.

No `precheck.yml`/`install.yml` - this is a build-only
role, distinct from the `agents`/`llm` Day 1 `run` components, which
deploy the already-built images.
