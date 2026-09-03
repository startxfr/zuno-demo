# ADR-0321: Delegate Kueue lifecycle to the Red Hat build of Kueue Operator

- **Status:** Implemented - see `gitops/charts/kueue/` (Subscription + operand), `gitops/apps/kueue/application-{d0,d1}.yaml`.
- **Target:** v0
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

The OpenShift AI `DataScienceCluster` currently declares Kueue queue names but the repository does not install the Red Hat build of Kueue Operator as a Day 0 dependency and does not explicitly set the supported external-management state.

Red Hat OpenShift AI 3.5 documents the Red Hat build of Kueue Operator as the component that manages quotas and queueing for distributed workloads. The supported OpenShift AI integration uses `spec.components.kueue.managementState: Unmanaged`, allowing the dedicated Red Hat operator to own the Kueue lifecycle. The OpenShift AI documentation also lists cert-manager as a prerequisite; cert-manager is already part of Zuno Day 0.

The repository enables Ray, training components and other OpenShift AI capabilities that can consume Kueue, so Kueue must be installed and reconciled explicitly instead of being left as an implicit dependency.

## Decision

Install the **Red Hat build of Kueue Operator** as a first-class Day 0 platform component before the OpenShift AI Day 1 `DataScienceCluster` is reconciled.

The Zuno `DataScienceCluster` must use:

```yaml
spec:
  components:
    kueue:
      managementState: Unmanaged
      defaultClusterQueueName: default
      defaultLocalQueueName: default
```

The operator lifecycle follows the existing Day 0 pattern used for OpenShift AI prerequisites:

- discover the supported OLM package/channel from the target cluster rather than hard-code an unverified channel;
- install Namespace/OperatorGroup/Subscription through Argo CD-managed resources;
- wait for the operator and Kueue CRDs/controller to become ready before applying dependent OpenShift AI configuration;
- expose `check`, `install` and `uninstall` behavior through the Make/Ansible command-dispatch contract;
- configure `ResourceFlavor`, `ClusterQueue` and `LocalQueue` resources only where Zuno actually requires quota/scheduling policy, rather than coupling those policies to operator installation.

## Consequences

Kueue lifecycle ownership becomes explicit and aligned with the current Red Hat product architecture. Distributed training/model-serving capabilities can use a supported queue-management path without controller ownership ambiguity.

This adds another Day 0 operator dependency and requires queue/quota configuration to be validated against the actual cluster accelerator topology.

## Security considerations

Kueue must not become an authorization mechanism for agent/data access. It controls workload admission and resource quota only. Namespace/RBAC, agent entitlement and C1/C2/C3 policy remain governed by their existing ADRs.

The operator must be sourced from the Red Hat catalog path approved by the repository's operator-supply-chain policy.

## Operational considerations

The Day 0 check must verify at minimum:

- Red Hat build of Kueue Operator subscription/CSV health;
- Kueue controller availability;
- `DataScienceCluster` Kueue integration readiness;
- absence of a conflicting embedded Kueue controller;
- existence/readiness of any Zuno-required `ClusterQueue`/`LocalQueue` resources.

Queue resource definitions must account for GPU `ResourceFlavor` and quotas before distributed training or queued model workloads are enabled.

## Acceptance criteria

- The repository installs the Red Hat build of Kueue Operator through the standard Day 0 GitOps/Ansible lifecycle.
- `DataScienceCluster.spec.components.kueue.managementState` is explicitly `Unmanaged`.
- `make d0 check` validates the operator and `make d1 check` validates OpenShift AI/Kueue integration.
- A queued test workload can be admitted through a configured `LocalQueue` without any duplicate Kueue-controller conflict.

## References

- Red Hat OpenShift AI Self-Managed 3.5, **Working with distributed workloads**.
- Red Hat OpenShift AI documentation, **Managing workloads with Kueue** and migration to the Red Hat build of Kueue Operator.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0002](0002-use-openshift-4-20-and-openshift-ai-3-5-for-the-mvp.md)
- [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md)
- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0318](0318-install-custom-metrics-autoscaler-and-jobset-operators.md)
