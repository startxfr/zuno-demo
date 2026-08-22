# ADR-0333: Separate product-managed AI infrastructure from Zuno build, run, and shared platform namespaces

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-22
- **Decision owners:** Zuno Demo architecture team
- **Relationship to prior ADRs:** Reaffirms and extends the `zuno-ai-platform` / `zuno-ai-build` / `zuno-ai-run` workload split from [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) (still in effect) and the decision in [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) to keep RHOAI in its default `redhat-ods-applications` namespace rather than relocating it to `zuno-ai-platform`. This ADR does not reopen either of those decisions; it generalizes the underlying rule ("product-managed infrastructure stays in its product-defined namespace") to OpenShift Ingress, Gateway API and Connectivity Link/Kuadrant, which ADR-0328/ADR-0331 did not cover.

## Context

Zuno relies on several OpenShift and Red Hat Operators to provide the AI platform, including:

- Red Hat OpenShift AI;
- OpenShift Ingress and Gateway API;
- Red Hat Connectivity Link / Kuadrant;
- Red Hat build of Kueue;
- LeaderWorkerSet;
- NVIDIA GPU Operator;
- cert-manager;
- Service Mesh and observability components.

Some of these products deploy controllers, operators, gateways, routers or other infrastructure into namespaces that are defined and managed by the corresponding product.

The current Red Hat OpenShift AI installation already uses the standard namespaces:

- `redhat-ods-operator`
- `redhat-ods-applications`

Red Hat OpenShift AI 3.5 supports selecting custom namespaces before a new OpenShift AI installation, but system namespaces of an existing deployment must not simply be renamed or relocated.

The same principle applies to OpenShift ingress infrastructure. The OpenShift Ingress Operator manages:

- `openshift-ingress-operator`
- `openshift-ingress`

and deploys router and Gateway API infrastructure there.

Zuno must therefore distinguish between:

- product-managed infrastructure, whose namespace is controlled by the product;
- Zuno-managed shared AI services, used by both build and run;
- AI build workloads;
- AI runtime workloads.

## Decision

Zuno adopts the following namespace ownership model:

```text
PRODUCT-MANAGED COMPONENT
         |
         v
Product-defined namespace
Do not relocate

ZUNO-MANAGED SHARED SERVICE
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

The general rule is:

- All Zuno-managed services shared between the AI build and runtime planes SHOULD be deployed in `zuno-ai-platform`.
- Components managed by OpenShift, Red Hat OpenShift AI, or another Operator MUST remain in their product-defined namespace whenever the supported product configuration does not explicitly allow namespace relocation.
- Namespace relocation must never be implemented by manually moving, copying, patching, or recreating Operator-managed Deployments or Pods in a Zuno namespace.

### Namespace topology

The target topology is:

```text
                         OpenShift cluster
                               |
          +--------------------+--------------------+
          |                    |                    |
          v                    v                    v
 Product-managed         Zuno shared          Zuno workloads
 infrastructure           AI platform
          |                    |               /           \
          |                    |              /             \
          v                    v             v               v

 redhat-ods-*        zuno-ai-platform   zuno-ai-build   zuno-ai-run

 openshift-ingress*
 operator-specific
 namespaces
```

More specifically:

```text
+------------------------------------------------------------+
| PRODUCT-MANAGED INFRASTRUCTURE                              |
|                                                              |
| redhat-ods-operator                                         |
| redhat-ods-applications                                     |
| openshift-ingress-operator                                  |
| openshift-ingress                                           |
| openshift-* / redhat-* Operator namespaces                  |
| other namespaces imposed by installed Operators             |
+------------------------------------------------------------+

                         manages

+------------------------------------------------------------+
| zuno-ai-platform                                            |
|                                                              |
| Zuno-managed services shared by BUILD and RUN                |
|                                                              |
| Model Registry instances                                     |
| shared AI services                                            |
| shared RAG services                                           |
| shared MCP services                                           |
| shared metadata/services                                      |
| shared Zuno AI Gateway components where namespace is free     |
| other cross-lifecycle Zuno resources                          |
+------------------------------------------------------------+
               |                              |
               v                              v
