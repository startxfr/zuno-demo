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
- **JobSet** - **installed as of ADR-0318**, ahead of any consumer. This
  repository's `DataScienceCluster` now enables `trainer`/`trainingoperator`
  (Kubeflow Trainer v2), which schedules distributed training runs on the
  JobSet API - without this operator/CRD, `trainer`/`trainingoperator`
  cannot actually schedule a distributed run, even though none exists yet
  in this repository. See `ansible/roles/jobset`.
- **MaaS** (Models-as-a-Service policy routing) - not applicable to v0.
  ADR-0049 ("Zuno as MaaS policy router") is explicitly deferred to v1 in
  the implementation sequencing plan; nothing in the current build routes
  through a MaaS layer.
- **OGX** - not a separate operator/capability to install at all. ADR-0018
  defines OGX as this project's own name for capabilities it already
  consumes via `kserve` (model serving) and pgvector/full-text retrieval
  (`components/rag-service`) - both already covered above, not a distinct
  prerequisite.
