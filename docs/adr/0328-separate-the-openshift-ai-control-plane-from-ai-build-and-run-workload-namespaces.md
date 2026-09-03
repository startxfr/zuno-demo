# ADR-0328: Separate the OpenShift AI control plane from AI build and run workload namespaces

- **Status:** Superseded in part by [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) for `applicationsNamespace`; the build/run workload-namespace split (`zuno-ai-build`/`zuno-ai-run`) remains in effect
- **Target:** v0
- **Date:** 2026-08-12
- **Decision owners:** Zuno Demo architecture team

## Context

The Zuno OpenShift AI installation uses cluster-scoped resources such as `DataScienceCluster` and `DSCInitialization` to manage platform capabilities including KServe, OGX, Spark, Ray, Training Operator, TrustyAI, AI Pipelines, Model Registry, AI Gateway and Workbenches.

The current namespace topology must clearly separate three responsibilities:

- the **OpenShift AI platform and shared services**;
- the **AI build workload plane**;
- the **AI runtime workload plane**.

The OpenShift AI platform is shared between build and runtime activities. Components that serve both lifecycle phases must therefore not be placed in either `zuno-ai-build` or `zuno-ai-run`.

The architecture must follow the principle:

```text
zuno-ai-platform = shared AI platform and cross-lifecycle services
zuno-ai-build    = build, preparation and training workloads
zuno-ai-run      = serving and inference workloads
```

Any component that is common to both build and runtime must be placed in `zuno-ai-platform`, unless the component, Operator or Custom Resource explicitly imposes or requires another namespace.

## Decision

Introduce and use:

```text
zuno-ai-platform
```

as the main OpenShift AI platform namespace.

The target namespace topology becomes:

```text
                     cluster-scoped
               DataScienceCluster
              DSCInitialization
                      |
                      v
+--------------------------------------------------+
|                 zuno-ai-platform                 |
|                                                  |
| OpenShift AI shared platform                     |
|                                                  |
| Dashboard             KServe controllers         |
| OGX                   Spark Operator             |
| Ray Operator          Training Operator          |
| TrustyAI              AI Pipelines controllers   |
| AI Gateway            Feast Operator             |
| MLflow Operator       Model Registry             |
| other shared DSC-managed components              |
+----------------------+---------------------------+
                       |
              manages / watches
           +-----------+-----------+
           |                       |
           v                       v
+----------------------+  +----------------------+
|    zuno-ai-build     |  |     zuno-ai-run      |
|                      |  |                      |
| Workbenches          |  | InferenceService     |
| SparkApplication     |  | LLMInferenceService  |
| Ray jobs             |  | vLLM / llm-d         |
| Training jobs        |  | MaaS-served models   |
| Pipelines runs       |  | runtime GPU pods     |
| LoRA / PEFT          |  | TrustyAI runtime     |
| RAG ingestion        |  | inference workloads  |
| dataset preparation  |  |                      |
+----------------------+  +----------------------+
```

## Core namespace principle

The following rule applies to all OpenShift AI components:

> Any component, service or capability shared between the AI build and AI runtime lifecycle is deployed into `zuno-ai-platform`, unless its Operator, component implementation or Custom Resource requires a different namespace.

This means that `zuno-ai-platform` is not limited to controllers.

It is the namespace for:

- OpenShift AI control-plane components;
- shared AI platform services;
- cross-lifecycle services;
- registries;
- shared gateways;
- shared metadata services;
- shared orchestration components;
- platform-level observability components when not required to use another namespace;
- any other AI service used by both build and runtime workloads.

Dedicated namespaces are only introduced where required by:

- the component architecture;
- the Operator installation model;
- a Custom Resource namespace requirement;
- security or tenancy constraints formalized by another ADR.

## OpenShift AI applications namespace

Create `zuno-ai-platform` before installing or reconciling OpenShift AI:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: zuno-ai-platform
  labels:
    opendatahub.io/application-namespace: "true"
```

Configure the `DSCInitialization` with:

```yaml
apiVersion: dscinitialization.opendatahub.io/v2
kind: DSCInitialization
metadata:
  name: default-dsci
spec:
  applicationsNamespace: zuno-ai-platform
  monitoring:
    managementState: Managed
    namespace: zuno-monitoring
```

`DSCInitialization` remains a cluster-scoped resource.

`zuno-ai-platform` identifies the main OpenShift AI applications and shared platform namespace.

## DataScienceCluster

The `DataScienceCluster` remains cluster-scoped.

It must not be conceptually associated with:

```text
zuno-ai-build
```

or:

```text
zuno-ai-run
```

Its responsibility is to declare which OpenShift AI capabilities are enabled at cluster level.

The controllers and shared services associated with these capabilities are placed in `zuno-ai-platform`, unless the component explicitly requires another namespace.

Example:

```yaml
apiVersion: datasciencecluster.opendatahub.io/v2
kind: DataScienceCluster
metadata:
  name: zuno-dsc
