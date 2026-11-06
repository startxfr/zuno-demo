# WP-224: Network and GitOps hardening: mesh, egress, AppProject, JWKS (delivers ADR-0602, ADR-0603)

- **State:** Not started
- **ADRs:** ADR-0602, ADR-0603
- **Depends on:** WP-222
- **Blocks:** WP-227
- **Estimated files touched:** ~30

> Execute this brief as a standalone task from the repository root. Every cluster action needs the user's go.

## Goal

Enforce what the mesh already issues (C3), limit what ArgoCD can do (C4), pin issuer and audience at the edge (C6) and close
open egress and plaintext hops (M1, M2, M4).

## ADR references

ADR-0602 clauses 4 to 6; ADR-0603 clause 2 (M1, M2, M4).

## Preconditions

- Re-read `gitops/charts/service-mesh/README.md`, `ansible/roles/argocd/kustomize/appproject/appproject.yaml`,
  `gitops/root-app-of-apps.yaml`, `gitops/charts/namespaces/templates/networkpolicy-platform.yaml`.
- Read the memory notes on mesh port exclusions for PostgreSQL and the zuno-mesh allowlist before writing a policy.

## Repo changes

1. `PeerAuthentication` STRICT mesh-wide with documented per-port exceptions; deny-by-default `AuthorizationPolicy` per
   namespace keyed on SPIFFE principals. Roll namespace by namespace, in `PERMISSIVE` plus logging first.
2. Default-deny egress on the platform baseline and a baseline for `zuno-ai-run`.
3. AppProject with an explicit kind list and destinations; remove the blanket `cluster-admin` binding; `Prune=false` on
   stateful resources; chart repository over HTTPS or by digest; branch protection and signed commits documented as a
   repository setting (outside this repository).
4. Authorino: JWKS over HTTPS, `iss` and `aud` rules on the quota route (the gateways' own audience check landed in WP-222).
5. PostgreSQL and MariaDB `sslmode=verify-full` with certificates from the Vault PKI.

## Verification

Per namespace, a plaintext call from a pod without a sidecar is refused; a call from an unlisted principal is refused;
a token for `aap` is refused at the Authorino route; an unlisted egress destination times out.
