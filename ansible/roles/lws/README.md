# lws

Applies the `gitops/apps/lws` ArgoCD Application pair (ADR-0317), whose
chart (`gitops/charts/lws`) installs the LeaderWorkerSet operator (OLM
`Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time - ADR-0048, same pattern as
`ansible/roles/external_secrets`) into its own dedicated
`openshift-lws-operator` namespace. A Day 0 component (ADR-0056) with all
three verbs: `check` verifies the `-d0` Application is Synced+Healthy;
`install` discovers the package/channel and applies `-d0` (dedicated
Namespace + `OperatorGroup` + `Subscription`, sync-wave `"10"`) then the
no-op `-d1` (`gitops/charts/noop` - kept present/synced the same way
`ansible/roles/models` applies its own no-op side); `uninstall` tears both
down in reverse order plus the OLM-owned CRDs/CSV/Subscription
(`ansible/tasks/remove_operator.yml`).

## Why this role exists, and why there's no operand CR

ADR-0047 originally judged LeaderWorkerSet "not applicable" - this demo
serves exactly one always-on, single-GPU model, no multi-node/multi-GPU
topology. ADR-0317 installs the operator anyway, ahead of any consumer, to
get the platform ready for multi-node distributed model serving - the same
"prerequisite before the feature that needs it" shape ADR-0047 itself used
for `nfd`. Unlike `connectivity_link`'s `Kuadrant` CR, there is no
cluster-singleton operand for LeaderWorkerSet to instantiate: the operator
only registers the `LeaderWorkerSet` CRD/controller; individual multi-node
workloads create their own `LeaderWorkerSet` objects later (out of scope
here - none exists in this repository yet).

## Package name and namespace

`gitops/charts/connectivity-link`'s original shape (a dedicated namespace
+ its own namespace-scoped `OperatorGroup`) failed on a real cluster with
`OwnNamespace InstallModeType is not supported` (ADR-0317's fix). This
operator's own install-mode support was never tested against a real
cluster before that fix landed, so it was changed preemptively to the
same `openshift-operators` (`AllNamespaces`) shape `external_secrets`
already uses, rather than risk shipping the same bug twice.

That `AllNamespaces` assumption turned out wrong for LWS specifically:
CONFIRMED against a live cluster's `PackageManifest`,
`leader-worker-set`'s CSV only supports `OwnNamespace` (not even
`SingleNamespace`/`MultiNamespace`, and not `AllNamespaces`). Subscribing
via the shared namespace's implicit `AllNamespaces` global-operators
`OperatorGroup` put the CSV into `Failed` phase (reason
`UnsupportedOperatorGroup`, message "AllNamespaces InstallModeType not
supported, cannot configure to watch all namespaces") - this is what
showed as "Red Hat build of Leader Worker Set" Failed in Installed
Operators; the *opposite* install-mode problem from `connectivity_link`
(whose CSV only supports `AllNamespaces`, not `OwnNamespace`). Fixed by
moving to a dedicated `openshift-lws-operator` namespace with its own
`OwnNamespace`-scoped `OperatorGroup`
(`operator.operatorGroup.target: openshift-lws-operator` in
`gitops/charts/lws/values.yaml`) - the same shape
`ansible/roles/custom_metrics_autoscaler` already uses for KEDA, not the
`AllNamespaces`-mode dedicated namespace `gitops/charts/kueue` uses
(Kueue's CSV requires the opposite install mode).

Package name confirmed against a live cluster's `redhat-operators`
catalog: `leader-worker-set` (checked in as
`gitops/charts/lws/values.yaml`'s `subscription.name`/
`subscription.operator.name`), channel `stable-v1.0` - ADR-0317's "not
yet verified" placeholder guess turned out correct. If this ever stops
matching on a different cluster, `install.yml`'s `PackageManifest` lookup
fails with a clear diagnostic (listing every published channel) - run
`oc get packagemanifest -n openshift-marketplace | grep -i leader-worker`
(or `-i lws`) against the target cluster and either pass `-e
lws_package_name=<real name>` or correct the role/chart defaults, the
same idiom `ansible/roles/external_secrets/tasks/install.yml` already
documents for its own operator.

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list `lws`
immediately before `openshift_ai` (after `connectivity_link`), and
`Makefile`'s `DAY0_COMPONENTS` includes `lws` - `make d0 install lws` (or
the default "all" run) installs it in that position.
