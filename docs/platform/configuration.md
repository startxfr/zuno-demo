# Platform Configuration

Day 0 (cluster prerequisites, ADR-0056) components: `admin-context`
(PriorityClasses, StorageClass check), `argocd`, `namespaces`, `vault`,
`cert-manager` (Vault-backed `ClusterIssuer` for workload/mesh certs),
`external-secrets` (syncs Vault secrets into Kubernetes `Secret`s),
`keycloak`, `postgresql`, `service-mesh` (Istio via the Sail Operator,
mesh-wide mTLS), `smtp`, `nfd`, `nvidia-gpu`, `observability`,
`openshift-ai`.

Day 1 (build + run the platform) components: `llm`, `models`,
`sql_schema`, `rag`, `mcp`, `agents`, `mlops`.

`make day0|d0 install [component]` / `make day1|d1 install [component]`
apply one or all components in controlled order - see `ansible/README.md`
and ADR-0056/ADR-0311-0314 for the full verb set (`check`/`install`/
`uninstall`/`all` for Day 0; `check`/`build`/`install`/`uninstall`/`all`
for Day 1).
