# service-mesh

Referenced by `gitops/apps/service-mesh/application-d0.yaml`
(`cluster-istio.operatorIstio`: the `servicemeshoperator3` `Subscription` in
`openshift-operators`) and `application-d1.yaml` (`clusterIssuer.enabled` +
`istioCsr.enabled` + `istiocni.enabled` + `istio.enabled`: the Vault-backed
mesh CA via `cert-manager-istio-csr`, the `IstioCNI`, and the `Istio` control
plane) - see `gitops/apps/README.md` - same `-d0`/`-d1` operator/operand
split as `cert-manager` (ADR-0312).

## Why `cluster-istio` is a dependency at all, and why it only renders a `Subscription`

This chart deploys OpenShift Service Mesh **3** (the Sail Operator,
`servicemeshoperator3`), not the Maistra-based OSSM 2. There's no
OSSM-3-specific startx chart, so this wraps the generic startx `cluster-istio`
chart (`alias:startx`, same convention as `openshift-ai`/`nvidia-gpu`/
`keycloak`/`postgresql`/`nfd`/`cert-manager`) purely for its vendored
`operator` subchart (`cluster-istio.operatorIstio`), which renders nothing
beyond a plain `Subscription`/`OperatorGroup` pair driven entirely by
values - nothing in it is OSSM-2-specific. `cluster-istio`'s own top-level
templates (`serviceMeshControlPlane.yaml`, `serviceMeshMember.yaml`) **are**
Maistra/OSSM-2-specific and are never rendered here (`cluster-istio.istio.*`
stays untouched, at the vendored chart's own `enabled: false` default).

`operatorGroup.enabled: false`: unlike the OSSM 2 setup, the Subscription
installs into `openshift-operators`, which already carries OpenShift's own
global `AllNamespaces` `OperatorGroup` - creating a second one there would
make OLM reject the Subscription (`TooManyOperatorGroups`). `project`/
`projectOperator` stay disabled too - OSSM 3 needs no dedicated operator
namespace the way OSSM 2's `istio-operators` did.

## Why the `Istio`/`IstioCNI` control plane is hand-authored, not vendored

The Sail Operator's `Istio`/`IstioCNI` CRDs (`sailoperator.io/v1`) have no
equivalent in `cluster-istio` (which only knows how to render Maistra's
`ServiceMeshControlPlane`/`ServiceMeshMember`), so `templates/istio.yaml` and
`templates/istiocni.yaml` create them directly. CA delegation is expressed
via `pilot.env.ENABLE_CA_SERVER: "false"` + `global.caAddress` pointing at
the vendored `cert-manager-istio-csr` chart's Service, so mesh workload
identity certs chain to the same Vault PKI root as everything else
cert-manager issues (`templates/clusterissuer-istio.yaml`'s
`vault-issuer-istio` `ClusterIssuer`).

## Why the Subscription channel/CSV and the CA-delegation mechanism are still flagged as assumptions

`servicemeshoperator3`'s package/channel/CSV (`stable` /
`servicemeshoperator3.v3.4.1` / `redhat-operators`) were never installed on
a live cluster from this repo - `ansible/roles/service_mesh/tasks/install.yml`
validates the package/channel/CSV actually exist on-cluster before applying
rather than trusting the hardcoded values blindly.

`templates/istio.yaml`'s `pilot.env.ENABLE_CA_SERVER`/`global.caAddress`
CA-delegation mechanism and the `cert-manager-istio-csr` chart version
(`0.16.0`) are asserted from general Sail Operator/istio-csr documentation,
**not verified** against a live cluster. Confirm both hold for the actual
installed CSV before relying on them.

`IstioCNI` is required on OpenShift with the Sail Operator (unlike legacy
Maistra, which manages the CNI plugin as part of the control plane install)
- not independently verified either.

**Infrastructure + mTLS rollout is staged, not immediate.** This chart only
brings the mesh control plane up; it does not create
`PeerAuthentication`/`AuthorizationPolicy` resources - left as a documented,
opt-in follow-up (see `ansible/roles/service_mesh/README.md`).
