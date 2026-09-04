# Physical Architecture

The MVP targets OpenShift 4.22 on AWS IPI. Namespace layout:

- `zuno-ai-run` — every active agent's frontend/BFF (only `tekos` in v0)
  plus Agent Runtime, AI Gateway, MCP Gateway.
- `zuno-ai-build` — in-cluster image builds via `BuildConfig`/
  `ImageStream`, isolated from running workloads.
- `redhat-ods-applications` — RHOAI's own control-plane operands (KServe,
  the OGX Operator, AI Gateway); `rhoai-model-registries` — Model
  Registry. A prior custom shared-platform namespace (`zuno-ai-platform`)
  was tried, found unused and removed (ADR-0333, ADR-0548) — see docs/adr/
  for why.
- `zuno-auth` (Keycloak), `zuno-vault` (Vault, External Secrets
  Operator), `zuno-data` (PostgreSQL), `zuno-monitoring` (observability),
  `zuno-mesh` (Istio control plane) — one dedicated namespace per
  platform service.

Istio sidecar injection is enabled on `zuno-ai-run`
and `zuno-ai-build` for mesh-wide mTLS. OpenShift AI manages local model
serving on GPU workers. PostgreSQL, Keycloak, Vault, cert-manager,
External Secrets Operator, the service mesh and observability are
explicit Day 0 prerequisites (`make day0|d0 install`).

Detailed node sizing and resource requests are refined during implementation and captured in `docs/platform/configuration.md` and the `gitops/charts/*/values.yaml` deployment manifests.
