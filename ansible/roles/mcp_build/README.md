# mcp_build

Day 1 `build` component (ADR-0056, `make day1|d1 build mcp`). Builds
`mcp-gateway`, `mcp-sales-db` and `mcp-confluence` (ADR-0117) via native
OpenShift `BuildConfig`/`ImageStream` in `zuno-ai-build` - see
`ansible/tasks/apply_openshift_build.yml` for the shared mechanism
(git-source Docker-strategy build, `ConfigChange` trigger, waits for
`status.phase: Complete`, fails loudly otherwise).

No `precheck.yml`/`install.yml` - this is a build-only
role, distinct from the `mcp` Day 1 `run` component (`ansible/roles/mcp`),
which deploys the already-built image.
