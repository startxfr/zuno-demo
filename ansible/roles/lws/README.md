# lws

Applies the `gitops/apps/lws` ArgoCD Application pair, whose chart
(`gitops/charts/lws`) installs the LeaderWorkerSet operator (OLM
`Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time, same pattern as
`ansible/roles/external_secrets`) into its own dedicated
`openshift-lws-operator` namespace. A Day 0 component with all three
verbs: `check` verifies the `-d0` Application is Synced+Healthy;
`install` discovers the package/channel and applies `-d0` (dedicated
Namespace + `OperatorGroup` + `Subscription`, sync-wave `"10"`) then the
no-op `-d1` (`gitops/charts/noop` - kept present/synced the same way
`ansible/roles/models` applies its own no-op side); `uninstall` tears both
down in reverse order plus the OLM-owned CRDs/CSV/Subscription
(`ansible/tasks/remove_operator.yml`).

## Why this role exists, and why there's no operand CR

This demo serves exactly one always-on, single-GPU model, no
multi-node/multi-GPU topology - but the operator is installed anyway,
ahead of any consumer, to get the platform ready for multi-node
distributed model serving, the same "prerequisite before the feature
that needs it" shape used for `nfd`. Unlike `connectivity_link`'s
`Kuadrant` CR, there is no cluster-singleton operand for LeaderWorkerSet
to instantiate: the operator only registers the `LeaderWorkerSet`
CRD/controller; individual multi-node workloads create their own
`LeaderWorkerSet` objects later (out of scope here - none exists in this
repository yet).

## Package name and namespace

`leader-worker-set`'s CSV only supports the `OwnNamespace` install mode
(not `SingleNamespace`/`MultiNamespace`/`AllNamespaces`) - the opposite
of `connectivity_link`'s CSV, which only supports `AllNamespaces`. This
role uses a dedicated `openshift-lws-operator` namespace with its own
`OwnNamespace`-scoped `OperatorGroup`
(`operator.operatorGroup.target: openshift-lws-operator` in
`gitops/charts/lws/values.yaml`) - the same shape
`ansible/roles/custom_metrics_autoscaler` uses for KEDA, not the
`AllNamespaces`-mode dedicated namespace `gitops/charts/kueue` uses
(Kueue's CSV requires the opposite install mode).

Package name/channel: `leader-worker-set` (checked in as
`gitops/charts/lws/values.yaml`'s `subscription.name`/
`subscription.operator.name`), channel `stable-v1.0`. If this ever stops
matching on a different cluster, `install.yml`'s `PackageManifest` lookup
fails with a clear diagnostic (listing every published channel) - run
`oc get packagemanifest -n openshift-marketplace | grep -i leader-worker`
(or `-i lws`) against the target cluster and either pass `-e
lws_package_name=<real name>` or correct the role/chart defaults, the
same idiom `ansible/roles/external_secrets/tasks/install.yml` documents
for its own operator.

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list `lws`
immediately before `openshift_ai` (after `connectivity_link`), and
`Makefile`'s `DAY0_COMPONENTS` includes `lws` - `make d0 install lws` (or
the default "all" run) installs it in that position.
