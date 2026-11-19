# openshift_ai

Applies the `gitops/apps/openshift-ai` ArgoCD Application, whose chart
(`gitops/charts/openshift-ai`) installs the Red Hat OpenShift AI operator
(OLM `Subscription`, channel discovered from the cluster's own catalog -
see below) and the `DataScienceCluster` with `kserve` (model serving)
enabled. A Day 1 component (`DAY1_RUN_COMPONENTS` in the Makefile - this
paragraph said Day 0 until 2026-09-03, and `make d0 <verb> openshift-ai`
simply fails, as `tasks/reconcile.yml`'s own header already noted) with all
three verbs: `check` verifies the
operator is published in the catalog; `install` discovers the channel,
applies the Application (Namespace + OperatorGroup + Subscription at
sync-wave 10, DataScienceCluster at sync-wave 20 - gated on the
Subscription's custom health check) and waits for the DataScienceCluster
to report `Ready`; `configure` is a documented no-op. `zuno-ai-run`'s own
`Namespace`, its RHOAI dashboard label and its GPU `ResourceQuota` are
owned by `gitops/charts/namespaces` instead - this role no longer
creates or labels that `Namespace` itself.

## Channel discovery

`tasks/discover_channel.yml` (included by `install.yml` and
`reconcile.yml`) reads the `rhods-operator` `PackageManifest`'s published
channels and prefers `stable-3.5` - the 3.5 z-stream, which serves the
`3.5.0` GA the chart pins and later `3.5.z` patches, but never rolls to
3.6. It falls back to the first channel matching the `3.5` family, then to
the manifest's own `defaultChannel`, and fails with a clear diagnostic -
listing every published channel - if none is available, instead of a
hardcoded `eus-3.5` guess. The result is passed to the chart via
`gitops_app_extra_helm_values`
(`cluster-ods.operator.subscription.operator.channel`).

That injection REPLACES the Application's `spec.source.helm.values`
wholesale, so it, not `gitops/charts/openshift-ai/values.yaml`, is what a
live cluster ends up running - the chart value is the fallback for a plain
`helm template` or an ArgoCD sync with no Ansible in the loop. Both must
stay pinned to the same channel.

This preference used to be `beta`, which is where RHOAI 3.5 EA2 was
published (ADR-0002). It must not go back: `beta` is frozen on
`rhods-operator.3.5.0-ea.2`, so preferring it now resolves to a downgrade
off the 3.5.0 GA.

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

## Dashboard feature flags

`tasks/dashboard_feature_flags.yml` (shared by `install` and `reconcile`)
applies four flags to `OdhDashboardConfig/odh-dashboard-config` in
`redhat-ods-applications`; `tasks/set_dashboard_flags.yml` holds the values and
is the authoritative list. `disableLMEval: false` and `guardrails: true` unlock
the Evaluations and guardrails surfaces (ADR-0534/WP-115), `trainingJobs: true`
the training-jobs UI (ADR-0538/WP-117), and `disableKueue: false` the Kueue
workload-allocation UI (WP-123).

They are not in a chart because the CR is created by the RHOAI operator and has
three concurrent writers: the operator owns `disableTracking`, this role owns
the four flags, and the dashboard UI itself writes `hardwareProfileOrder` and
`modelServing` at runtime. With `prune`/`selfHeal` on every Application, ArgoCD
ownership would revert the UI's own writes, and the usual `ignoreDifferences`
escape hatch is the false-green trap this repo has hit three times. So this is a
partial merge patch that touches only the keys it names - never the whole
`dashboardConfig`.

The trap worth knowing: an **absent** flag is not "the operator's default". The
dashboard's flag evaluator returns `"off"` for an undefined key *before* it
applies the `disable*` inversion, and the CRD declares no defaults - so deleting
a key turns its surface off rather than restoring neutral behaviour. That is
exactly how `disableKueue` went missing and produced "Kueue is disabled in this
cluster" on a cluster whose Kueue operand was running fine. `check` reports any
drift as a blocked finding (auto-fix `make d1 reconcile openshift-ai`) without
marking the component uninstalled.
