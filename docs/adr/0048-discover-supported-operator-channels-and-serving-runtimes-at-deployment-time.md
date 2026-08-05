# ADR-0048: Discover supported operator channels and serving runtimes at deployment time

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The repository contains hard-coded assumptions such as `quay.io/modh/vllm:rhoai-2.16-cuda`, `latest` channels and comments indicating that some tags were not verified. OpenShift AI 3.5 should use serving runtimes and operator channels that are actually available in the installed cluster/catalog.

## Decision

Precheck the PackageManifest/CatalogSource and OpenShift AI resources before configuration. Select approved operator channels and `ClusterServingRuntime`/serving images exposed by the installed OpenShift AI version instead of embedding unverified runtime image tags. Fail with a clear diagnostic when the expected capability is unavailable.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The demo follows the installed product rather than stale hard-coded image assumptions, reducing upgrade and compatibility risk.

## Security considerations

Only approved registries and signed images may be selected. Runtime discovery must not silently switch to an untrusted image.

## Operational considerations

Add precheck output showing selected channels, operator versions, serving runtimes and GPU compatibility before model deployment.

## Implementation state

**Implemented (2026-08-05)** for the two hardcoded assumptions this ADR's
own Context names by name.

**Serving-runtime image** (`quay.io/modh/vllm:rhoai-2.16-cuda`):
`ansible/roles/models/tasks/discover_vllm_image.yml` (a shared task,
included by both `tasks/precheck.yml` for early visibility and
`tasks/configure.yml`, since separate `ansible-playbook` runs don't share
facts) lists the `Template` objects OpenShift AI publishes in
`redhat-ods-applications` (the same catalog the dashboard's own "Serving
runtimes" page reads from), selects the one naming "vllm", extracts the
image from its embedded `ServingRuntime`/`ClusterServingRuntime` object -
resolving a `${PARAM}`-style Template parameter reference against that
Template's own `parameters` list if the image field is parameterized
rather than literal - and fails with a clear diagnostic (listing every
template actually found) if discovery can't resolve a concrete image at
any step, rather than silently falling back to the old hardcoded guess.
`ansible/tasks/apply_gitops_app.yml` gained a generic
`gitops_app_extra_helm_values` mechanism so the discovered value reaches
the chart without hand-editing checked-in GitOps config.
`gitops/charts/models/values.yaml`'s old hardcoded value is kept only as
a `helm template`/standalone-testing fallback, explicitly documented as
never trusted for a real deploy. An operator who already knows the
correct image can bypass discovery with an explicit
`models_vllm_image_override` variable - a conscious override, never a
silent one (Security considerations: "must not silently switch to an
untrusted image").

This whole resolution algorithm (Template selection, object extraction,
both the literal-image and parameterized-image paths, and the
no-default-value failure path) was verified against synthetic fixture
data via a standalone local `ansible-playbook` run (no live cluster
needed for pure Jinja/fact logic) before being committed - all paths
behaved correctly. Discovery itself (the `kubernetes.core.k8s_info` calls)
was not exercised against a real cluster - no live OpenShift AI
installation exists in this environment, the same constraint as every
other cluster-dependent role in this repository.

**Operator channel** (`eus-3.5`, previously flagged as an unverified
guess): `ansible/roles/openshift_ai/tasks/prepare.yml` now reads the
`rhods-operator` `PackageManifest`'s published channels and selects the
one matching the `3.5` family, falling back to the manifest's own
`defaultChannel`, and failing with a clear diagnostic (listing every
published channel) if neither is available.

Security considerations: "Only approved registries... may be selected" -
satisfied by construction, since discovery only ever reads Templates the
already-trusted `rhods-operator` (itself installed only from the
`redhat-operators` catalog, ADR-0047) published into
`redhat-ods-applications` - never an arbitrary external source. "...and
signed images" and "runtime discovery must not silently switch to an
untrusted image" - the *never silent* half is implemented (every failure
path above fails loudly rather than guessing); actual image *signature*
verification at discovery time is **not implemented** - that would need a
cluster-side policy (e.g. Sigstore Policy Controller or an
ImageContentSourcePolicy-based check) this ansible role has no mechanism
to enforce, and connects more naturally to ADR-0051's own signing/
verification scope than to this ADR's discovery mechanism - flagged here
as an honest gap, not silently assumed covered.

Operational considerations ("Add precheck output showing selected
channels, operator versions, serving runtimes... before model
deployment"): both discovery paths above end in an
`ansible.builtin.debug` summary naming exactly what was selected and why
(the matched channel plus every published alternative; the resolved image
plus the Template it came from, or the explicit override used instead).

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0002
- ADR-0019
- ADR-0047
- ADR-0051

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
