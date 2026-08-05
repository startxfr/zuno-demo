# Platform Configuration

Day 0 (cluster prerequisites, ADR-0056) components: `admin-context`,
`argocd`, `namespaces`, `vault`, `keycloak`, `postgresql`, `smtp`,
`external-secrets`, `nfd`, `nvidia-gpu`, `observability`, `openshift-ai`.

Day 1 (build + run the platform) components: `llm`, `models`,
`sql_schema`, `rag`, `mcp`, `agents`, `mlops`.

`make day0|d0 configure [component]` / `make day1|d1 configure|run
[component]` apply one or all components in controlled order - see
`ansible/README.md` and ADR-0056 for the full verb set (`check`/
`install`/`configure`/`all` for Day 0; `check`/`build`/`configure`/`run`/
`all` for Day 1).
