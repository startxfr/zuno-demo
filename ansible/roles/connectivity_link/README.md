# connectivity_link

Applies the `gitops/apps/connectivity-link` ArgoCD Application pair, whose
chart (`gitops/charts/connectivity-link`) installs the Red Hat Connectivity
Link operator (OLM `Subscription`, channel/catalog discovered from the
cluster's own `PackageManifest` at apply time - same pattern as
`ansible/roles/external_secrets`) into `openshift-operators`, plus a
`Kuadrant` operand CR in its own `kuadrant-system` namespace.
`kuadrant.authorinoTls.enabled`
(`gitops/charts/connectivity-link/templates/{authorino,certificate}.yaml`)
additionally patches the Authorino sub-controller the `Kuadrant` CR causes
the operator to provision, enabling TLS on its listener - required by MaaS
(`DataScienceCluster`'s `MaaSPrerequisitesAvailable` condition checks
`spec.listener.tls.enabled` on the `Authorino` CR directly). This is a
direct patch of the `Authorino` CR, not a `Kuadrant` CR field - this CRD
version (`kuadrant.io/v1beta1`) exposes no `spec.authorino` override
(confirmed via `oc explain kuadrant.spec`). A Day 0 component with all
three verbs: `check` verifies the Application pair is
Synced+Healthy and the `Kuadrant` instance exists; `install` discovers the
package/channel, applies `-d0` (`Subscription` only, sync-wave `"10"`) then
`-d1` (`Namespace` + `Kuadrant`, sync-wave `"20"`) once `-d0` is Healthy;
`uninstall` tears both down in reverse order plus the OLM-owned
CRDs/CSV/Subscription (`ansible/tasks/remove_operator.yml`).

## Why this role exists

The operator is installed ahead of any consumer, to get the platform ready
for Gateway API-fronted inference policy (rate limiting/auth in front of
`kserve` endpoints). No `Gateway`, `AuthPolicy`, `RateLimitPolicy` or other
policy object exists yet - MaaS (`platform/docs/platform_profile.yaml`:
`maas: v0-active`) is the only current consumer, via the Authorino TLS
listener patch described above.

## Package name and namespace, confirmed against a real cluster

`rhcl-operator` (checked in as `gitops/charts/connectivity-link/
values.yaml`'s `subscriptionName`) is the correct OLM package name. Its
CSV only supports the `AllNamespaces` install mode, so the `Subscription`
lives in `openshift-operators`, relying on OLM's own pre-existing
`global-operators` `OperatorGroup` there - no custom `OperatorGroup` is
created. `kuadrant-system` remains the *operand* namespace (where the
`Kuadrant` CR and its sub-controller pods live), just not the operator's
own namespace.

Channel naming still isn't confirmed against a live catalog.
`install.yml`'s `PackageManifest` lookup fails with a clear diagnostic
(listing every published channel) if the guessed package name is ever
wrong on a given cluster - run `oc get packagemanifest -n
openshift-marketplace | grep -i connectivity` (or `-i kuadrant`/`-i rhcl`)
against the target cluster and either pass `-e
connectivity_link_package_name=<real name>` or correct the role/chart
defaults.

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list
`connectivity_link` immediately before `openshift_ai` (after `nvidia_gpu`),
and `Makefile`'s `DAY0_COMPONENTS` includes `connectivity-link` -
`make d0 install connectivity-link` (or the default "all" run) installs it
in that position.
