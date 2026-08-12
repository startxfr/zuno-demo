# jobset

Applies the `gitops/apps/jobset` ArgoCD Application pair (ADR-0318), whose
chart (`gitops/charts/jobset`) installs the JobSet operator (OLM
`Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time - ADR-0048, same pattern as
`ansible/roles/external_secrets`) into its own dedicated
`openshift-jobset-operator` namespace, plus a minimal, cluster-scoped
`JobSetOperator` operand CR (name `cluster`, `managementState: Managed`).
A Day 0 component (ADR-0056) with all three verbs: `check` verifies the
Application pair is Synced+Healthy and the `JobSetOperator` instance
exists; `install` discovers the package/channel, applies `-d0`
(dedicated Namespace + `OperatorGroup` + `Subscription`, sync-wave `"10"`)
then `-d1` (`JobSetOperator`, sync-wave `"20"`) once `-d0` is Healthy;
`uninstall` tears both down in reverse order plus the OLM-owned
CRDs/CSV/Subscription (`ansible/tasks/remove_operator.yml`).

## Why this role exists, and what the JobSetOperator CR does (and doesn't do)

`gitops/charts/openshift-ai/values.yaml`'s `DataScienceCluster` now
enables `trainer`/`trainingoperator` (Kubeflow Trainer v2), which runs
distributed training jobs on the JobSet API (`jobset.x-k8s.io`), not raw
Jobs/Pods - without this operator/CRD, `trainer`/`trainingoperator` cannot
actually schedule a distributed run. ADR-0318 installs the operator ahead
of any actual `TrainJob`/distributed run - none exists in this repository
yet, same "prerequisite before the feature that needs it" shape ADR-0047
used for `nfd`. The `JobSetOperator` CR (`operator.openshift.io/v1`,
cluster-scoped singleton named `cluster`) is the operator's own
management-state switch - same "meta-operator needs a CR to actually do
anything" shape as `gitops/charts/custom-metrics-autoscaler`'s
`KedaController` and `gitops/charts/connectivity-link`'s `Kuadrant` CR.
It is NOT a JobSet workload: the operator only registers the `JobSet`
CRD/controller once `Managed`; individual distributed training runs still
create their own `JobSet` objects later (out of scope here).

## Package name

`job-set` (checked in as `gitops/charts/jobset/values.yaml`'s
`subscription.name`/`subscription.operator.name`), channel `stable-v1.0`,
confirmed against a live cluster's `redhat-operators` catalog. ADR-0318
originally guessed `jobset-operator`, which doesn't exist on this catalog
- if `install.yml`'s `PackageManifest` lookup ever fails again on a
different cluster, check `oc get packagemanifest -n openshift-marketplace
| grep -i job` for that cluster's actual name and update this default (or
pass `-e jobset_package_name=<name>`).

Originally subscribed into the shared `openshift-operators` namespace
(`AllNamespaces`, no dedicated `OperatorGroup`) alongside `connectivity-link`/
`external_secrets`/`limitador`/`lws` - the "now-confirmed-safe shape"
assumption ADR-0318 made by analogy with those other operators. That
assumption was wrong for JobSet specifically: CONFIRMED against a live
cluster's `PackageManifest`, `job-set`'s CSV only supports
`OwnNamespace`/`SingleNamespace`, not `AllNamespaces`. Subscribing via
the shared namespace's implicit `AllNamespaces` global-operators
`OperatorGroup` put the CSV into `Failed` phase (reason
`UnsupportedOperatorGroup`, message "AllNamespaces InstallModeType not
supported, cannot configure to watch all namespaces") - this is what
showed as "Job Set Operator" Failed in Installed Operators. Fixed by
moving to a dedicated `openshift-jobset-operator` namespace with its own
`OwnNamespace`-scoped `OperatorGroup`
(`operator.operatorGroup.target: openshift-jobset-operator` in
`gitops/charts/jobset/values.yaml`) - the same shape
`ansible/roles/custom_metrics_autoscaler` already uses for KEDA, not the
`AllNamespaces`-mode dedicated namespace `gitops/charts/kueue` uses
(Kueue's CSV requires the opposite install mode).

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list `jobset`
immediately before `openshift_ai`, and `Makefile`'s `DAY0_COMPONENTS`
includes `jobset` - `make d0 install jobset` (or the default "all" run)
installs it in that position.