spec:
  components:
    ogx:
      managementState: Managed

    sparkoperator:
      managementState: Managed

    kserve:
      managementState: Managed
      modelsAsService:
        managementState: Managed

    modelregistry:
      managementState: Managed
      registriesNamespace: zuno-ai-platform

    trustyai:
      managementState: Managed

    aipipelines:
      managementState: Managed

    ray:
      managementState: Managed

    kueue:
      managementState: Unmanaged
      defaultClusterQueueName: default
      defaultLocalQueueName: default

    workbenches:
      managementState: Managed
      workbenchNamespace: zuno-ai-build

    mlflowoperator:
      managementState: Managed

    dashboard:
      managementState: Managed

    trainer:
      managementState: Managed

    aigateway:
      managementState: Managed

    trainingoperator:
      managementState: Managed
```

## Build workload namespace

Use:

```text
zuno-ai-build
```

for workloads whose primary responsibility is to create, prepare, train or evaluate AI assets.

This includes, where applicable:

- OpenShift AI Workbenches;
- notebooks;
- AI Pipeline runs;
- `SparkApplication`;
- Ray development workloads;
- Ray training workloads;
- Training Operator jobs;
- LoRA training;
- PEFT training;
- model evaluation jobs;
- dataset preparation;
- feature engineering;
- RAG ingestion;
- embedding generation;
- vector indexing;
- preprocessing jobs.

Configure:

```yaml
spec:
  components:
    workbenches:
      managementState: Managed
      workbenchNamespace: zuno-ai-build
```

Example workload:

```yaml
apiVersion: sparkoperator.k8s.io/v1beta2
kind: SparkApplication
metadata:
  name: zuno-rag-ingestion
  namespace: zuno-ai-build
```

The Spark Operator itself remains part of the shared platform, while the Spark workload belongs to the build namespace.

The same pattern applies to Ray, Training Operator and AI Pipelines.

## Runtime workload namespace

Use:

```text
zuno-ai-run
```

for workloads whose primary responsibility is to serve or execute AI models.

This includes:

- `InferenceService`;
- `LLMInferenceService`;
- vLLM model servers;
- llm-d inference workloads;
- MaaS-served local models;
- inference GPU workers;
- runtime model endpoints;
- TrustyAI resources attached specifically to runtime models;
- runtime autoscaling resources;
- inference-oriented application workloads.

Example:

```text
KServe controller
zuno-ai-platform
        |
        | manages
        v
InferenceService
zuno-ai-run
        |
        v
model serving pods
zuno-ai-run
```

The shared model-serving control plane remains in `zuno-ai-platform`.

Only the concrete inference workloads are placed in `zuno-ai-run`.

## Model Registry

The Model Registry is considered a **shared platform capability**, because it represents the transition point between model creation and model consumption.

Its lifecycle is:

```text
BUILD
  |
  v
REGISTER
  |
  v
DEPLOY
  |
  v
RUN
```

Because it is used by both build and runtime workflows, it must be hosted in:

```text
zuno-ai-platform
```

Configure:

```yaml
spec:
  components:
    modelregistry:
      managementState: Managed
      registriesNamespace: zuno-ai-platform
```

The Model Registry must therefore not be placed in `zuno-ai-build`.

This follows the general architecture rule:

```text
shared between BUILD and RUN
        |
        v
zuno-ai-platform
```

## AI Gateway and MaaS

AI Gateway and MaaS are also considered shared platform capabilities.

They provide services used by runtime workloads but are not runtime workloads themselves.

Their shared control-plane components therefore belong in:

```text
zuno-ai-platform
```

Model-serving workloads exposed through MaaS remain in:

```text
zuno-ai-run
```

Conceptually:

```text
               zuno-ai-platform

          AI Gateway / MaaS Gateway
                  |
          auth / quota / routing
                  |
                  v

                zuno-ai-run

          LLMInferenceService
          vLLM / llm-d
          model workloads
```

## OGX

OGX is considered a shared AI platform capability.

Its controller and shared services belong in:

```text
zuno-ai-platform
```

Agent, RAG or other workloads using OGX can reside in the namespace corresponding to their lifecycle and ownership.

If an OGX Custom Resource imposes a namespace-specific deployment model, that requirement takes precedence.

## Kueue

Kueue is also a cross-lifecycle capability.

It can govern resource admission for workloads from both:

```text
zuno-ai-build
```

and:

```text
zuno-ai-run
```

The Red Hat build of Kueue Operator is installed according to ADR-0321 in the namespace required by that Operator.

Kueue resources such as `ClusterQueue` are cluster-scoped.

Namespace-scoped resources such as `LocalQueue` are created in the workload namespace they govern.

Example:

```text
ClusterQueue
   cluster-wide
        |
        +-------------------+
        |                   |
        v                   v
