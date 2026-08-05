# ADR-0052: Harden all workloads for OpenShift restricted security and SecNumCloud objectives

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

A repository-wide search currently finds no consistent pod/container `securityContext` or `automountServiceAccountToken` hardening in the reviewed Helm content. The project targets OpenShift and has a future SecNumCloud-oriented security objective.

## Decision

Adopt a default restricted workload baseline: run as non-root/arbitrary UID compatible with OpenShift, `allowPrivilegeEscalation: false`, drop all Linux capabilities, `seccompProfile: RuntimeDefault`, read-only root filesystem where compatible, explicit writable emptyDir mounts, and `automountServiceAccountToken: false` unless Kubernetes API access is required. Add NetworkPolicies and least-privilege service accounts by default.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Workloads align with OpenShift restricted expectations and reduce lateral movement/privilege risk. Some third-party images may require remediation or explicit documented exceptions.

## Security considerations

Exceptions require an ADR or security waiver with compensating controls. No component may request privileged SCC merely for convenience.

## Operational considerations

Add policy-as-code or CI checks that fail charts missing the baseline and verify deployed pods against the expected SCC/PSA behavior.

## Implementation state

**Implemented (2026-08-05) for every workload this repository directly
controls; two operator/third-party-managed exceptions documented, not
silently skipped.**

Every raw-PodSpec Deployment (`gitops/charts/{tekos,agent-runtime,
ai-gateway,mcp-gateway,mcp-sales-db,rag-service}`) now sets, at the pod
level, `securityContext.runAsNonRoot: true` and
`seccompProfile.type: RuntimeDefault` plus
`automountServiceAccountToken: false` (none of these services call the
Kubernetes API) and a dedicated least-privilege `ServiceAccount`; at the
container level, `allowPrivilegeEscalation: false`,
`capabilities.drop: [ALL]` and `readOnlyRootFilesystem: true` with an
explicit writable `/tmp` `emptyDir` mount (Python services additionally
get `PYTHONDONTWRITEBYTECODE: "1"` so a read-only `/app` doesn't break
bytecode-cache writes). No fixed `runAsUser`/`fsGroup` is set - OpenShift's
restricted SCC assigns an arbitrary UID per namespace, and hardcoding one
would conflict with that range on a real cluster.

`gitops/charts/models/templates/servingruntime.yaml`'s vLLM container gets
`allowPrivilegeEscalation`/`capabilities.drop` (its `spec.containers` is a
raw `corev1.Container` list, a verified-safe injection point) but
deliberately not `readOnlyRootFilesystem`: vLLM writes a HuggingFace/
compilation cache under its own filesystem at startup, and setting this
without verifying the exact writable paths against a live cluster risks
breaking model serving outright rather than hardening it -
a documented gap, not a fabricated fix. The `InferenceService`
(`templates/inferenceservice.yaml`) predictor pod-level context is the
same kind of gap: KServe's `model:` shorthand doesn't reliably expose a
verified pod-level override in this KServe/RHOAI 3.5 profile.
`gitops/charts/keycloak/templates/keycloak.yaml` gets the same partial
treatment via the already-established `spec.unsupported.podTemplate`
overlay mechanism (pod-level fields + container `allowPrivilegeEscalation`/
`capabilities.drop`, no `readOnlyRootFilesystem` for the same
JVM-writes-its-own-caches reason). CloudNativePG
(`gitops/charts/postgresql`) is documented as already restricted-PSA
-compliant by the operator's own design with no user-facing override
field; the upstream HashiCorp Vault chart
(`gitops/apps/vault/application.yaml`) gets `global.openshift: true`, that
chart's own documented flag, rather than a guessed-at value path.

NetworkPolicies (Decision: "Add NetworkPolicies... by default"):
`gitops/charts/namespaces` gained a `platformNamespaces` baseline
(default-deny-other-namespaces + specific known cross-namespace allows)
for `zuno-auth`/`zuno-data`/`zuno-telemetry`, mirroring the existing
per-agent-namespace shape. `zuno-ai` deliberately does NOT get this
baseline - see ADR-0037's implementation note for why (a broad
same-namespace allow would defeat that ADR's sales-db-mcp isolation
requirement) - every `zuno-ai` workload instead has its own precise,
workload-owned `NetworkPolicy`.

Policy-as-code check (Operational considerations: "Add policy-as-code or
CI checks that fail charts missing the baseline"):
`platform/security/check_workload_hardening.py` renders every chart via
`helm template` and asserts the baseline is actually present (70 checks
across 6 Deployment charts + Keycloak + models, all passing) - not wired
into a CI pipeline since `.github/workflows/` doesn't exist yet in this
repository (`.github/README.md`), but written to be CI-usable (non-zero
exit) the moment one does. "Verify deployed pods against the expected
SCC/PSA behavior" (the live-cluster half of that same consideration) is
out of scope here, consistent with every other ADR in this build - no
live cluster exists in this environment.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0023
- ADR-0024
- ADR-0111
- ADR-0037

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
