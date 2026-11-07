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
(confirmed via `oc explain kuadrant.spec`). A Day 1 component with all
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

## Day 1 ordering

This has always been a Day 1 component (this section previously, and
incorrectly, described a Day 0 placement it never actually had).
`ansible/playbooks/day1_{check,install,uninstall}.yml` list
`connectivity_link` immediately before `lws` and, since ADR-0421 moved
`keycloak`/`aap`/`aap_config` out to Day 0, right after `openshift_oauth`
(which now sits where `keycloak` used to). `Makefile`'s
`DAY1_RUN_COMPONENTS` includes `connectivity-link` -
`make d1 install connectivity-link` (or the default "all" run) installs
it in that position.

## Stale OLM annotations after RHCL 1.5

RHCL 1.5 takes Authorino, DNS and Limitador off OLM. Their CRDs lose the
`olm.managed=true` label but keep OLM's
`operatorframework.io/installed-alongside-*` annotations. On its next start,
olm-operator counts those CRDs as its own and unlabelled: it labels what it
can, exits, and does the same again after every restart. The result is a
CrashLoopBackOff with frozen CSV statuses, and no OLM install can finish.

On demo333 this surfaced on 2026-11-07, when a master reboot restarted
olm-operator, two days after the RHCL 1.5 upgrade.

`tasks/olm_crd_annotations.yml` handles it:

- `make d1 install connectivity-link` removes the stale annotations.
- `make d1 check connectivity-link` fails while any of them remain.

Both act only when no authorino-operator, dns-operator or limitador-operator
CSV is left, so a cluster on RHCL < 1.5 is never touched.