+-----------------------------+   +----------------------------+
| zuno-ai-build               |   | zuno-ai-run                |
|                              |   |                            |
| Workbenches                  |   | InferenceService           |
| SparkApplication              |   | LLMInferenceService      |
| Training jobs                  |   | vLLM / llm-d workloads |
| Ray jobs                        |   | model-serving pods   |
| Pipelines                        |   | inference GPU workloads |
| LoRA / PEFT                       |   | runtime AI workloads |
| RAG ingestion/indexing              |   |                    |
| evaluations                          |   |                    |
+-----------------------------+   +----------------------------+
```

## Red Hat OpenShift AI namespaces

### Existing RHOAI namespaces

The existing OpenShift AI deployment keeps `redhat-ods-operator` for the Red Hat OpenShift AI Operator, and `redhat-ods-applications` for OpenShift AI managed application/control-plane components.

The Zuno architecture MUST NOT attempt to replace `redhat-ods-applications` with `zuno-ai-platform` on the existing installation.

The `DataScienceCluster` remains cluster-scoped:

```yaml
apiVersion: datasciencecluster.opendatahub.io/v2
kind: DataScienceCluster
metadata:
  name: zuno-dsc
```

Controllers and services whose lifecycle is managed by RHOAI remain where RHOAI deploys them.

Typical examples include:

```text
redhat-ods-applications
|
+-- KServe controllers
+-- Ray controller
+-- Training controllers
+-- Spark controller
+-- Dashboard
+-- OGX-managed platform components
+-- TrustyAI controllers
+-- Data Science Pipeline controllers
+-- other DSC-managed components
```

These components are considered part of the Zuno architecture but not owned by Zuno at the namespace-placement level.

### Zuno shared AI platform namespace

The namespace `zuno-ai-platform` is reserved for components that meet both conditions:

- they are shared by the BUILD and RUN lifecycle;
- Zuno is free to select their namespace.

Examples include:

- Model Registry instances when `registriesNamespace` is configurable;
- shared RAG APIs and services;
- shared MCP infrastructure;
- shared metadata services;
- Zuno-specific AI Gateway components;
- shared contextualization or routing services;
- other Zuno-owned cross-lifecycle services.

The existence of `zuno-ai-platform` does not imply that every shared product component must be relocated there.

The namespace rule is therefore:

```text
                   Shared component?
                         |
                         v
                        yes
                         |
                 Zuno controls its
                   namespace?
                    /       \
                  yes        no
                   |          |
                   v          v
        zuno-ai-platform    product
                           namespace
```

### Model Registry

The Model Registry is a cross-lifecycle capability:

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

Because its registry namespace is configurable, Zuno deploys Model Registry instances into `zuno-ai-platform`. For example:

```yaml
spec:
  components:
    modelregistry:
      managementState: Managed
      registriesNamespace: zuno-ai-platform
```

The Operator/controller responsible for managing Model Registry remains in its RHOAI-managed namespace.

This illustrates the intended model:

```text
RHOAI controller
redhat-ods-applications
        |
        | manages
        v
Model Registry instance
zuno-ai-platform
```

### AI build namespace

The namespace `zuno-ai-build` contains workloads whose purpose is to create, prepare, train, evaluate or enrich AI assets.

Examples include: Workbenches; notebooks; `SparkApplication`; Ray training workloads; distributed training jobs; AI Pipeline runs; LoRA; PEFT; model evaluation; dataset preparation; feature preparation; RAG ingestion; chunking; embedding generation; vector indexing.

For example:

```yaml
spec:
  components:
    workbenches:
      managementState: Managed
      workbenchNamespace: zuno-ai-build
```

and:

```yaml
apiVersion: sparkoperator.k8s.io/v1beta2
kind: SparkApplication
metadata:
  name: zuno-rag-ingestion
  namespace: zuno-ai-build
```

The Spark Operator itself remains in the namespace selected by OpenShift AI.

### AI runtime namespace

The namespace `zuno-ai-run` contains workloads whose purpose is to serve or execute AI models.

Examples include: `InferenceService`; `LLMInferenceService`; vLLM workloads; llm-d workloads; model-serving pods; inference GPU workers; runtime autoscaling resources; inference-specific TrustyAI resources when namespace-scoped; agent runtime services that are exclusively part of inference.

Conceptually:

```text
KServe / llm-d controllers
product-managed namespace
          |
          | manages
          v
LLMInferenceService
zuno-ai-run
          |
          v
