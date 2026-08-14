# Platform: openshift-ai

OpenShift AI Operator and platform prerequisites for the RHOAI 3.5 EA2 MVP.

`ansible/roles/openshift_ai` installs the operator (channel discovered
from the cluster's own `PackageManifest` - see that role's
README) and applies the `DataScienceCluster` with `kserve` (model
serving) enabled and `kserve.serving.managementState: Removed`
(RawDeployment mode - see below), then creates the project namespace
(`zuno-ai-run`) and a GPU-capped `ResourceQuota`. `ansible/roles/nfd` and
`ansible/roles/nvidia_gpu` (`platform/gpu`) are GPU-serving prerequisites,
applied before it. `ansible/roles/connectivity_link` and `ansible/roles/lws`,
`ansible/roles/custom_metrics_autoscaler` and `ansible/roles/jobset`
are also applied before it - all four ahead of any actual
consumer, see below.

## Which OpenShift AI 3.5 capabilities this repository actually uses

Possible OpenShift AI capability dependencies include NFD, cert-manager,
Service Mesh, Connectivity Link, LeaderWorkerSet, and MaaS - only what
this repository's v0 feature set genuinely uses gets a prerequisite role.

- **Node Feature Discovery** - required for GPU node labeling (the
  NVIDIA GPU Operator's default `ClusterPolicy`). See `ansible/roles/nfd`.
- **cert-manager, Red Hat OpenShift Service Mesh, Red Hat OpenShift
  Serverless** - not installed, deliberately. These are only needed if
  KServe runs in Serverless mode; this repository's `DataScienceCluster`
  sets `kserve.serving.managementState: Removed` (RawDeployment mode), so
  none of the three are required. See
  `ansible/roles/openshift_ai/tasks/prepare.yml`'s inline comment.
- **Connectivity Link** (Kuadrant-based API policy gateway) - installed
  ahead of any consumer. Nothing in this repository's architecture uses
  it yet - the MCP Gateway (`components/mcp-gateway`) and AI Inference
  Gateway (`components/ai-gateway`) remain this project's actual policy
  enforcement points - but the operator and a minimal, empty `Kuadrant`
  CR are installed to get the platform ready for Gateway API-fronted
  inference policy. See `ansible/roles/connectivity_link` and
  `platform/networking/README.md`.
- **LeaderWorkerSet** - installed ahead of any consumer. This demo still
  serves exactly one always-on, single-GPU model (`gitops/charts/models`)
  with no multi-node/multi-GPU topology; the operator is installed to get
  the platform ready for that. See `ansible/roles/lws` and
  `platform/lws/README.md`.
- **Custom Metrics Autoscaler** (Red Hat's productized KEDA build) -
  installed ahead of any consumer. This repository's `DataScienceCluster`
  enables a richer `kserve` configuration (`modelsAsService`, `wva`,
  `nim`) that RHOAI's custom-metrics-based model-serving autoscaling
  depends on; no `ScaledObject`/`TriggerAuthentication` exists yet. See
  `ansible/roles/custom_metrics_autoscaler`.
- **JobSet** - installed ahead of any consumer. `DataScienceCluster`'s
  `trainingoperator` (Kubeflow Training Operator v1, distinct from
  `trainer`/Kubeflow Trainer v2 below) schedules distributed training
  runs on the JobSet API; none exist yet in this repository. See
  `ansible/roles/jobset`.
- **Red Hat build of Kueue Operator** - installed ahead of
  `openshift_ai`. This repository's `DataScienceCluster` declares
  `kueue.defaultClusterQueueName`/`defaultLocalQueueName: default` and
  sets `managementState: Unmanaged`, giving `trainingoperator` a
  supported queue-management path once distributed training runs exist.
  See `ansible/roles/kueue`.
- **`trainer` (Kubeflow Trainer v2), `ray`, `dashboard` and
  `mlflowoperator`** - all four are `Managed`. RHOAI 3.5 EA2's bundled
  manifests hardcode the RHOAI default namespace names rather than
  deriving them from `DSCInitialization.spec`, so a custom
  `applicationsNamespace`/`monitoring.namespace` broke `trainer`'s
  `ClusterTrainingRuntime` validation, `ray`'s SCC bindings, `dashboard`'s
  observability reconciliation, and `mlflowoperator`'s RBAC. The fix
  reverted the namespace fields to RHOAI defaults
  (`applicationsNamespace: redhat-ods-applications`,
  `monitoring.namespace: redhat-ods-monitoring`, and
  `modelregistry.registriesNamespace: rhoai-model-registries`) rather
  than disabling each component one by one. `gitops/charts/namespaces`
  now also declares `redhat-ods-operator`/`redhat-ods-applications`/
  `rhoai-model-registries`/`redhat-ods-monitoring` so they get the same
  governance (labels, NetworkPolicy, quota) `zuno-ai-platform` used to
  get. Nothing in this repository schedules a distributed training or
  Ray run yet, and nothing links to the RHOAI console UI (Zuno has its
  own `agent-frontend`) - but all four components are `Managed` and
  expected healthy. Revisit a custom `applicationsNamespace` once RHOAI
  ships a fix.
- **MaaS** (Models-as-a-Service policy routing) - the underlying platform
  plumbing (`kserve.modelsAsService.managementState: Managed` and the
  `maas-default-gateway` this chart's own `templates/maas-gateway.yaml`
  renders) is active, not deferred. MaaS also requires Authorino (the
  auth sub-controller Connectivity Link's `Kuadrant` CR provisions) to
  accept TLS connections from the gateway - `DataScienceCluster`'s
  `MaaSPrerequisitesAvailable` condition checks
  `spec.listener.tls.enabled` on the `Authorino` CR directly. That's
  satisfied by
  `gitops/charts/connectivity-link/templates/{authorino,certificate}.yaml`
  (`kuadrant.authorinoTls.enabled`, flipped on in
  `gitops/apps/connectivity-link/application-d1.yaml`) patching the
  `Authorino` CR directly, reusing the Vault-backed `vault-issuer`
  `ClusterIssuer` Keycloak already consumes.
  What's still v2 is the *policy* layer: Zuno as MaaS policy router, and
  completing the MaaS governance plane (subscriptions, auth policy, usage
  observability) remain "To be implemented" - nothing in the current
  build routes application traffic through a MaaS policy layer yet, even
  though the gateway/serving/Authorino-TLS prerequisites it would sit in
  front of already exist.
- **OGX** - this is the actual Red Hat OpenShift AI OGX Operator, a real
  `DataScienceCluster` component (`spec.components.ogx`), replacing the
  former `llamastackoperator` activation. **Not yet effective on a real
  cluster**: the installed rhods-operator's `DataScienceCluster` CRD does
  not expose an `ogx` field yet (only `llamastackoperator`) - see the
  comment in `gitops/charts/openshift-ai/values.yaml` next to the `ogx:`
  block. The v0 scope here is the config swap and Day 1 diagnostic (see
  `ansible/roles/openshift_ai/tasks/precheck.yml`); the v1 scope (an
  actual OGX-backed RAG provider behind Zuno's retrieval contract) is
  separate, later work.
