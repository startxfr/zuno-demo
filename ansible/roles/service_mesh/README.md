# service_mesh

A Day 0 component (`make d0 install service-mesh`). Applies
`gitops/apps/service-mesh/application-d0.yaml` (the `servicemeshoperator`
OLM package, Red Hat OpenShift Service Mesh / Maistra, via the startx
`cluster-istio` chart) then `application-d1.yaml` (a Vault-backed mesh CA,
the `ServiceMeshControlPlane`, and the `ServiceMeshMember` set) -
`gitops/charts/service-mesh` - see `gitops/apps/README.md` and
`gitops/charts/service-mesh/README.md`.

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

## Why the CA-delegation mechanism is still flagged as an assumption

`servicemeshoperator`'s package/channel/CSV (`stable` /
`servicemeshoperator.v2.6.17` / `redhat-operators`) were confirmed against a
live cluster's `PackageManifest` (`oc get packagemanifest
servicemeshoperator -n openshift-marketplace`) - unlike most of this role's
other pins, this one is no longer a guess. `install.yml` still validates it
on every run (fail-fast, rather than blindly trusting the hardcoded
Subscription), since a different cluster's catalog can publish a different
CSV. See `gitops/charts/service-mesh/README.md` for the still-unverified
`ServiceMeshControlPlane` `spec.security.certificateAuthority`
CA-delegation mechanism.

**Infrastructure + mTLS rollout is staged, not immediate.** This role only
brings the mesh control plane up and retrofits postgresql's sidecar; it
does **not** create `PeerAuthentication`/`AuthorizationPolicy` resources.
Per the roadmap this component was designed against, `PeerAuthentication`
STRICT should be rolled out per-namespace (`zuno-auth` -> `zuno-data` ->
`zuno-ai-run`/`zuno-ai-build`) after each is individually validated with
sidecars running, before any mesh-wide default - left as a documented,
opt-in follow-up rather than bundled into this component.