Model-serving pods
zuno-ai-run
```

## OpenShift ingress infrastructure

OpenShift ingress infrastructure is product-managed and MUST remain in the namespaces controlled by the OpenShift Ingress Operator.

The main namespaces are `openshift-ingress-operator` and `openshift-ingress`.

An `IngressController` is created in `openshift-ingress-operator`. For example:

```yaml
apiVersion: operator.openshift.io/v1
kind: IngressController
metadata:
  name: zuno
  namespace: openshift-ingress-operator
```

The resulting router infrastructure remains in `openshift-ingress`, even for an additional Zuno-specific `IngressController`.

OpenShift documentation shows custom `IngressController` resources in `openshift-ingress-operator` and their generated router Services in `openshift-ingress`.

Therefore Zuno MUST NOT attempt to move `router-default` / `router-*` pods or Services into `zuno-ai-platform` or any other `zuno-*` namespace.

### Dedicated Zuno ingress

Zuno MAY create a dedicated `IngressController` when isolation from the default cluster ingress is required. For example:

```yaml
apiVersion: operator.openshift.io/v1
kind: IngressController
metadata:
  name: zuno
  namespace: openshift-ingress-operator
spec:
  domain: zuno.apps.example.com

  namespaceSelector:
    matchLabels:
      zuno.io/ingress: "true"

  nodePlacement:
    nodeSelector:
      matchLabels:
        node-role.kubernetes.io/worker: ""
```

This provides isolation based on: domain; selected application namespaces; selected nodes; load-balancer configuration; router replicas.

It does not relocate the router into the application namespace. The distinction is:

```text
namespaceSelector
      |
      v
Which application namespaces
can use the ingress

NOT

Where the router pods
are deployed
```

## OpenShift Gateway API

When using the OpenShift built-in Gateway API implementation:

```yaml
spec:
  controllerName: openshift.io/gateway-controller/v1
```

the OpenShift Ingress Operator manages the Gateway API infrastructure.

OpenShift 4.22 installs a lightweight Istio control plane for this implementation in `openshift-ingress` when the OpenShift Gateway API implementation is enabled.

The corresponding infrastructure MUST remain product-managed.

For the built-in `openshift-default` GatewayClass, Zuno follows the OpenShift-supported topology and keeps shared Gateway resources in `openshift-ingress` unless Red Hat documentation for the precise OpenShift/Connectivity Link combination explicitly supports another placement.

For example:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: zuno-ai-gateway
  namespace: openshift-ingress
spec:
  gatewayClassName: openshift-default
```

Application `HTTPRoute` resources remain in their application namespaces (`zuno-ai-run`, `zuno-ai-platform`, other zuno application namespaces) and reference the shared Gateway. For example:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: zuno-model-api
  namespace: zuno-ai-run
spec:
  parentRefs:
    - name: zuno-ai-gateway
      namespace: openshift-ingress
```

OpenShift explicitly supports a shared Gateway with routes located in separate namespaces.

## Connectivity Link and Kuadrant

Connectivity Link adds governance capabilities around Gateway API, including: authentication; authorization; rate limiting; TLS policy; DNS policy.

Connectivity Link documentation supports defining a Gateway namespace through `KUADRANT_GATEWAY_NS`, and policy resources are generally associated with the namespace of the Gateway they target.

However, namespace placement must also respect the requirements of the selected Gateway implementation.

For Zuno, when Connectivity Link operates against `GatewayClass: openshift-default`, the OpenShift 4.22 Gateway API topology takes precedence for infrastructure placement.

Therefore Zuno MUST NOT assume that a Gateway or its policies can automatically be moved into `zuno-ai-platform`.

The supported placement must be validated against the combination of OpenShift version + GatewayClass implementation + Connectivity Link version before changing namespace placement.

For the current architecture, the conservative supported model is:

```text
openshift-ingress
|
+-- shared OpenShift Gateway
+-- Gateway infrastructure
+-- policies that must colocate with that Gateway

zuno-ai-run
|
+-- HTTPRoute
+-- inference services

