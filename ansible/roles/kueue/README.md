# kueue

Applies the `gitops/apps/kueue` ArgoCD Application pair, whose
chart (`gitops/charts/kueue`) installs the Red Hat build of Kueue Operator
(OLM `Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time, same pattern as `ansible/roles/jobset`)
into its own dedicated `openshift-kueue-operator` namespace. A Day 0
component with all three verbs: `check` verifies both Applications are
Synced+Healthy plus the singleton `Kueue` operand CR and default
`ClusterQueue` exist; `install` discovers the package/channel and applies
`-d0` (`Subscription` only) then `-d1` (the `Kueue` operand CR and the
default `ResourceFlavor`/`ClusterQueue`/`LocalQueue`); `uninstall` tears
both down in reverse order plus the OLM-owned CRDs/CSV/Subscription
(`ansible/tasks/remove_operator.yml`).

## Why this role exists, and why (unlike jobset) it has real d1 content

`gitops/charts/openshift-ai/values.yaml`'s `DataScienceCluster` declares
`kueue.defaultClusterQueueName`/`defaultLocalQueueName: default`, which
needs a dedicated operator with `managementState: Unmanaged` to back it -
Red Hat OpenShift AI 3.5 documents the Red Hat build of Kueue Operator as
the supported way to own Kueue lifecycle (`Unmanaged` lets RHOAI defer to
it instead of an embedded, unsupported-for-this-purpose path).

Unlike `ansible/roles/jobset` (operator only, no operand CR), the
`kueue-operator` package ships a singleton `Kueue` CR
(`kueue.openshift.io/v1`, named `cluster`) that the operator watches to
actually deploy its managed controller - without it, the operator
installs but nothing runs. `templates/kueue-operand.yaml` renders that
CR; `templates/queue-resources.yaml` renders the default
`ResourceFlavor`/`ClusterQueue`/`LocalQueue` Zuno's `DataScienceCluster`
config already assumes exist, gated separately (`queueResources.enabled`)
so operator installation and Zuno's own quota policy stay decoupled.

ADR-0538/WP-117 discharged the GPU precondition ADR-0321 set for itself
("must account for GPU `ResourceFlavor` and quotas before distributed
training or queued model workloads are enabled"): a `gpu-mig` flavor
selects the `machine.startx.io/group=gpu` nodes and the `ClusterQueue`
gained a second `resourceGroup` holding the MIG resources, sized to the
live cluster totals (`nvidia.com/mig-1g.24gb: 4`,
`nvidia.com/mig-2g.48gb: 2`). `nvidia.com/gpu` is deliberately unquotaed -
allocatable is zero on MIG-partitioned nodes.

Enabling quota does not enable interception. The operand runs
`manageJobsWithoutQueueName: false`, so a Job is queued only if it carries
`kueue.x-k8s.io/queue-name` **and** lives in a namespace labelled
`kueue.openshift.io/managed=true`. Both opt-ins are explicit.

## Package name and install mode

`kueue-operator` (checked in as `gitops/charts/kueue/values.yaml`'s
`subscription.name`/`subscription.operator.name`), channels
`stable-v1.3`/`stable-v1.4` (default `stable-v1.4`). Its CSV only
supports the `AllNamespaces` install mode, so Kueue uses a dedicated
`openshift-kueue-operator` namespace with its own `AllNamespaces`-mode
`OperatorGroup`, rather than the shared `openshift-operators` namespace
`ansible/roles/jobset`/`ansible/roles/lws` use - the shared namespace's
webhook Service selector (`control-plane: controller-manager`, the
generic kubebuilder convention label) collides with other operators'
pods carrying that same label there.

Before subscribing a new operator into a shared namespace, check its own
`PackageManifest.status.channels[].currentCSVDesc.installModes` first:
this repository has hit both directions of this mismatch on live
clusters (Kueue needs `AllNamespaces` only; JobSet/LWS/Keycloak need
`OwnNamespace` only; `connectivity-link`/`external_secrets` need
`AllNamespaces` only).

**Not yet verified against a live install** (only the `PackageManifest`
was checked, not an actual running operator): that the `Kueue` operand CR
is cluster-scoped and named `cluster`, per the package's own
`alm-examples`. If the operator rejects `templates/kueue-operand.yaml`,
re-check the current `alm-examples` against the target cluster and
correct the chart accordingly.

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list `kueue`
immediately before `openshift_ai` (after `jobset`), and `Makefile`'s
`DAY0_COMPONENTS` includes `kueue` - `make d0 install kueue` (or the
default "all" run) installs it in that position, ahead of the
`DataScienceCluster` that consumes `kueue.managementState: Unmanaged`.

## No `make d1 check` path

`openshift_ai` and `kueue` are `DAY0_COMPONENTS`, not
`DAY1_RUN_COMPONENTS` - there is no `make d1 check` path for either. The
OpenShift AI/Kueue integration check instead lives in this role's own
Day 0 `precheck.yml` (the diagnostic `DataScienceCluster`
`kueue.managementState` lookup).
