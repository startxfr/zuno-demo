# custom_metrics_autoscaler

Applies the `gitops/apps/custom-metrics-autoscaler` ArgoCD Application pair
(ADR-0318), whose chart (`gitops/charts/custom-metrics-autoscaler`)
installs the Custom Metrics Autoscaler operator (Red Hat's productized
KEDA build; OLM `Subscription`, channel/catalog discovered from the
cluster's own `PackageManifest` at apply time - ADR-0048, same pattern as
`ansible/roles/external_secrets`) into a dedicated `openshift-keda`
namespace, plus a minimal, empty `KedaController` operand CR in that same
namespace. A Day 0 component (ADR-0056) with all three verbs: `check`
verifies the Application pair is Synced+Healthy and the `KedaController`
instance exists; `install` discovers the package/channel, applies `-d0`
(Namespace/OperatorGroup/Subscription, sync-wave `"10"`) then `-d1`
(`KedaController`, sync-wave `"20"`) once `-d0` is Healthy; `uninstall`
tears both down in reverse order plus the OLM-owned CRDs/CSV/Subscription
(`ansible/tasks/remove_operator.yml`).

## Why this role exists

`gitops/charts/openshift-ai/values.yaml`'s `DataScienceCluster` now
enables a richer `kserve` configuration (`modelsAsService`, `wva`, `nim`)
that RHOAI's custom-metrics-based model-serving autoscaling (scaling
`InferenceService` replicas on request-rate/queue-depth rather than
CPU/memory) depends on. ADR-0318 installs the operator ahead of any actual
`ScaledObject`/`TriggerAuthentication` consumer - none exists in this
repository yet, same "prerequisite before the feature that needs it" shape
ADR-0047 used for `nfd`.

## Install mode: OwnNamespace, deliberately different from connectivity-link/lws

Unlike `ansible/roles/connectivity_link` and `ansible/roles/lws` (both
`AllNamespaces`, subscribed into `openshift-operators` - `rhcl-operator`'s
CSV only supports that mode, confirmed against a real cluster, ADR-0317),
this operator uses a dedicated `openshift-keda` namespace with its own
`OwnNamespace`-scoped `OperatorGroup` - Red Hat's own documented install
procedure for this operator. This is a deliberate choice per this
operator's actual documented shape, not a repeat of the mistake
ADR-0317 fixed.

## Package name / namespace / channel / operand CR shape are unverified (ADR-0318)

Neither this operator's exact OLM package name (checked in as
`openshift-custom-metrics-autoscaler-operator`, `gitops/charts/
custom-metrics-autoscaler/values.yaml`'s `subscriptionName`), its channel
naming, nor the `KedaController` CRD's exact required shape has been
confirmed against a live OpenShift AI 3.5+ catalog - the checked-in CR
uses `spec: {}`. `install.yml`'s `PackageManifest` lookup fails with a
clear diagnostic (listing every published channel) if the guessed package
name is wrong - run `oc get packagemanifest -n openshift-marketplace |
grep -i keda` against the target cluster and either pass `-e
custom_metrics_autoscaler_package_name=<real name>` or correct the
role/chart defaults. If the empty `KedaController` spec is rejected by the
CRD, follow `gitops/charts/nvidia-gpu/README.md`'s `alm-examples`
discovery pattern (read the installed CSV's recommended default CR)
instead of hand-guessing a larger spec.

## Day 0 ordering

`ansible/playbooks/day0_{check,install,uninstall}.yml` list
`custom_metrics_autoscaler` immediately before `openshift_ai`, and
`Makefile`'s `DAY0_COMPONENTS` includes `custom-metrics-autoscaler` -
`make d0 install custom-metrics-autoscaler` (or the default "all" run)
installs it in that position.