zuno-ai-platform
|
+-- shared Zuno AI services
+-- services exposed through HTTPRoute
```

## Gateway and route ownership

Namespace ownership and resource ownership are separate concepts.

A Zuno-managed object can legitimately reside in a product namespace when the underlying product requires that placement. For example:

| | |
|---|---|
| Resource | `zuno-ai-gateway` |
| Owned/configured by | Zuno GitOps |
| Namespace | `openshift-ingress` |
| Lifecycle | managed declaratively by Zuno |

Therefore: a resource being stored in `openshift-ingress` does not make it unmanaged by Zuno.

Zuno GitOps MAY manage selected resources in product namespaces when this is the supported integration mechanism. It MUST NOT manage underlying Operator-generated objects directly.

## Resources that must not be moved

The following objects MUST remain under control of their respective Operators:

| Resource | Namespace |
|---|---|
| Red Hat OpenShift AI Operator | `redhat-ods-operator` |
| RHOAI platform controllers | `redhat-ods-applications` |
| Ingress Operator | `openshift-ingress-operator` |
| IngressController CRs | `openshift-ingress-operator` |
| HAProxy router pods | `openshift-ingress` |
| Router Services | `openshift-ingress` |
| OpenShift Gateway API lightweight Istio control plane | `openshift-ingress` |
| Operator-managed components with fixed namespace | Product-defined namespace |

Pods or Deployments generated by these Operators MUST NOT be manually copied to or recreated in a `zuno-*` namespace.

## Resources preferred in zuno-ai-platform

When their namespace is under Zuno control, the following types of shared resources SHOULD use `zuno-ai-platform`:

- Model Registry instances;
- shared MCP Gateway and services;
- shared RAG APIs;
- Zuno AI orchestration services;
- shared model/context metadata APIs;
- AI Gateway services owned directly by Zuno;
- shared configuration services;
- other BUILD/RUN cross-cutting Zuno workloads.

## Namespace decision algorithm

Every new component must be evaluated using the following sequence:

```text
Is the component managed by an Operator?
             |
        +----+----+
        |         |
       yes        no
        |         |
        v         |
Does the product |
define/impose    |
its namespace?   |
   |             |
 +-+-+           |
 |   |           |
yes  no          |
 |    |          |
 v    +----------+
product          |
namespace        v
          Shared BUILD/RUN?
             /       \
           yes        no
            |          |
            v          v
    zuno-ai-platform   Build-specific?
                       /          \
                     yes          no
                      |            |
                      v            v
               zuno-ai-build  zuno-ai-run
```

Any exception must be documented either in the component's implementation documentation, in an existing ADR, or through a dedicated ADR if architecturally significant.

## Security consequences

This architecture provides clear authorization boundaries.

### Product namespaces

Examples: `redhat-ods-applications`, `openshift-ingress`, `openshift-ingress-operator`.

Only cluster administrators, relevant Operators, and explicitly authorized platform automation may modify resources there.

Zuno application users MUST NOT receive general edit permissions on those namespaces.

### zuno-ai-platform

Restricted to platform administrators and identities responsible for shared AI services.

### zuno-ai-build

Accessible to AI development roles according to ADR-0320. Typical permissions cover: workbenches; training; Spark; Ray; pipelines; data preparation.

### zuno-ai-run

More restricted because changes affect model-serving and production-style inference endpoints.

## GitOps model

All Zuno-owned declarative resources remain GitOps-managed even when they must reside in product namespaces. For example:

```text
Git repository
      |
      +--> Gateway
      |    namespace: openshift-ingress
      |
      +--> HTTPRoute
      |    namespace: zuno-ai-run
      |
      +--> ModelRegistry
      |    namespace: zuno-ai-platform
      |
      +--> LLMInferenceService
           namespace: zuno-ai-run
