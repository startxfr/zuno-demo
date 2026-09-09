# ADR-0554: Widen RHOAI's built-in MonitoringStack to observe `zuno-ai-run`'s models

- **Status:** Implemented (live-verified 2026-09-09 - all 4 model targets
  `health: up` in RHOAI's own Prometheus, see the Dated correction note for
  the fourth piece the original Decision missed)
- **Target:** v0.5
- **Date:** 2026-09-09
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0522](0522-enable-openshift-ai-monitoring-stack-side-by-side.md)
  (prior art this ADR extends), [ADR-0552](0552-reuse-rhoais-perses-instance-instead-of-running-an-independent-one.md)/[ADR-0553](0553-collocate-perses-dashboards-in-redhat-ods-monitoring-for-visibility.md)
  (the reuse-not-duplicate precedent this approach follows). Neither is
  superseded.

## Context

RHOAI's own dashboard (`rhods-dashboard`) has a built-in "Observe & Monitor >
Dashboard > Models" tab. Live-observed on `demo333`: it shows only 1 of the 5
models actually deployed in `zuno-ai-run` (`qwen36-27b-instruct`, all-zero
stats), while **AI Hub > Models > Deployments** correctly lists all 5 as
`Ready` (`qwen36-27b-instruct`, `qwen35-9b`, `qwen35-9b-wesh`, `gpt-oss-20b`,
`embeddings`). Per ADR-0553's dated correction note, this tab renders a
**fixed, hardcoded set of six tabs** (Cluster/Models/LLM Traffic/LLM
Utilization/Usage/LLM Performance) backed by RHOAI's own `PersesDashboard`
objects - not something this repo can add tabs/panels to. The only lever
available is making the existing panels' queries return real data, by
populating the Thanos instance they read from.

Root cause, live-confirmed 2026-09-09: that tab reads exclusively from
RHOAI's own separate stack, `MonitoringStack/data-science-monitoringstack`
(`monitoring.rhobs/v1alpha1`, namespace `redhat-ods-monitoring`, the ADR-0522
phase-1 "RHOAI-managed-workloads-only" stack). Three independent conditions
all currently block it from seeing `zuno-ai-run`:

1. `spec.namespaceSelector` is absent on the CR. Per
   `oc explain monitoringstack.spec.namespaceSelector`: "To monitor resources
   in the namespace where Monitoring Stack was created in, set to null" - the
   default. `spec.resourceSelector` is already `{}` (matches any
   ServiceMonitor/PodMonitor by label, cluster-wide) but that never matters
   while the namespace scope itself is closed. Confirmed live: zero
   `namespace="zuno-ai-run"` series anywhere in this stack's Thanos today,
   even though KServe's own controller already auto-creates correctly-labeled
   PodMonitors there (`kserve-llm-isvc-vllm-engine`/`-default`,
   `monitoring.opendatahub.io/scrape: "true"`).
2. Even with (1) fixed, this stack's Prometheus ServiceAccount
   (`data-science-monitoringstack-prometheus`) has no RBAC to read
   `Pods`/`Services`/`Endpoints` in `zuno-ai-run` - its existing RoleBinding
   (to a same-named `ClusterRole`, `get`/`list`/`watch` on
   `services`/`endpoints`/`pods`/`endpointslices`/`ingresses`) is scoped only
   to `redhat-ods-monitoring`.
3. Even with (1)+(2) fixed, each model's NetworkPolicy would still drop the
   scrape request at L4. The PodMonitor scrapes pods directly
   (`targetPort: 8000`, `scheme: https`), and cross-referencing the four
   LLMInferenceService NetworkPolicies: only `qwen36-27b-instruct`'s admits
   any monitoring namespace at all (`openshift-monitoring`/
   `openshift-user-workload-monitoring`, a legacy ADR-0413 rule its own
   comment already marks "not actually needed") - none admits
   `redhat-ods-monitoring`, and the other three admit no monitoring source
   whatsoever.

**Hard constraint:** purely additive on the RHOAI side. Zero changes to the
platform's own Grafana/Kiali/`zuno-monitoring` stack, which already renders
this same data correctly via `prometheus-k8s` (`openshift-monitoring`) -
confirmed unaffected by anything below.

## Decision

