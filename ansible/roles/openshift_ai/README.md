# openshift_ai

Applies the `gitops/apps/openshift-ai` ArgoCD Application (ADR-0312),
whose chart (`gitops/charts/openshift-ai`) installs the Red Hat OpenShift
AI operator (OLM `Subscription`, channel discovered from the cluster's
own catalog - ADR-0048, see below) and the `DataScienceCluster` with
`kserve` (model serving) enabled. A Day 0 component (ADR-0056) with all
three verbs: `check` verifies the operator is published in the catalog;
`install` discovers the channel, applies the Application (Namespace +
OperatorGroup + Subscription at sync-wave 10, DataScienceCluster at
sync-wave 20 - gated on the Subscription's custom health check, ADR-0312)
and waits for the DataScienceCluster to report `Ready`; `configure` is a
documented no-op. `zuno-ai-run`'s own `Namespace`, its RHOAI dashboard
label and its GPU `ResourceQuota` are owned by `gitops/charts/namespaces`
instead (ADR-0312) - this role no longer creates or labels that
`Namespace` itself, closing a prior double-ownership (that `Namespace`
used to be declared independently by this role, `ansible/roles/
external_secrets`, *and* `gitops/charts/namespaces`).

This role used to apply raw manifests directly via `ansible/tasks/
apply_kustomize.yml` (ADR-0310); ADR-0312 converted it, along with
`nfd`/`nvidia_gpu`/`external_secrets`, to the same "role applies one
ArgoCD Application" pattern every other Day 0/Day 1 component already
used. It was previously split across `openshift_ai` (operator +
DataScienceCluster) and a separate `datascience` role (namespace +
quota) - merged into one role for one conceptual prerequisite as part of
ADR-0056, since the split never reflected two genuinely independent
concerns.

## Channel discovery (ADR-0048)

`tasks/install.yml` reads the `rhods-operator` `PackageManifest`'s
published channels and selects the one matching the `3.5` family (falling
back to the manifest's own `defaultChannel`, and failing with a clear
diagnostic - listing every published channel - if neither is available)
instead of a hardcoded `eus-3.5` guess, then passes it to the chart via
`gitops_app_extra_helm_values` (`subscriptionChannel`). The exact
EA2/GA channel name published by a given catalog snapshot isn't
standardized, and a hardcoded value was explicitly flagged as an
unverified assumption in an earlier revision of this role.

## RawDeployment, not Serverless (ADR-0047)

`gitops/charts/openshift-ai/templates/datasciencecluster.yaml`'s
`kserve.serving.managementState` is `Removed`, not `Managed` - a
deliberate fix, not the original value. `Managed` (with a `name:
knative-serving` `KNativeServing` reference) implicitly requires the Red
Hat OpenShift Service Mesh Operator, the Red Hat OpenShift Serverless
Operator, and cert-manager, none of which this repository ever installed
- so on a real cluster this `DataScienceCluster` would never have reached
`Ready`. This demo's one model (`gitops/charts/models`) is always-on
(`minReplicas == maxReplicas == 1`) with no use for Serverless's
scale-to-zero, so `Removed` (RawDeployment mode) is the correct choice
here, not a workaround - see that template's inline comment for the full
reasoning, and `gitops/charts/models/README.md` for the
`InferenceService`-level annotation that makes the same choice explicit
at that layer too.

MaaS-related dependencies (also named in ADR-0047's Operational
considerations) are deliberately not installed - see
`platform/openshift-ai/README.md` for why. Connectivity Link and
LeaderWorkerSet, named in that same list, are no longer in that bucket:
ADR-0317 installs both operators (`ansible/roles/connectivity_link`,
`ansible/roles/lws`) ahead of `openshift_ai` in the Day 0 sequence, ahead
of any actual consumer - see that ADR and `platform/openshift-ai/
README.md`'s per-capability breakdown for the current disposition of
every capability ADR-0047 named. Custom Metrics Autoscaler and JobSet -
not named in ADR-0047 at all, but needed now that this repository's
`DataScienceCluster` enables `kserve`'s richer autoscaling-relevant
configuration and `trainer`/`trainingoperator` respectively - are
installed the same way by ADR-0318 (`ansible/roles/
custom_metrics_autoscaler`, `ansible/roles/jobset`). The Red Hat build of
Kueue Operator - needed so `trainer`/`trainingoperator`'s distributed runs
have a supported queue-management path (`kueue.managementState:
Unmanaged`, not RHOAI's own embedded/unsupported-for-this-purpose path) -
is installed the same way by ADR-0321 (`ansible/roles/kueue`), immediately
before this role in the Day 0 sequence.

## Sync-wave ordering within the Application (ADR-0312)

`gitops/charts/openshift-ai`'s `Namespace`/`OperatorGroup`/`Subscription`
carry `argocd.argoproj.io/sync-wave: "10"`, the `DataScienceCluster`
carries `"20"`. ArgoCD does not attempt wave 20 until wave 10 reports
`Healthy` - meaningful here because `ansible/roles/argocd/tasks/
apply_resource_health_checks.yml` registers a custom health check for
`operators.coreos.com/Subscription` (`Healthy` only once
`status.installedCSV` is set and that CSV has `Succeeded`). Without it,
ArgoCD's default health evaluation would report the `Subscription`
`Healthy` immediately after apply, before OLM has actually installed the
CSV that registers the `DataScienceCluster` CRD, and the wave 20 sync
would fail with "no matches for kind DataScienceCluster".
