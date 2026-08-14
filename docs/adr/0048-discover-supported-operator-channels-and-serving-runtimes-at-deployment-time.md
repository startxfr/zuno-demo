# ADR-0048: Discover supported operator channels and serving runtimes at deployment time

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The repository contains hard-coded assumptions such as `quay.io/modh/vllm:rhoai-2.16-cuda`, `latest` channels and comments indicating that some tags were not verified. OpenShift AI 3.5 should use serving runtimes and operator channels that are actually available in the installed cluster/catalog.

## Decision

Precheck the PackageManifest/CatalogSource and OpenShift AI resources before configuration. Select approved operator channels and `ClusterServingRuntime`/serving images exposed by the installed OpenShift AI version instead of embedding unverified runtime image tags. Fail with a clear diagnostic when the expected capability is unavailable.

## Consequences

The demo follows the installed product rather than stale hard-coded image assumptions, reducing upgrade and compatibility risk.

## Security considerations

Only approved registries and signed images may be selected. Runtime discovery must not silently switch to an untrusted image.

## Operational considerations

Add precheck output showing selected channels, operator versions, serving runtimes and GPU compatibility before model deployment.

## Implementation state

**Implemented (2026-08-05)** for the two hardcoded assumptions this ADR's Context names.

- **Serving-runtime image**: `ansible/roles/models/tasks/discover_vllm_image.yml` (shared, included by both `precheck.yml` and `install.yml`, since separate `ansible-playbook` runs don't share facts) lists the `Template` objects OpenShift AI publishes in `redhat-ods-applications` (RHOAI's applications namespace since the ADR-0331 revert), selects those naming "vllm", prefers the CUDA-flavored one among them (this deployment's `ServingRuntime` requests `nvidia.com/gpu` - see `gitops/charts/models/values.yaml`), extracts the image from its embedded `ServingRuntime`/`ClusterServingRuntime` object - resolving a `${PARAM}`-style Template parameter reference if the image field is parameterized - and fails with a clear diagnostic (listing every template found) if discovery can't resolve a concrete image, rather than silently falling back to the old hardcoded guess or to a non-CUDA runtime. `ansible/tasks/apply_gitops_app.yml` gained a generic `gitops_app_extra_helm_values` mechanism so the discovered value reaches the chart without hand-editing checked-in GitOps config. The old hardcoded value in `gitops/charts/models/values.yaml` is kept only as a `helm template`/standalone-testing fallback, never trusted for a real deploy. An operator who already knows the correct image can bypass discovery with an explicit `models_vllm_image_override` - a conscious override, never a silent one.
- This resolution algorithm (Template selection, object extraction, both literal- and parameterized-image paths, and the no-default-value failure path) was verified against synthetic fixture data via a standalone local `ansible-playbook` run; the `kubernetes.core.k8s_info` discovery calls themselves were not exercised against a real cluster (none exists in this environment).
- **Operator channel**: `ansible/roles/openshift_ai/tasks/prepare.yml` now reads the `rhods-operator` `PackageManifest`'s published channels and selects the one matching the `3.5` family, falling back to the manifest's own `defaultChannel`, and failing with a clear diagnostic (listing every published channel) if neither is available.
- Security: "only approved registries" is satisfied by construction, since discovery only ever reads Templates the already-trusted `rhods-operator` (installed only from `redhat-operators`, ADR-0047) published - never an arbitrary external source. The "never silent" half of "must not silently switch to an untrusted image" is implemented (every failure path fails loudly); actual image *signature* verification at discovery time is **not implemented** - that needs a cluster-side policy this Ansible role has no mechanism to enforce, and connects more naturally to ADR-0115's signing/verification scope - flagged as an honest gap.
- Operational: both discovery paths end in an `ansible.builtin.debug` summary naming exactly what was selected and why (matched channel plus every published alternative; resolved image plus its source Template, or the explicit override used instead).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0002](0002-use-openshift-4-20-and-openshift-ai-3-5-ea2-for-the-mvp.md)
- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md)
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md)