LocalQueue              LocalQueue
zuno-ai-build           zuno-ai-run
```

This is an example of the exception rule:

> A component can use its own imposed Operator namespace or resource-specific namespace while still being considered part of the shared AI platform architecture.

## Components with imposed namespaces

Some Operators and components may require dedicated namespaces independent from the Zuno namespace model.

Examples can include:

- Red Hat OpenShift AI Operator;
- Red Hat build of Kueue Operator;
- NVIDIA GPU Operator;
- Connectivity Link Operator;
- LeaderWorkerSet Operator;
- cert-manager;
- service mesh;
- observability operators.

These namespaces must not be artificially moved into `zuno-ai-platform`.

The rule is:

```text
Does the component impose its own namespace?
          |
      +---+---+
      |       |
     yes      no
      |       |
      v       v
component    shared?
required      |
namespace    yes --> zuno-ai-platform
              |
             no
              |
       build or run workload
```

## Namespace responsibility model

| Namespace | Responsibility | Lifecycle |
|---|---|---|
| `redhat-ods-operator` | Red Hat OpenShift AI Operator | Operator |
| `zuno-ai-platform` | Shared OpenShift AI control plane and cross-lifecycle AI services | Platform |
| `zuno-ai-build` | Data preparation, workbenches, pipelines, training, RAG ingestion and model creation | Build |
| `zuno-ai-run` | Model serving, inference and runtime AI workloads | Run |
| `zuno-monitoring` | Shared monitoring where explicitly configured | Cross-cutting |
| Component-specific namespaces | Operators/components that impose their own namespace | Component-specific |

The use of additional namespaces must be justified by a component requirement or another ADR.

## Security model

The namespace separation must also define distinct authorization boundaries.

### zuno-ai-platform

Write access is restricted to:

- platform administrators;
- OpenShift AI operators/controllers;
- automation identities explicitly responsible for AI platform lifecycle.

AI developers must not receive general `edit` access.

This namespace may contain sensitive shared capabilities such as:

- Model Registry;
- AI Gateway;
- MaaS configuration;
- OGX;
- shared model metadata;
- shared orchestration services.

### zuno-ai-build

AI developers can receive permissions required for:

- Workbenches;
- Pipelines;
- Spark;
- Ray;
- Training;
- LoRA;
- PEFT;
- data processing;
- RAG ingestion.

This namespace corresponds to the development/build plane.

### zuno-ai-run

Access is more restrictive because changes can directly affect exposed inference services.

Authorized AI operations profiles can manage:

- model deployments;
- inference scaling;
- serving runtimes;
- runtime model configuration.

## Network isolation

NetworkPolicies must reflect the lifecycle separation.

Expected flows include:

```text
                   zuno-ai-platform
                     /          \
                    /            \
                   v              v
          zuno-ai-build      zuno-ai-run
```

Examples:

```text
zuno-ai-build
   |
   +--> Model Registry
   +--> shared object storage
   +--> PostgreSQL / pgvector
   +--> approved external data sources
```

```text
zuno-ai-run
   |
   +--> Model Registry
   +--> model storage
   +--> AI Gateway / MaaS
   +--> approved RAG / MCP services
   +--> observability services
```

Shared services must not require unrestricted network access between build and run namespaces.

## Day 0 responsibilities

Day 0 automation must:

1. create `zuno-ai-platform`;
2. apply the OpenShift AI applications namespace label;
3. install OpenShift AI and prerequisite Operators;
4. configure `DSCInitialization`;
5. configure `applicationsNamespace: zuno-ai-platform`;
6. configure shared components;
7. configure Model Registry in `zuno-ai-platform`;
8. configure Workbenches to use `zuno-ai-build`;
9. create the required build and run namespaces;
10. apply base RBAC and NetworkPolicies.

## Day 1 responsibilities

Day 1 automation must deploy workloads according to lifecycle.

### Build

```text
zuno-ai-build
```

receives:

- workbenches;
- pipelines;
- training jobs;
- Spark jobs;
- Ray jobs;
- LoRA/PEFT;
- RAG ingestion;
- model evaluation.

### Run

```text
zuno-ai-run
```

receives:

- model-serving workloads;
- `InferenceService`;
- `LLMInferenceService`;
- vLLM;
- llm-d;
- inference GPU workloads.

### Shared services

Cross-lifecycle services remain in:

```text
zuno-ai-platform
```

unless explicitly required elsewhere.

## Migration

The existing OpenShift AI deployment must not be silently moved between application namespaces.

The migration sequence for a disposable Zuno environment is:

```text
Remove existing DSC
        |
        v
