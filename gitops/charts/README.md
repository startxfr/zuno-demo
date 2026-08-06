# Zuno-authored charts

Helm charts for components that don't have a suitable upstream chart, plus
thin wrapper charts around a third-party chart when it needs local
additions (`vault` pulls in `hashicorp/vault` as a Helm dependency to add
an optional Route - see `vault/Chart.yaml`) - Tekos's FE/BFF/Agent
Runtime, the MCP Gateway and tool servers, the RAG service, Vault,
namespace/quota scaffolding, and observability wiring. Each chart is
referenced by exactly one `gitops/apps/<component>/application.yaml`.

Components using an upstream chart directly, with no local chart of their
own (Keycloak Operator, Crunchy Postgres Operator, External Secrets
Operator, OpenShift AI serving runtimes) do not have a directory here -
their `application.yaml` points at the upstream `repoURL`/`chart` instead.
