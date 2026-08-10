# ADR-0052: Harden all workloads for OpenShift restricted security and SecNumCloud objectives

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

A repository-wide search currently finds no consistent pod/container `securityContext` or `automountServiceAccountToken` hardening in the reviewed Helm content. The project targets OpenShift and has a future SecNumCloud-oriented security objective.

## Decision

Adopt a default restricted workload baseline: run as non-root/arbitrary UID compatible with OpenShift, `allowPrivilegeEscalation: false`, drop all Linux capabilities, `seccompProfile: RuntimeDefault`, read-only root filesystem where compatible, explicit writable emptyDir mounts, and `automountServiceAccountToken: false` unless Kubernetes API access is required. Add NetworkPolicies and least-privilege service accounts by default.

## Consequences

Workloads align with OpenShift restricted expectations and reduce lateral movement/privilege risk. Some third-party images may require remediation or explicit documented exceptions.

## Security considerations

Exceptions require an ADR or security waiver with compensating controls. No component may request privileged SCC merely for convenience.

## Operational considerations

Add policy-as-code or CI checks that fail charts missing the baseline and verify deployed pods against the expected SCC/PSA behavior.

## Implementation state

**Implemented (2026-08-05) for every workload this repository directly controls; two operator/third-party-managed exceptions documented, not silently skipped.**

- Every raw-PodSpec Deployment (`gitops/charts/{tekos,agent-runtime,ai-gateway,mcp-gateway,mcp-sales-db,rag-service}`) now sets, at the pod level, `securityContext.runAsNonRoot: true`, `seccompProfile.type: RuntimeDefault`, `automountServiceAccountToken: false` (none of these services call the Kubernetes API) and a dedicated least-privilege `ServiceAccount`; at the container level, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]` and `readOnlyRootFilesystem: true` with an explicit writable `/tmp` `emptyDir` mount (Python services also get `PYTHONDONTWRITEBYTECODE: "1"`). No fixed `runAsUser`/`fsGroup` is set - OpenShift's restricted SCC assigns an arbitrary UID per namespace.
- `gitops/charts/models/templates/servingruntime.yaml`'s vLLM container gets `allowPrivilegeEscalation`/`capabilities.drop` but deliberately not `readOnlyRootFilesystem`: vLLM writes a HuggingFace/compilation cache under its own filesystem at startup, and hardening this without verifying the exact writable paths against a live cluster risks breaking model serving - a documented gap. The `InferenceService` predictor pod-level context is the same kind of gap (KServe's `model:` shorthand doesn't reliably expose a verified pod-level override in this profile). `gitops/charts/keycloak/templates/keycloak.yaml` gets the same partial treatment via the existing `spec.unsupported.podTemplate` overlay (pod-level fields + container flags, no `readOnlyRootFilesystem` for the same JVM-writes-its-own-caches reason). Crunchy Postgres Operator is documented as already restricted-PSA-compliant by its own design with no user-facing override field; the upstream Vault chart gets `global.openshift: true`, that chart's own documented flag.
- NetworkPolicies: `gitops/charts/namespaces` gained a `platformNamespaces` baseline (default-deny-other-namespaces + specific known cross-namespace allows) for `zuno-auth`/`zuno-data`/`zuno-telemetry`. `zuno-ai` deliberately does NOT get this baseline (see ADR-0037's implementation note: a broad same-namespace allow would defeat sales-db-mcp's isolation) - every `zuno-ai` workload instead has its own precise, workload-owned `NetworkPolicy`.
- Policy-as-code check: `platform/security/check_workload_hardening.py` renders every chart via `helm template` and asserts the baseline is present (70 checks across 6 Deployment charts + Keycloak + models, all passing) - not wired into a CI pipeline since `.github/workflows/` didn't exist yet at the time, but written to be CI-usable (non-zero exit) the moment one does. Verifying deployed pods against live SCC/PSA behavior is out of scope - no live cluster exists in this environment.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- ADR-0111
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
