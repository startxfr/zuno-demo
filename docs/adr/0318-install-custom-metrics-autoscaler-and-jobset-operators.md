# ADR-0318: Install the Custom Metrics Autoscaler and JobSet operators as OpenShift AI prerequisites

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team

## Context

`gitops/charts/openshift-ai/values.yaml`'s `DataScienceCluster` spec now
enables `trainer`/`trainingoperator` (Kubeflow Trainer v2) and a richer
`kserve` configuration (`modelsAsService`, `wva`, `nim`) alongside
`kueue`, `ray`, `trustyai`, `aipipelines`, `mlflowoperator`,
`llamastackoperator`, `sparkoperator` and `modelregistry`. Two of these
now-enabled capabilities have real cluster-level prerequisites this
repository didn't install before this ADR, neither of which ADR-0047 named
(that ADR's list - NFD, cert-manager, Service Mesh, Connectivity Link,
LeaderWorkerSet, OGX, MaaS - predates this DSC expansion):

- **Kubeflow Trainer v2** (`trainer`/`trainingoperator`) runs distributed
  training jobs on the JobSet API (`jobset.x-k8s.io`), not raw Jobs/Pods -
  without the JobSet operator/CRD installed, `trainer`/`trainingoperator`
  cannot actually schedule a distributed training run.
- RHOAI's custom-metrics-based autoscaling for deployed models (scaling
  `InferenceService` replicas on request-rate/queue-depth rather than
  CPU/memory) is implemented via the Custom Metrics Autoscaler operator
  (Red Hat's productized KEDA build) - relevant given this DSC's expanded
  `kserve` configuration.

## Decision

Install both as new Day 0 prerequisite components,
`custom-metrics-autoscaler` and `jobset`, using the same chart +
`-d0`/`-d1` ArgoCD `Application` pair + Ansible role shape as every other
OLM operator in this repository, ordered ahead of `openshift_ai`
(alongside `connectivity_link`/`lws`, ADR-0317). Channel/catalog are
discovered from each operator's own `PackageManifest` at apply time
(ADR-0048), never hardcoded.

The two components use **different** OLM install-mode shapes, deliberately
- not a copy-paste of each other, because their CSVs don't support the
same install modes:

- **`custom-metrics-autoscaler`** follows Red Hat's documented install
  procedure: a dedicated `openshift-keda` namespace with its own
  `OwnNamespace`-scoped `OperatorGroup` (the `nfd`/`nvidia-gpu`/
  `openshift-ai` shape), plus a minimal `KedaController` operand CR
  (`spec: {}`) in that same namespace - required for the operator to
  actually deploy KEDA's metrics-apiserver/controller pods, same
  "meta-operator needs a CR" shape as `connectivity-link`'s `Kuadrant` CR.
- **`jobset`** follows the `lws`/`external-secrets` shape: a `Subscription`
  into the pre-existing `openshift-operators` namespace (`AllNamespaces`),
  no dedicated namespace/`OperatorGroup`, no operand CR.

This distinction exists because ADR-0317's original `connectivity-link`
implementation guessed the wrong install mode (`OwnNamespace` in a
dedicated namespace) for `rhcl-operator`, which turned out to only support
`AllNamespaces` - confirmed against a real cluster and fixed. Neither
`custom-metrics-autoscaler`'s nor `jobset`'s exact package name, namespace,
or install-mode support has been verified against a live cluster here
either; `custom-metrics-autoscaler`'s shape matches Red Hat's official
documented procedure (higher confidence), `jobset`'s package name/shape is
a best-known placeholder (lower confidence - it may not even be
OLM-packaged by Red Hat at all, unlike the other four operators this
repository installs) modeled on the already-proven-safe
`external-secrets`/`lws` shape as the lower-risk default.

## Consequences

`platform/openshift-ai/README.md` and `ansible/roles/openshift_ai/
README.md` gain entries for both capabilities. No DataScienceCluster spec
change - `trainer`/`trainingoperator`/`kserve` were already enabled
elsewhere; this ADR only adds their missing cluster-level prerequisites.

## Security considerations

Both Subscriptions source from whatever catalog each operator's own
`PackageManifest` reports (ADR-0048), never a hardcoded assumption. The
`KedaController` CR is minimal (`spec: {}}`) - no `ScaledObject`/
`TriggerAuthentication` or external metrics source is configured by this
ADR.

## Operational considerations

Neither operator's real OLM package name, namespace, or install-mode
support is verified against a live OpenShift AI 3.5+ catalog.
`ansible/roles/{custom_metrics_autoscaler,jobset}/tasks/install.yml`'s
`PackageManifest` lookup fails with a clear diagnostic (listing published
channels) if the guessed package name is wrong. If `jobset`'s guessed
package name doesn't exist on a given catalog at all (a real possibility -
see Decision above), that's the expected failure signal to go find the
correct package name/installation method, same as ADR-0317's precedent.
If `custom-metrics-autoscaler`'s `KedaController` CR is rejected for a
missing/invalid field (the CRD's exact required shape isn't confirmed
here), follow `gitops/charts/nvidia-gpu/README.md`'s `alm-examples`
discovery pattern instead of hand-guessing a larger spec.

## Implementation state

**Implemented (2026-08-11)**, scoped exactly as described above: operator
installation (+ minimal `KedaController` CR for
`custom-metrics-autoscaler`) only, ordered ahead of `openshift_ai`. Does
not modify ADR-0317 or ADR-0047 - this is a new, additive prerequisite
need, not a reversal of either's dispositions.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0317](0317-install-connectivity-link-and-leaderworkerset-operators.md) (the install-mode-guessing lesson this ADR's Decision applies)
