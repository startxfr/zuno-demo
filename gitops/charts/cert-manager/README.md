# cert-manager

Referenced by `gitops/apps/cert-manager/application-d0.yaml` (operator.enabled:
`Namespace`s + `OperatorGroup` + `Subscription` + the operator's own
`CertManager` singleton CR, which actually deploys the controller/webhook/
cainjector pods) and `application-d1.yaml` (issuer.enabled: a Vault-backed
`ClusterIssuer`) - same `-d0`/`-d1` operator/operand split as
`nfd`/`nvidia-gpu`/`openshift-ai` (ADR-0312).

`ansible/roles/keycloak` (ADR-0316) is the first consumer of `vault-issuer`:
`gitops/charts/keycloak/templates/ingress.yaml` requests a `Certificate`
for Keycloak's external hostname via the `cert-manager.io/cluster-issuer`
annotation on a hand-authored `Ingress`, which cert-manager's ingress-shim
and OpenShift's Ingress-to-Route sync turn into an edge-terminated Route
with the issued certificate embedded. See
`ansible/roles/keycloak/README.md`'s "External TLS via cert-manager"
section for the mechanism and its unverified assumptions.

## Why the CertManager CR and the OLM package/channel/catalog are flagged as assumptions

Unlike `nfd`/`nvidia-gpu`/`openshift-ai` (well-known package names, single
operator namespace), the Red Hat build of cert-manager
("openshift-cert-manager-operator") was never installed anywhere in this
repository before, and its exact package/channel/catalog and the shape of
its singleton `operator.openshift.io/v1alpha1/CertManager` config CR
(`metadata.name: cluster`) are asserted here from general knowledge, not
verified against a live cluster in this environment - same posture this
repo already documents for RHBK's/PGO's channel selection before dynamic
discovery was added, or the NVIDIA GPU Operator's `ClusterPolicy` shape.
If `make d0 check cert-manager` shows any of this is wrong on a real
cluster, fix it the same way `ansible/roles/{keycloak,postgresql,
openshift_ai}/tasks/install.yml` do: discover the real values from the
cluster's own `PackageManifest` at run time instead of trusting this
hardcoded value.