Remove / recreate DSCI when required
        |
        v
Reinstall or reconcile RHOAI as required
        |
        v
Create zuno-ai-platform
        |
        v
Label as application namespace
        |
        v
Configure DSCInitialization
applicationsNamespace: zuno-ai-platform
        |
        v
Create DataScienceCluster
        |
        +----------------------+
        |                      |
        v                      v
 zuno-ai-build            zuno-ai-run
 build workloads          runtime workloads
```

The migration automation must explicitly verify that no unintended OpenShift AI shared components remain in:

```text
redhat-ods-applications
```

or:

```text
zuno-ai-build
```

or:

```text
zuno-ai-run
```

## Consequences

### Positive

- Clear separation between shared AI platform, build and runtime.
- Shared components have a natural home.
- Model Registry is correctly treated as a build/run bridge rather than a build-only service.
- Better RBAC separation.
- Better NetworkPolicy separation.
- Runtime users cannot modify platform controllers.
- Build users cannot automatically modify production-style inference services.
- The architecture remains compatible with component-specific namespaces.
- Easier transition from demo architecture to production architecture.

### Negative

- Adds a dedicated `zuno-ai-platform` namespace.
- Some cross-namespace RBAC is required.
- Operators must be validated individually to determine whether they impose their own namespace.
- Migration from an existing `redhat-ods-applications` deployment can require OpenShift AI reinstallation or explicit reconciliation.
- Operational checks must validate both platform components and workload namespaces.

## Acceptance criteria

- `zuno-ai-platform` exists.
- It has `opendatahub.io/application-namespace=true`.
- `DSCInitialization.spec.applicationsNamespace` is `zuno-ai-platform`.
- Shared OpenShift AI components run in `zuno-ai-platform`, except where their Operator or CR explicitly requires another namespace.
- Model Registry uses:

```yaml
registriesNamespace: zuno-ai-platform
```

- Workbenches use:

```yaml
workbenchNamespace: zuno-ai-build
```

- Build workloads are deployed to `zuno-ai-build`.
- Runtime inference workloads are deployed to `zuno-ai-run`.
- Shared services are not arbitrarily duplicated across build and run namespaces.
- Component-specific namespaces are documented and justified.
- `make d0 check` validates platform namespace topology.
- `make d1 check` validates build and runtime workload placement.
- AI developers cannot administer `zuno-ai-platform`.
- AI runtime operators cannot modify build workloads unless explicitly authorized.

## Future evolution

The architecture can later scale to multiple build and runtime namespaces:

```text
zuno-ai-build-team-a
zuno-ai-build-team-b

zuno-ai-run-dev
zuno-ai-run-prod
```

while keeping:

```text
zuno-ai-platform
```

as the common platform layer.

The fundamental rule remains:

```text
COMMON BUILD + RUN SERVICE
          |
          v
 zuno-ai-platform

BUILD-SPECIFIC WORKLOAD
          |
          v
   zuno-ai-build

RUN-SPECIFIC WORKLOAD
          |
          v
    zuno-ai-run
```

unless the component, Operator or Custom Resource explicitly imposes another namespace.

## Related ADRs

- ADR-0047 - Manage the complete OpenShift AI prerequisite lifecycle
- ADR-0048 - Discover supported operator channels and serving runtimes at deployment time
- ADR-0056 - Restructure deployment into Day 0 / Day 1 sequencing
- ADR-0319 - Target OpenShift 4.22
- ADR-0320 - Pre-provision OpenShift users, RBAC and console favorites via Keycloak
- ADR-0321 - Delegate Kueue lifecycle to the Red Hat build of Kueue Operator
- ADR-0322 - Migrate from Llama Stack configuration to OpenShift AI OGX
- ADR-0201 - Complete the OpenShift AI MaaS governance plane integration
- ADR-0329 - Consolidate agent workloads into the shared zuno-ai-run namespace, retiring the namespace-per-agent isolation model
- [ADR-0333](0333-separate-product-managed-ai-infrastructure-from-zuno-build-run-and-shared-platform-namespaces.md) - Reaffirms this ADR's build/run workload split and extends the "product-managed infrastructure stays in its own namespace" principle to OpenShift Ingress, Gateway API and Connectivity Link/Kuadrant

## Review evidence

This ADR formalizes the namespace model around one simple architectural rule:

```text
zuno-ai-platform = everything shared across build and run
zuno-ai-build    = build-specific workloads
zuno-ai-run      = runtime-specific workloads
```

Component-specific namespaces remain valid when required by the corresponding Operator, component or Custom Resource.
