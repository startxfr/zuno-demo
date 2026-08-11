# connectivity_link

Applies the `gitops/apps/connectivity-link` ArgoCD Application pair
(ADR-0317), whose chart (`gitops/charts/connectivity-link`) installs the
Red Hat Connectivity Link operator (OLM `Subscription`, channel/catalog
discovered from the cluster's own `PackageManifest` at apply time -
ADR-0048, same pattern as `ansible/roles/external_secrets`) and a minimal,
empty `Kuadrant` operand CR. A Day 0 component (ADR-0056) with all three
verbs: `check` verifies the Application pair is Synced+Healthy and the
`Kuadrant` instance exists; `install` discovers the package/channel,
applies `-d0` (Namespace/OperatorGroup/Subscription, sync-wave `"10"`)
then `-d1` (`Kuadrant`, sync-wave `"20"`) once `-d0` is Healthy; `uninstall`
tears both down in reverse order plus the OLM-owned CRDs/CSV/Subscription
(`ansible/tasks/remove_operator.yml`).

## Why this role exists

ADR-0047 originally judged Connectivity Link "not applicable" - nothing in
this repository's v0 feature set uses Kuadrant-based Gateway API policy;
this project's own MCP Gateway / AI Inference Gateway are its policy
enforcement points. ADR-0317 installs the operator anyway, ahead of any
consumer, to get the platform ready for Gateway API-fronted inference
policy (rate limiting/auth in front of `kserve` endpoints) - the same
"prerequisite before the feature that needs it" shape ADR-0047 itself used
for `nfd`. No `Gateway`, `AuthPolicy`, `RateLimitPolicy` or other policy
object exists yet; the `Kuadrant` CR checked in is intentionally empty.

## Package name / namespace / channel are unverified (ADR-0317)

Neither this operator's exact OLM package name (checked in as
`rhcl-operator`, `gitops/charts/connectivity-link/values.yaml`'s
`subscriptionName`), its default namespace (`kuadrant-system`), nor its
channel naming has been confirmed against a live OpenShift AI 3.5+
catalog. `install.yml`'s `PackageManifest` lookup fails with a clear
diagnostic (listing every published channel) if the guessed package name
is wrong on a given cluster - run `oc get packagemanifest -n
openshift-marketplace | grep -i connectivity` (or `-i kuadrant`/`-i rhcl`)
against the target cluster and either pass `-e
connectivity_link_package_name=<real name>` or correct the role/chart
defaults, the same idiom `ansible/roles/external_secrets/tasks/install.yml`
already documents for its own operator.

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list
`connectivity_link` immediately before `openshift_ai` (after `nvidia_gpu`),
and `Makefile`'s `DAY0_COMPONENTS` includes `connectivity-link` -
`make d0 install connectivity-link` (or the default "all" run) installs it
in that position.