1. **Widen `MonitoringStack/data-science-monitoringstack`'s
   `spec.namespaceSelector`** to `matchLabels:
   {kubernetes.io/metadata.name: zuno-ai-run}` - scoped to exactly this one
   namespace (never `{}`/all-namespaces), via a partial Ansible patch
   (`ansible/roles/openshift_ai/tasks/widen_monitoringstack_namespace_selector.yml`,
   wired into `install.yml`/`reconcile.yml`), not GitOps. This CR is
   RHOAI-operator-owned (`ownerReferences` to `Monitoring/default-monitoring`
   -> `DSCInitialization/default-dsci`, actively reconciled by RHOAI's own
   controller). Live-verified via `.metadata.managedFields` that the
   `monitoring` field-manager's Server-Side Apply ownership never claims
   `namespaceSelector` (only `alertmanagerConfig`/`logLevel`/
   `prometheusConfig`/`resourceSelector`/`resources`/`retention`) - under SSA
   semantics a field no manager asserts ownership over is never reverted, so
   this patch survives reconciliation. Same established pattern as this
   role's two existing siblings for `Monitoring/default-monitoring`-derived
   resources (`right_size_monitoring_stack.yml` for `TempoStack`,
   `dashboard_feature_flags.yml` for `OdhDashboardConfig`) - see those files
   for why GitOps/ArgoCD management, a blanket `ignoreDifferences`, and
   `Replace=true` are all rejected for this class of object.