```

The GitOps repository MUST distinguish Zuno-owned declarative resources from Operator-generated resources.

Operator-generated Deployments, Pods, Services or internal configuration MUST NOT be copied into Git and independently reconciled.

## Operational checks

### Day 0

`make d0 check` SHOULD validate:

- `redhat-ods-operator` exists and is healthy;
- `redhat-ods-applications` exists and is healthy;
- no attempt has been made to replace the existing RHOAI applications namespace;
- `openshift-ingress-operator` is healthy;
- `openshift-ingress` is healthy;
- required product-specific Operator namespaces exist;
- `zuno-ai-platform` exists;
- `zuno-ai-build` exists;
- `zuno-ai-run` exists;
- shared Zuno services are placed according to this ADR.

### Day 1

`make d1 check` SHOULD validate:

- build workloads are in `zuno-ai-build`;
- inference workloads are in `zuno-ai-run`;
- Model Registry instances are in `zuno-ai-platform`;
- shared Zuno services are in `zuno-ai-platform`;
- HTTPRoutes reference the expected Gateway;
- no Operator-managed Pods have been manually duplicated into `zuno-*`;
- ingress and Gateway API components remain healthy.

## Consequences

### Positive

- Respects Red Hat-supported namespace topology.
- Avoids unsupported relocation of Operator-managed components.
- Clearly separates product infrastructure from Zuno workloads.
- Preserves a meaningful `zuno-ai-platform` namespace.
- Separates BUILD and RUN responsibilities.
- Allows Zuno to manage Gateway and other resources through GitOps without pretending to own the underlying product infrastructure.
- Makes upgrades safer because Operators remain responsible for their own resources.
- Prevents `zuno-ai-platform` from becoming an artificial replacement for Red Hat system namespaces.

### Negative

- The architecture cannot be represented entirely with `zuno-*` namespaces.
- Some Zuno-owned GitOps resources may legitimately live in `openshift-*` namespaces.
- RBAC for Argo CD/automation must permit carefully controlled changes in selected product namespaces.
- Namespace placement varies according to the support model of each Operator.
- Gateway/Connectivity Link placement must be validated when product versions change.

## Acceptance criteria

ADR-0333 is implemented when:

- existing `redhat-ods-operator` and `redhat-ods-applications` namespaces are preserved;
- no attempt is made to relocate RHOAI controllers into `zuno-ai-platform`;
- `zuno-ai-platform` is used for Zuno-managed BUILD/RUN shared services;
- Model Registry instances use `zuno-ai-platform` where supported;
- Workbenches and build workloads use `zuno-ai-build`;
- inference workloads use `zuno-ai-run`;
- OpenShift router pods remain in `openshift-ingress`;
- OpenShift Gateway API infrastructure remains in `openshift-ingress`;
- additional IngressController resources are created in `openshift-ingress-operator`;
- `namespaceSelector` is used for route isolation rather than attempting router relocation;
- Gateway and Kuadrant resource placement follows the supported namespace requirements of the selected Gateway implementation;
- no Operator-generated Deployment or Pod is duplicated into a Zuno namespace;
- GitOps distinguishes Zuno-owned resources from Operator-generated resources;
- Day 0 and Day 1 checks validate the namespace topology.

## Related ADRs

- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md) - Manage the complete OpenShift AI prerequisite lifecycle
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md) - Discover supported operator channels and serving runtimes at deployment time
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) - Restructure deployment into Day 0 / Day 1 sequencing
- [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md) - Complete the OpenShift AI MaaS governance plane integration
- [ADR-0319](0319-target-openshift-4-22.md) - Target OpenShift 4.22
- [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md) - Pre-provision OpenShift users, RBAC and console favorites via Keycloak
- [ADR-0321](0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md) - Delegate Kueue lifecycle to the Red Hat build of Kueue Operator
- [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md) - Migrate from Llama Stack configuration to OpenShift AI OGX
- [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) - Separate the OpenShift AI control plane from AI build and run workload namespaces (build/run split reaffirmed here)
- [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) - Revert OpenShift AI to the default applications namespace (reaffirmed here, extended to ingress/Gateway API/Connectivity Link)

## References

The decision is based on the supported namespace and resource-placement models documented for:

- Red Hat OpenShift AI Self-Managed 3.5, which documents `redhat-ods-operator`, `redhat-ods-applications`, and the requirement not to rename existing system namespaces.
- OpenShift Container Platform 4.22 Ingress, where custom `IngressController` resources live in `openshift-ingress-operator` and generated router infrastructure remains in `openshift-ingress`.
- OpenShift Container Platform 4.22 Gateway API, whose built-in implementation installs its lightweight Istio control plane in `openshift-ingress` and documents shared Gateway topologies across application namespaces.
- Red Hat Connectivity Link, which defines Gateway-scoped authentication, TLS, DNS and rate-limit policies and supports explicit Gateway namespace configuration subject to the selected Gateway implementation.

## Architectural summary

```text
PRODUCT MANAGED?
      |
     YES
      |
      v
KEEP PRODUCT NAMESPACE
redhat-ods-*
openshift-ingress*
operator namespaces


ZUNO MANAGED?
      |
      +------ shared ------> zuno-ai-platform
      |
      +------ build -------> zuno-ai-build
      |
      +------ run ---------> zuno-ai-run
```

The namespace name expresses ownership and lifecycle, but never overrides the namespace requirements of the underlying supported product.
