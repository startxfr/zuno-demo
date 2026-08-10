# service-mesh

Referenced by `gitops/apps/service-mesh/application-d0.yaml`
(`cluster-istio.projectOperator`/`operatorIstio`: the `servicemeshoperator`
`Subscription` in `istio-operators`) and `application-d1.yaml`
(`clusterIssuer.enabled` + `istio.enabled` + `cluster-istio.istio.enabled`/
`members.enabled`: the Vault-backed mesh CA, the `ServiceMeshControlPlane`,
and the `ServiceMeshMember` set) - see `gitops/apps/README.md` - same
`-d0`/`-d1` operator/operand split as `cert-manager` (ADR-0312).

Wraps the startx `cluster-istio` chart (`alias:startx`, same convention as
`openshift-ai`/`nvidia-gpu`/`keycloak`/`postgresql`/`nfd`/`cert-manager`) as
its sole Helm dependency, replacing the previous direct
`https://charts.jetstack.io` dependency on `cert-manager-istio-csr` and the
Sail Operator (`servicemeshoperator3`, `sailoperator.io` `Istio`/`IstioCNI`
CRs) approach it came with.

## Why the `ServiceMeshControlPlane` is created by this chart, not `cluster-istio`

`cluster-istio`'s own `templates/serviceMeshControlPlane.yaml` (gated by
`istio.enabledControlPlane`) renders a **hardcoded** spec with no values
hook for `spec.security.certificateAuthority` - it can't express delegating
the mesh CA to our Vault-backed `ClusterIssuer`. So this wrapper leaves
`cluster-istio.istio.enabledControlPlane: false` and creates the
`ServiceMeshControlPlane` itself (`templates/istio.yaml`), the same split
this repo already uses for `cert-manager`/`cluster-certmanager` (vendored
chart installs the operator only; the wrapper owns the operand CR).
`ServiceMeshMember` has no such sensitivity, so it's left to the vendored
chart via `cluster-istio.istio.members`.

## Why the CSV, CA-delegation mechanism, and CNI handling are flagged as assumptions

`servicemeshoperator` was never installed anywhere in this repository before
- its exact package/channel/CSV (`stable` / `servicemeshoperator.v2.6.17-0`
/ `redhat-operators`) are taken as given rather than discovered from the
cluster's `PackageManifest` (same posture as the Sail Operator pin this
chart previously used).

`templates/istio.yaml`'s `spec.security.certificateAuthority` block
(delegating the control plane's CA to `vault-issuer-istio`) is asserted from
general knowledge of OpenShift Service Mesh / Maistra's cert-manager
integration, **not verified** against this operator's exact CSV. Confirm the
real field names via `oc explain
servicemeshcontrolplane.spec.security --api-version=maistra.io/v2` (or the
operator's docs) on a live cluster before relying on it. The Vault
`auth/kubernetes/role/istio-issuer` binding
(`ansible/roles/vault/kustomize/unseal-configure/configmap.yaml`) was
updated to the `cert-manager`/`cert-manager` controller identity (matching
`pki/roles/cert-manager`'s own role, on the assumption the same controller
processes both delegation chains) - re-verify alongside the CA-delegation
mechanism itself.

Legacy OSSM/Maistra 2.x is assumed to manage the Istio CNI plugin
automatically as part of the control plane install on OpenShift (unlike the
Sail Operator's separate `IstioCNI` CR) - not independently verified either.

**Infrastructure + mTLS rollout is staged, not immediate.** This chart only
brings the mesh control plane up; it does not create
`PeerAuthentication`/`AuthorizationPolicy` resources - left as a documented,
opt-in follow-up (see `ansible/roles/service_mesh/README.md`).
