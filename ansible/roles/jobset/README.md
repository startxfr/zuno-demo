# jobset

Applies the `gitops/apps/jobset` ArgoCD Application pair (ADR-0318), whose
chart (`gitops/charts/jobset`) installs the JobSet operator (OLM
`Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time - ADR-0048, same pattern as
`ansible/roles/external_secrets`) into `openshift-operators`. A Day 0
component (ADR-0056) with all three verbs: `check` verifies the `-d0`
Application is Synced+Healthy; `install` discovers the package/channel and
applies `-d0` (`Subscription` only, sync-wave `"10"`) then the no-op `-d1`
(`gitops/charts/noop` - kept present/synced the same way
`ansible/roles/models` applies its own no-op side); `uninstall` tears both
down in reverse order plus the OLM-owned CRDs/CSV/Subscription
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

## Package name is the least confirmed of any operator this repository installs

`jobset-operator` (checked in as `gitops/charts/jobset/values.yaml`'s
`subscriptionName`) is a placeholder with lower confidence than this
repository's other operators: it isn't confirmed that Red Hat ships JobSet
as a separate OLM-installable operator at all, rather than e.g. a
raw-manifest install from the upstream `kubernetes-sigs/jobset` releases,
or a dependency bundled inside the Trainer operator's own install. If
`install.yml`'s `PackageManifest` lookup fails because no such package
exists on the target catalog, that is the expected signal to check `oc
get packagemanifest -n openshift-marketplace | grep -i jobset` and, if it
genuinely isn't there, switch this role to whatever the correct
installation method turns out to be instead of continuing to guess an OLM
package name.

Subscribes into `openshift-operators` (`AllNamespaces`) rather than a
dedicated namespace - the now-confirmed-safe shape
`ansible/roles/external_secrets`/`ansible/roles/lws` already use, not the
dedicated-namespace shape that failed for `connectivity_link` on a real
cluster (`OwnNamespace InstallModeType is not supported`, ADR-0317).

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list `jobset`
immediately before `openshift_ai`, and `Makefile`'s `DAY0_COMPONENTS`
includes `jobset` - `make d0 install jobset` (or the default "all" run)
installs it in that position.
