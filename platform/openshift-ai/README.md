# Platform: openshift-ai

OpenShift AI Operator and platform prerequisites for the RHOAI 3.5 EA2 MVP
(ADR-0047).

`ansible/roles/openshift_ai` installs the operator (channel discovered
from the cluster's own `PackageManifest`, ADR-0048 - see that role's
README) and applies the `DataScienceCluster` with `kserve` (model
serving) enabled and `kserve.serving.managementState: Removed`
(RawDeployment mode - see below), then creates the project namespace
(`zuno-ai-run`) and a GPU-capped `ResourceQuota` - formerly a separate
`datascience` role, merged into `openshift_ai` (ADR-0056: one role for
one conceptual prerequisite). `ansible/roles/nfd` and
`ansible/roles/nvidia_gpu` (`platform/gpu`) are GPU-serving prerequisites,
applied before it. `ansible/roles/connectivity_link` and `ansible/roles/lws` (ADR-0317),
`ansible/roles/custom_metrics_autoscaler` and `ansible/roles/jobset`
(ADR-0318) are also applied before it - all four ahead of any actual
consumer, see below.

## Which OpenShift AI 3.5 capabilities this repository actually uses

ADR-0047's Operational considerations name a broader list of possible
OpenShift AI capability dependencies (NFD, cert-manager, Service Mesh,
Connectivity Link, LeaderWorkerSet, MaaS) than what this repository's
actual v0 feature set needs. Only what's genuinely in use gets a
prerequisite role - "only install feature-specific dependencies when the
corresponding capability is enabled" (that ADR's own Decision) cuts both
ways: it also means *not* installing operators nothing here uses.

