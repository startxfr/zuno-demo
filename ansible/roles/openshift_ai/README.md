# openshift_ai

Applies the `gitops/apps/openshift-ai` ArgoCD Application, whose chart
(`gitops/charts/openshift-ai`) installs the Red Hat OpenShift AI operator
(OLM `Subscription`, channel discovered from the cluster's own catalog -
see below) and the `DataScienceCluster` with `kserve` (model serving)
enabled. A Day 0 component with all three verbs: `check` verifies the
operator is published in the catalog; `install` discovers the channel,
applies the Application (Namespace + OperatorGroup + Subscription at
sync-wave 10, DataScienceCluster at sync-wave 20 - gated on the
Subscription's custom health check) and waits for the DataScienceCluster
to report `Ready`; `configure` is a documented no-op. `zuno-ai-run`'s own
`Namespace`, its RHOAI dashboard label and its GPU `ResourceQuota` are
owned by `gitops/charts/namespaces` instead - this role no longer
creates or labels that `Namespace` itself.

## Channel discovery

`tasks/install.yml` reads the `rhods-operator` `PackageManifest`'s
published channels and selects the one matching the `3.5` family (falling
back to the manifest's own `defaultChannel`, and failing with a clear
diagnostic - listing every published channel - if neither is available)
instead of a hardcoded `eus-3.5` guess, then passes it to the chart via
`gitops_app_extra_helm_values` (`subscriptionChannel`). The exact
EA2/GA channel name published by a given catalog snapshot isn't
standardized.

## RawDeployment, not Serverless

`gitops/charts/openshift-ai/templates/datasciencecluster.yaml`'s
`kserve.serving.managementState` is `Removed`, not `Managed`. `Managed`
(with a `name: knative-serving` `KNativeServing` reference) implicitly
requires the Red Hat OpenShift Service Mesh Operator, the Red Hat
OpenShift Serverless Operator, and cert-manager, none of which this
repository installs - so on a real cluster this `DataScienceCluster`
would never reach `Ready`. This demo's one model (`gitops/charts/models`)
is always-on (`minReplicas == maxReplicas == 1`) with no use for
Serverless's scale-to-zero, so `Removed` (RawDeployment mode) is the
correct choice here - see that template's inline comment for the full
reasoning, and `gitops/charts/models/README.md` for the
`InferenceService`-level annotation that makes the same choice explicit
at that layer too.

MaaS-related dependencies are deliberately not installed - see
`platform/openshift-ai/README.md` for why. Connectivity Link and
LeaderWorkerSet are installed ahead of `openshift_ai` in the Day 0
sequence (`ansible/roles/connectivity_link`, `ansible/roles/lws`), ahead
of any actual consumer - see `platform/openshift-ai/README.md`'s
per-capability breakdown for the current disposition of every RHOAI
capability. Custom Metrics Autoscaler and JobSet are needed now that
this repository's `DataScienceCluster` enables `kserve`'s richer
autoscaling-relevant configuration and `trainer`/`trainingoperator`
respectively - installed the same way (`ansible/roles/
custom_metrics_autoscaler`, `ansible/roles/jobset`). The Red Hat build of
Kueue Operator - needed so `trainer`/`trainingoperator`'s distributed runs
have a supported queue-management path (`kueue.managementState:
Unmanaged`, not RHOAI's own embedded/unsupported-for-this-purpose path) -
is installed the same way (`ansible/roles/kueue`), immediately before
this role in the Day 0 sequence.

## Sync-wave ordering within the Application

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
