# service_mesh

A Day 0 component (`make d0 install service-mesh`). Applies
`gitops/apps/service-mesh/application-d0.yaml` (the `servicemeshoperator3`
OLM package, Red Hat's productized Sail Operator) then `application-d1.yaml`
(a Vault-backed mesh CA via `cert-manager-istio-csr`, `IstioCNI`, and the
`Istio` control plane itself) - `gitops/charts/service-mesh` - see
`gitops/apps/README.md` and `gitops/charts/service-mesh/README.md`.

Positioned right after `postgresql` in `day0_components`
(`ansible/playbooks/day0_{install,check}.yml`, reversed in
`day0_uninstall.yml`): the `pki/roles/istio` secrets engine and the
`istio-issuer` Kubernetes-auth role/policy this role's `ClusterIssuer`
depends on are prepared by `vault`'s own bootstrap script
(`ansible/roles/vault/kustomize/unseal-configure/configmap.yaml`), the same
way `cert_manager`'s `ClusterIssuer` depends on `vault`'s pre-existing
`cert-manager-issuer` role/policy. This role never writes to Vault directly
with the root token - it only discovers the Vault client Service (same
`app.kubernetes.io/name=vault` label-selector lookup `vault`/
`cert_manager`/`external_secrets` already use) and applies a declarative
`ClusterIssuer` pointing at the already-configured backend.

## Why `postgresql` must come first, and what that means for its pods

`zuno-data`/`zuno-auth`/`zuno-ai-run`/`zuno-ai-build` are labeled
`istio-injection: enabled` by `gitops/charts/namespaces` from the very
start of Day 0 (position 3 in `day0_components`) - long before this
component's sidecar-injection webhook exists. That means:

- **postgresql** (position 7, before this component) has its pods created
  *without* a sidecar. `install.yml`'s last step rollout-restarts its
  `StatefulSet`s (Crunchy PGO instance sets, label
  `postgres-operator.crunchydata.com/cluster=zuno-postgresql`) once the
  mesh control plane is Ready, so they pick one up retroactively.
- **keycloak** (the component right after this one) and every Day 1
  AI/agent workload (`agent-runtime`, `ai-gateway`, `mcp-gateway`,
  `rag-service`, `tekos`, `models`) are created after this component
  installs, so they auto-inject on first deploy with no restart needed.

`zuno-vault` is deliberately **not** labeled for injection - it's the
mTLS/PKI trust root this role's own `ClusterIssuer` depends on, so meshing
it risks a bootstrap circularity between Vault and the CA that would sign
its own sidecar's certificate.

## Why the Subscription channel/CSV and the istio-csr integration are flagged as assumptions

Like `cert_manager` before it, `servicemeshoperator3` was never installed
anywhere in this repository before - its exact package/channel/catalog
(`stable` / `servicemeshoperator3.v3.4.1` / `redhat-operators`) are taken as
given rather than discovered from the cluster's `PackageManifest`, but
`install.yml` validates the package/channel/CSV actually exist on-cluster
before applying (fail-fast, rather than blindly trusting the hardcoded
Subscription) - see `gitops/charts/service-mesh/README.md` for the same
caveat applied to `cert-manager-istio-csr`'s chart version and the
`pilot.env.ENABLE_CA_SERVER`/`global.caAddress` CA-delegation mechanism.

**Infrastructure + mTLS rollout is staged, not immediate.** This role only
brings the mesh control plane up and retrofits postgresql's sidecar; it
does **not** create `PeerAuthentication`/`AuthorizationPolicy` resources.
Per the roadmap this component was designed against, `PeerAuthentication`
STRICT should be rolled out per-namespace (`zuno-auth` -> `zuno-data` ->
`zuno-ai-run`/`zuno-ai-build`) after each is individually validated with
sidecars running, before any mesh-wide default - left as a documented,
opt-in follow-up rather than bundled into this component.