2. **New Role/RoleBinding in `zuno-ai-run`**
   (`gitops/charts/models/templates/rolebinding-rhoai-monitoringstack-prometheus.yaml`,
   GitOps-managed - a brand-new resource this repo fully owns) granting
   `data-science-monitoringstack-prometheus` (ServiceAccount,
   `redhat-ods-monitoring`) read-only access
   (`get`/`list`/`watch` on `services`/`endpoints`/`pods`/`endpointslices`/`ingresses`)
   in `zuno-ai-run`. A dedicated Role rather than a `roleRef` to RHOAI's own
   `ClusterRole` - same "widen with a targeted extra Role, never a broader
   built-in" idiom as `gitops/charts/aap-config/templates/
   rolebinding-openshift-ai-secrets.yaml`/`rolebinding-rhtas-signer-secret.yaml` -
   decouples this grant from RHOAI renaming or narrowing that ClusterRole on
   a future upgrade.
3. **NetworkPolicy admission for `redhat-ods-monitoring` on TCP 8000**, added
   to all four LLMInferenceService NetworkPolicies
   (`gitops/charts/models/templates/networkpolicy-{qwen,qwen35,gptoss,wesh}.yaml`),
   gated by the chart's existing `metrics.enabled` flag. Corrected three
   stale comments claiming "metrics scraping needs no allowance here" - true
   only in the sense that the PodMonitor object exists (KServe's controller
   auto-creates it), not that the scrape request actually reaches the pod.
4. **New `PodMonitor` (`monitoring.rhobs/v1`)**
   (`gitops/charts/models/templates/podmonitor-rhoai-vllm-engine.yaml`,
   GitOps-managed) mirroring KServe's own auto-created
   `kserve-llm-isvc-vllm-engine` selector/relabelings. Found live-necessary
   after decisions 1-3 alone still left zero series flowing (see the Dated
   correction note below) - not part of the original decision.

## Operational considerations

**Corrected (see Dated correction note): `resourceSelector: {}` does NOT
surface other pre-existing `zuno-ai-run` ServiceMonitors/PodMonitors**
(`vllm-predictors`/`zuno-evalhub-metrics`/`zuno-guardrails-smoke-service-monitor`)
the way this section originally claimed - all three are
`monitoring.coreos.com/v1` (live-verified), the wrong CRD group for RHOAI's
Prometheus to ever see, same as the KServe PodMonitors decision 4 exists to
route around. The only object this widening actually admits is decision
4's own `monitoring.rhobs/v1` PodMonitor. Its series are ALSO scraped by
the platform's own `prometheus-k8s`, via the separate, pre-existing
`monitoring.coreos.com/v1` KServe PodMonitors, under different `job`/
`instance` labels - two independent Prometheus instances each
independently scraping the same target pods, not one Prometheus
double-matching a single Service via an ambiguous selector (a previously
seen, different bug class) - no double-counting risk for any existing panel
in either stack.

**If the field-manager assumption in Decision 1 ever stops holding** (the
`namespaceSelector` patch reverts within seconds of a green
`make d1 reconcile openshift-ai`), RHOAI's operator has started owning that
field: drop `widen_monitoringstack_namespace_selector.yml` and record it as
an upstream constraint here, rather than adding retries to fight a
controller - same standing instruction as this task file's two siblings.

`make d1 uninstall openshift-ai` needs no counterpart: the `MonitoringStack`
CR (and this patch with it) is cascade-deleted by the operator/CRD removal
`remove_operator.yml` already performs. `make d2 uninstall models` needs no
counterpart either: the Role/RoleBinding and NetworkPolicy rules are pruned
automatically by ArgoCD's existing `prune: true`.

## Security considerations

This decision is a deliberate widening, not a weakening: the new RoleBinding
grants read-only (`get`/`list`/`watch`, no `create`/`update`/`delete`) access
to non-secret discovery objects (`services`/`endpoints`/`pods`/
`endpointslices`/`ingresses`) in one namespace, to one already-existing,
RHOAI-managed ServiceAccount, mirroring exactly the read-only rules that
ServiceAccount already holds in its own namespace - no new capability class,
only an additional scope. The NetworkPolicy change admits one more monitoring
source on the same port these policies already open to other monitoring
consumers, nothing new port-wise. No Secret, credential, or write-capable
RBAC is touched anywhere in this change.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Acceptance criteria and Review evidence.

## Dated correction note (2026-09-09)

Decisions 1-3 as originally written were necessary but not sufficient.
Live-verified after applying all three: `MonitoringStack`'s `namespaceSelector`
correctly widened (confirmed via the underlying `Prometheus` CR's own
`serviceMonitorNamespaceSelector`/`podMonitorNamespaceSelector`), the
RoleBinding correctly granted, the NetworkPolicy correctly admitting - yet
`/api/v1/status/config` on the live Prometheus pod still showed zero
`zuno-ai-run` mentions and zero scrape targets, repeatedly, across a
restart of the operator controller pod (`obo-prometheus-operator`) and
several of its own "sync prometheus" reconcile passes with no error logged.

Root cause: KServe's LLMInferenceService controller creates its
`kserve-llm-isvc-vllm-engine(-default)` PodMonitor under
`monitoring.coreos.com/v1` (confirmed: `oc get podmonitor ... -o
jsonpath='{.apiVersion}'`). RHOAI's MonitoringStack is built on Red Hat's
Cluster Observability Operator, whose own `obo-prometheus-operator`
ServiceAccount's ClusterRole (read live from the cluster) grants
`get`/`list`/`watch` **only** on the `monitoring.rhobs` API group -
`podmonitors.monitoring.coreos.com` and `podmonitors.monitoring.rhobs` are
two entirely separate CRDs (different `spec.group`, confirmed via `oc get
crd`) that merely share the Kind name `PodMonitor`. No namespaceSelector,
RBAC or NetworkPolicy change can bridge that gap - the operator's
informers are wired to one specific CRD group and structurally cannot
discover objects registered under the other, no matter how permissive
`resourceSelector`/`namespaceSelector` are set.

This exact landmine was already documented in this repo, just not read
before starting this ADR: `gitops/charts/models/templates/
servicemonitor-vllm.yaml`'s own header comment and
`gitops/charts/observability/templates/servicemonitor-otel-collector.yaml`
both warn that `monitoring.rhobs/v1` here would "render successfully and
never be scraped by prometheus-k8s" - the same trap in the opposite
direction. `gitops/charts/mesh-monitoring/templates/
podmonitor-istio-proxy.yaml`/`servicemonitor-istiod.yaml` already carry
the correct `monitoring.rhobs/v1` choice for feeding a COO-based
MonitoringStack (`mesh-monitoring`), which is why Kiali's own Prometheus
data source has always worked without hitting this - it was the template
to copy, not read until after re-deriving the same conclusion the hard
way.

Fixed by adding Decision 4 (`podmonitor-rhoai-vllm-engine.yaml`, a new
`monitoring.rhobs/v1` PodMonitor mirroring KServe's own selector/
relabelings). Live-verified end to end after all four parts: all 4 model
targets (`qwen36-27b-instruct`, `qwen35-9b`, `qwen35-9b-wesh`,
`gpt-oss-20b`) `health: up` in RHOAI's own Prometheus within seconds of
applying it.

## Migration / evolution

If a future RHOAI/COO version exposes `spec.namespaceSelector` (or an
equivalent) through `DSCInitialization`/`Monitoring`'s own CRD schema, this
patch becomes redundant with a supported, GitOps-manageable knob - revisit
and retire the Ansible task in favor of that, not decided here. If RHOAI's
`Monitoring` controller is ever observed to start owning `namespaceSelector`
(see Operational considerations above), record that as a correction note
here rather than silently deleting the workaround.
