# kueue

Applies the `gitops/apps/kueue` ArgoCD Application pair (ADR-0321), whose
chart (`gitops/charts/kueue`) installs the Red Hat build of Kueue Operator
(OLM `Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time - ADR-0048, same pattern as
`ansible/roles/jobset`) into `openshift-operators`. A Day 0 component
(ADR-0056) with all three verbs: `check` verifies both Applications are
Synced+Healthy plus the singleton `Kueue` operand CR and default
`ClusterQueue` exist; `install` discovers the package/channel and applies
`-d0` (`Subscription` only) then `-d1` (the `Kueue` operand CR and the
default `ResourceFlavor`/`ClusterQueue`/`LocalQueue`); `uninstall` tears
both down in reverse order plus the OLM-owned CRDs/CSV/Subscription
(`ansible/tasks/remove_operator.yml`).

## Why this role exists, and why (unlike jobset) it has real d1 content

`gitops/charts/openshift-ai/values.yaml`'s `DataScienceCluster` declares
`kueue.defaultClusterQueueName`/`defaultLocalQueueName: default` but,
before ADR-0321, never installed a dedicated operator or set
`managementState: Unmanaged` - so those queue names referred to nothing.
Red Hat OpenShift AI 3.5 documents the Red Hat build of Kueue Operator as
the supported way to own Kueue lifecycle (`Unmanaged` lets RHOAI defer to
it instead of an embedded, unsupported-for-this-purpose path).

Unlike `ansible/roles/jobset` (operator only, no operand CR - individual
`JobSet` objects are created later by consumers), the `kueue-operator`
package ships a singleton `Kueue` CR (`kueue.openshift.io/v1`, named
`cluster`) that the operator watches to actually deploy its managed
controller - same "meta-operator needs a CR to actually deploy pods" shape
as `ansible/roles/custom_metrics_autoscaler`'s `KedaController`. Without
it, the operator installs but nothing runs. `templates/kueue-operand.yaml`
renders that CR; `templates/queue-resources.yaml` renders the default
`ResourceFlavor`/`ClusterQueue`/`LocalQueue` Zuno's `DataScienceCluster`
config already assumes exist, gated separately (`queueResources.enabled`)
so operator installation and Zuno's own quota policy stay decoupled per
ADR-0321's Decision.

No GPU `ResourceFlavor`/quota exists yet - ADR-0321's Operational
considerations call this out explicitly as required "before distributed
training or queued model workloads are enabled," and none exist in this
repository yet (same "prerequisite ahead of any consumer" shape as
ADR-0317/ADR-0318).

## Package name and install mode

`kueue-operator` (checked in as `gitops/charts/kueue/values.yaml`'s
`subscription.name`/`subscription.operator.name`), channels
`stable-v1.3`/`stable-v1.4` (default `stable-v1.4`), confirmed against a
live cluster's `redhat-operators` catalog - including that its CSV only
supports the `AllNamespaces` install mode, so this subscribes into
`openshift-operators` the same way `ansible/roles/jobset`/`ansible/roles/lws`
do, not the dedicated-namespace shape
`ansible/roles/custom_metrics_autoscaler` uses.

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

## Known gap versus ADR-0321's acceptance criteria wording

ADR-0321's acceptance criteria say "`make d1 check` validates OpenShift
AI/Kueue integration" - but `openshift-ai` (and now `kueue`) are
`DAY0_COMPONENTS` entries in this repository's actual `Makefile`, not
`DAY1_RUN_COMPONENTS`; there is no `make d1 check` path for either. The
integration check this criterion asks for is implemented instead inside
this role's own Day 0 `precheck.yml` (the diagnostic `DataScienceCluster`
`kueue.managementState` lookup) - called out here rather than silently
reinterpreting the ADR's text.
