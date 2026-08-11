# lws

Applies the `gitops/apps/lws` ArgoCD Application pair (ADR-0317), whose
chart (`gitops/charts/lws`) installs the LeaderWorkerSet operator (OLM
`Subscription`, channel/catalog discovered from the cluster's own
`PackageManifest` at apply time - ADR-0048, same pattern as
`ansible/roles/external_secrets`). A Day 0 component (ADR-0056) with all
three verbs: `check` verifies the `-d0` Application is Synced+Healthy;
`install` discovers the package/channel and applies `-d0`
(Namespace/OperatorGroup/Subscription, sync-wave `"10"`) then the no-op
`-d1` (`gitops/charts/noop` - kept present/synced the same way
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

## Package name / namespace / channel are unverified (ADR-0317)

Neither this operator's exact OLM package name (checked in as
`leader-worker-set`, `gitops/charts/lws/values.yaml`'s `subscriptionName`),
its default namespace (`openshift-lws-operator`), nor its channel naming
has been confirmed against a live OpenShift AI 3.5+ catalog.
`install.yml`'s `PackageManifest` lookup fails with a clear diagnostic
(listing every published channel) if the guessed package name is wrong on
a given cluster - run `oc get packagemanifest -n openshift-marketplace |
grep -i leader-worker` (or `-i lws`) against the target cluster and either
pass `-e lws_package_name=<real name>` or correct the role/chart defaults,
the same idiom `ansible/roles/external_secrets/tasks/install.yml` already
documents for its own operator.

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list `lws`
immediately before `openshift_ai` (after `connectivity_link`), and
`Makefile`'s `DAY0_COMPONENTS` includes `lws` - `make d0 install lws` (or
the default "all" run) installs it in that position.
