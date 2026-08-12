# jobset

Applies the `gitops/apps/jobset` ArgoCD Application pair (ADR-0318), whose
chart (`gitops/charts/jobset`) installs the JobSet operator (OLM
`Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time - ADR-0048, same pattern as
`ansible/roles/external_secrets`) into its own dedicated
`openshift-jobset-operator` namespace. A Day 0 component (ADR-0056) with
all three verbs: `check` verifies the `-d0` Application is
Synced+Healthy; `install` discovers the package/channel and applies `-d0`
(dedicated Namespace + `OperatorGroup` + `Subscription`, sync-wave `"10"`)
then the no-op `-d1` (`gitops/charts/noop` - kept present/synced the same
way `ansible/roles/models` applies its own no-op side); `uninstall` tears
both down in reverse order plus the OLM-owned CRDs/CSV/Subscription
(`ansible/tasks/remove_operator.yml`).

## Why this role exists, and why there's no operand CR

`gitops/charts/openshift-ai/values.yaml`'s `DataScienceCluster` now
enables `trainer`/`trainingoperator` (Kubeflow Trainer v2), which runs
distributed training jobs on the JobSet API (`jobset.x-k8s.io`), not raw
Jobs/Pods - without this operator/CRD, `trainer`/`trainingoperator` cannot
actually schedule a distributed run. ADR-0318 installs the operator ahead
of any actual `TrainJob`/distributed run - none exists in this repository
yet, same "prerequisite before the feature that needs it" shape ADR-0047
used for `nfd`. There is no cluster-singleton operand for JobSet to
instantiate: the operator only registers the `JobSet` CRD/controller;
individual distributed training runs create their own `JobSet` objects
later (out of scope here).

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
`external_secrets`/`limitador`/`lws`. Moved to a dedicated
`openshift-jobset-operator` namespace with its own `AllNamespaces`-mode
`OperatorGroup` (`operator.operatorGroup.target: "all-ns"` in
`gitops/charts/jobset/values.yaml`) after `gitops/charts/kueue` hit a
real-cluster collision from that same shared-namespace shape: multiple
kubebuilder-scaffolded operators there carry the same generic
`control-plane: controller-manager` label, so a webhook Service's
Endpoints round-robinned admission calls across unrelated pods and
intermittently returned "connection refused" - see that chart's
`values.yaml` for the full incident. Isolating JobSet the same way removes
that collision risk structurally, while keeping the same `AllNamespaces`
install mode it was already subscribed under - not the `OwnNamespace`
shape that separately failed for `connectivity_link` on a real cluster
(`OwnNamespace InstallModeType is not supported`, ADR-0317).

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list `jobset`
immediately before `openshift_ai`, and `Makefile`'s `DAY0_COMPONENTS`
includes `jobset` - `make d0 install jobset` (or the default "all" run)
installs it in that position.