- **Node Feature Discovery** - genuinely required (GPU node labeling for
  the NVIDIA GPU Operator's default `ClusterPolicy`) and was a real,
  previously undeclared gap. See `ansible/roles/nfd`.
- **cert-manager, Red Hat OpenShift Service Mesh, Red Hat OpenShift
  Serverless** - **not installed, deliberately.** These would only be
  needed if KServe ran in Serverless mode. This repository's
  `DataScienceCluster` sets `kserve.serving.managementState: Removed`
  (RawDeployment mode) precisely so none of these three are required -
  see `ansible/roles/openshift_ai/tasks/prepare.yml`'s inline comment for
  the full reasoning (this was, in fact, a real bug found and fixed under
  ADR-0047: the previous `Managed` configuration implicitly needed all
  three operators, none of which this repository ever installed, and
  would never have reached `Ready` on a real cluster).
- **Connectivity Link** (Kuadrant-based API policy gateway) - **installed
  as of ADR-0317**, ahead of any consumer. Nothing in this repository's
  architecture uses it yet - the MCP Gateway (`components/mcp-gateway`)
  and AI Inference Gateway (`components/ai-gateway`) remain this project's
  actual policy enforcement points (ADR-0010, ADR-0011, ADR-0009) - but the
  operator and a minimal, empty `Kuadrant` CR are now installed to get the
  platform ready for Gateway API-fronted inference policy. See
  `ansible/roles/connectivity_link` and `platform/networking/README.md`.
- **LeaderWorkerSet** - **installed as of ADR-0317**, ahead of any
  consumer. This demo still serves exactly one always-on, single-GPU model
  (`gitops/charts/models`) with no multi-node/multi-GPU topology, but the
  operator is now installed to get the platform ready for that. See
  `ansible/roles/lws` and `platform/lws/README.md`.
- **Custom Metrics Autoscaler** (Red Hat's productized KEDA build) -
  **installed as of ADR-0318**, ahead of any consumer. This repository's
  `DataScienceCluster` now enables a richer `kserve` configuration
  (`modelsAsService`, `wva`, `nim`) that RHOAI's custom-metrics-based
  model-serving autoscaling depends on; no `ScaledObject`/
  `TriggerAuthentication` exists yet. See
  `ansible/roles/custom_metrics_autoscaler`.
- **JobSet** - **installed as of ADR-0318**, ahead of any consumer.
  `DataScienceCluster`'s `trainingoperator` (Kubeflow Training Operator v1,
  distinct from `trainer`/Kubeflow Trainer v2 below) schedules distributed
  training runs on the JobSet API - without this operator/CRD it couldn't
  actually schedule a distributed run, even though none exists yet in this
  repository. See `ansible/roles/jobset`.
- **Red Hat build of Kueue Operator** - **installed as of ADR-0321**,
  ahead of `openshift_ai`. This repository's `DataScienceCluster` declared
  `kueue.defaultClusterQueueName`/`defaultLocalQueueName: default` from
  the start but never installed a dedicated operator or set
  `managementState: Unmanaged` - ADR-0321 fixes that so `trainingoperator`
  has a supported queue-management path once distributed training runs
  actually exist. See `ansible/roles/kueue`.
- **`trainer` (Kubeflow Trainer v2), `ray`, `dashboard` and
  `mlflowoperator`** - briefly `managementState: Removed` (the first three)
  as of 2026-08-13, now back to `Managed` per **ADR-0331**. All four were
  verified live against a real cluster to be broken under this repository's
  then-custom namespace fields (ADR-0328) - three under
  `applicationsNamespace: zuno-ai-platform`, one under
  `monitoring.namespace: zuno-monitoring` - because RHOAI 3.5 EA2's bundled
  manifests hardcode the RHOAI default namespace names rather than deriving
  them from `DSCInitialization.spec`. `trainer`'s `ClusterTrainingRuntime`
  failed validation because RHOAI's own bundled
  `ValidatingWebhookConfiguration` hardcodes
  `kubeflow-trainer-controller-manager.redhat-ods-applications.svc`;
  `ray`'s `kuberay-operator` pod was rejected by every SCC on the cluster
  (RHOAI's namespace-specific SCC/RBAC bindings for Ray only exist for the
  product's default namespace); `dashboard`'s observability/Perses
  reconciliation didn't derive watched namespaces from
  `DSCInitialization.spec.monitoring.namespace` (failed with "unknown
  namespace for the cache" for `zuno-monitoring`) - **not**
  `applicationsNamespace`, an important distinction: an earlier pass at
  ADR-0331 reverted only `applicationsNamespace` and wrongly assumed that
  alone fixed `dashboard` too; `monitoring.namespace` needed its own revert
  to `redhat-ods-monitoring`; `mlflow-operator-controller-manager` (the pod
  whose CrashLoopBackOff surfaced this bug class) ran
  `--namespace=redhat-ods-applications` unconditionally with a generated
  `ClusterRole` that granted no list/watch on `Secret`/`ServiceAccount`/
  `ConfigMap`/`Deployment`/`Job`/`CronJob`/`Service`/`PersistentVolumeClaim`/
  `ServiceMonitor` anywhere, so its controller-runtime cache never synced.
  Same precedent as ADR-0047 disabling KServe Serverless mode because it
  "would never have reached Ready on a real cluster" - except this time,
  with four independently-broken components, ADR-0331 reverted the
  underlying namespace fields themselves back to RHOAI defaults
  (`applicationsNamespace: redhat-ods-applications`,
  `monitoring.namespace: redhat-ods-monitoring`, and
  `modelregistry.registriesNamespace: rhoai-model-registries` - RHOAI's own
  true Model Registry default, a separate namespace from
  `applicationsNamespace`) rather than disabling each component one by one.
  `gitops/charts/namespaces` now also declares `redhat-ods-operator`/
  `redhat-ods-applications`/`rhoai-model-registries`/`redhat-ods-monitoring`
  so they get the same governance (labels, NetworkPolicy, quota)
  `zuno-ai-platform` used to get. Nothing in this repository schedules a
  distributed training or Ray run yet, and nothing links to the RHOAI
  console UI (Zuno has its own `agent-frontend`) - but all four components
  are now `Managed` and expected healthy. Revisit a custom
  `applicationsNamespace` (restoring ADR-0328's original intent) alongside
  ADR-0301/ADR-0302 (v3 LoRA/PEFT and dataset-to-model MLOps pipelines) once
  RHOAI ships a fix.
- **MaaS** (Models-as-a-Service policy routing) - the underlying platform
  plumbing (`kserve.modelsAsService.managementState: Managed` and the
  `maas-default-gateway` this chart's own `templates/maas-gateway.yaml`
  renders) is active as of the OpenShift AI DSCInitialization/gateway
  work, not deferred. MaaS also requires Authorino (the auth sub-controller
  Connectivity Link's `Kuadrant` CR provisions) to accept TLS connections
  from the gateway - `DataScienceCluster`'s `MaaSPrerequisitesAvailable`
  condition checks `spec.listener.tls.enabled` on the `Authorino` CR
  directly. That's now satisfied by
  `gitops/charts/connectivity-link/templates/{authorino,certificate}.yaml`
  (`kuadrant.authorinoTls.enabled`, flipped on in
  `gitops/apps/connectivity-link/application-d1.yaml`) patching the
  `Authorino` CR directly - its `Kuadrant` CR has no override field for
  this on the installed CRD version - reusing the Vault-backed
  `vault-issuer` `ClusterIssuer` Keycloak already consumes.
  What's still v2 is the *policy* layer: ADR-0114 ("Zuno as MaaS policy
  router") and ADR-0201 (completing the MaaS governance plane -
  subscriptions, auth policy, usage observability) remain "To be
  implemented" - nothing in the current build routes application traffic
  through a MaaS policy layer yet, even though the gateway/serving/
  Authorino-TLS prerequisites it would sit in front of already exist.
- **OGX** - as of ADR-0322 (superseding ADR-0018 and ADR-0050 for OGX
  product mapping), this is the actual Red Hat OpenShift AI OGX Operator,
  a real `DataScienceCluster` component (`spec.components.ogx`), replacing
  the former `llamastackoperator` activation. **Not yet effective on a
  real cluster**: verified against a live cluster on 2026-08-11, the
  installed rhods-operator's `DataScienceCluster` CRD does not expose an
  `ogx` field yet (only `llamastackoperator`) - see the comment in
  `gitops/charts/openshift-ai/values.yaml` next to the `ogx:` block. The
  v0 scope here is the config swap and Day 1 diagnostic (see
  `ansible/roles/openshift_ai/tasks/precheck.yml`); the v1 scope (an
  actual OGX-backed RAG provider behind Zuno's retrieval contract) is
  separate, later work.
