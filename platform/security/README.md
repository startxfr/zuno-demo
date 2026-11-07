# Platform: security

Platform security policies and workload hardening.

## Workload hardening baseline (ADR-0052)

`check_workload_hardening.py` is the policy-as-code check ADR-0052's
Operational considerations ask for: it renders every chart this repo
directly controls via `helm template` and asserts the restricted baseline
(non-root, no privilege escalation, all Linux capabilities dropped,
`seccompProfile: RuntimeDefault`, read-only root filesystem, no
autonomously-mounted service account token, a dedicated `ServiceAccount`,
and a `NetworkPolicy`) is actually present in the rendered manifests, not
just claimed in a commit message. No live cluster needed - pure
`helm template`, runnable anywhere `helm` is on `PATH`:

```bash
python3 platform/security/check_workload_hardening.py
```

Two operator/third-party-managed workloads get a documented partial check
instead of the full baseline, because this repo does not control their raw
PodSpec and guessing at unverified CRD/chart fields risks breaking the
workload outright rather than hardening it - see the comments in
`gitops/charts/keycloak/templates/keycloak.yaml` (Keycloak Operator) and
`gitops/charts/models/templates/servingruntime-embedding.yaml` (KServe
vLLM container: needs a writable HuggingFace/compilation cache, so
`readOnlyRootFilesystem` is intentionally not set). Crunchy Postgres
Operator (PGO, `gitops/charts/postgresql`) and the upstream HashiCorp
Vault chart (`gitops/apps/vault/application-d1.yaml`) are not checked at all
here: PGO's operand pods are restricted-PSA-compliant by the operator's
own design with no user-facing override field, and Vault gets `global.openshift: true`
(that chart's own documented OpenShift-compatibility flag) rather than a
guessed-at securityContext override.

This is not wired into a CI pipeline - `.github/workflows/` doesn't exist
yet in this repository (see `.github/README.md`) - but is written to be
CI-usable (non-zero exit on failure) the moment one does.

## check_mesh_mtls.py (ADR-0602 / WP-224)

`python3 platform/security/check_mesh_mtls.py` renders every `gitops/apps`
Application (the hermetic rendering of `platform/vault/check_secret_access.py`)
and fails when a PeerAuthentication exists outside zuno-data, zuno-auth and
zuno-ai-run, when one of them lacks its namespace-wide `default`, when a
plaintext port exception has no `zuno.io/permissive-reason` (the values field
`reason:` naming the non-mesh caller) or is not PERMISSIVE, when a workload
PeerAuthentication overrides the namespace mode or duplicates another's
selector, and when zuno-ai-run or zuno-unifai has no EgressFirewall ending in
`Deny 0.0.0.0/0` (or one that allows 0.0.0.0/0). Negative cases:
`python3 platform/security/tests/test_check_mesh_mtls.py`. Wired into
`.github/workflows/lint.yml`.
