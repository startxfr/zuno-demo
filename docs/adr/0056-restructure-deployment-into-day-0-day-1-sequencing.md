# ADR-0056: Restructure deployment into Day 0 / Day 1 sequencing

- **Status:** To be implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0003 established Ansible and `make` as the deployment entry point, with a two-level `make <verb> [component]` dispatch (`precheck`/`prepare`/`configure`/`install`/`check`) that has carried this repository through nine phases of ADR implementation. Real-cluster use of that interface (fixing CloudNativePG's and then Crunchy Postgres Operator's catalog/channel discovery) surfaced that the interface doesn't express two things operators actually need: a distinct, checkable "is the cluster ready at all" milestone before "is the platform running" (today both are interleaved across `precheck`/`prepare`/`configure`/`install`), and a uniform three-verb lifecycle applied consistently to every component (today some components, like namespace creation, only exist implicitly inside another component's `configure` step, with no independent check/install/configure of their own).

## Decision

Restructure the deployment interface into two named stages:

- **Day 0** - every cluster-level prerequisite needed before the Zuno AI platform can be installed at all: AdminContext (PriorityClass/StorageClass/ClusterRoleBinding), Namespaces, ArgoCD, Vault, Keycloak, NFD, NVIDIA GPU, External Secrets, Observability, PostgreSQL, SMTP, and OpenShift AI (now including the DataScienceCluster, merging the former separate `datascience` role). Each Day 0 component gets a uniform `check` / `install` / `configure` lifecycle, plus a convenience `all` that runs all three in sequence.
- **Day 1** - building the platform's own component images (`build`: `mcp`, `rag`, `agent`, via native OpenShift `BuildConfig`/`ImageStream`, no new operator dependency) and running the platform itself (`run`: `llm`, `rag`, `mcp`, `agents`, reusing each component's existing configuration logic unchanged).

`make` gains a 3-level dispatch: `make day0|d0 <check|install|configure|all> [component]` and `make day1|d1 <check|build|configure|run|all> [component]`, extending the `$(word N,$(MAKECMDGOALS))` pattern the Makefile already uses for two-level dispatch. The old `precheck`/`prepare`/`configure`/`install`/`check` top-level targets are removed - `day0`/`d0`/`day1`/`d1` become the only interface.

This also splits the shared `zuno-ai` namespace into `zuno-ai-run` (workloads) and `zuno-ai-build` (in-cluster image builds), so a compromised or misbehaving build never shares a namespace boundary with running workloads.

## Alternatives considered

- Keep the current two-level `precheck`/`prepare`/`configure`/`install`/`check` interface unchanged and rely on documentation to explain sequencing. Rejected because real-cluster operation already showed the missing Day 0/Day 1 distinction and the inconsistent per-component verb coverage cause real confusion, not just a naming preference.
- Add `day0`/`day1` as a new interface alongside the old one (both keep working). Rejected per an explicit operator decision: maintaining two parallel dispatch surfaces for the same underlying roles would double the long-term maintenance burden for no lasting benefit once operators retrain their muscle memory once.
- Use Tekton/OpenShift Pipelines for Day 1's build mechanism. Rejected per an explicit operator decision: native `BuildConfig`/`ImageStream` needs no new operator dependency, keeping Day 0's already-large prerequisite list from growing further for a demo-scale platform.

## Consequences

Operators get an explicit, checkable "cluster ready" milestone distinct from "platform running," and every Day 0 component gets the same three-verb lifecycle instead of an inconsistent subset. The `zuno-ai-run` split adds one more namespace and its associated NetworkPolicy/RBAC surface to reason about. Removing the old top-level targets is a breaking change to any existing muscle memory or external scripts invoking `make precheck`/`prepare`/`configure`/`install`/`check` directly.

## Security considerations

The `zuno-ai-run`/`zuno-ai-build` split narrows the blast radius of a compromised build (build-time supply-chain risk, ADR-0051) so it cannot directly reach running workload namespaces. Cross-namespace image pulls from `zuno-ai-build` into `zuno-ai-run` are granted via a scoped `system:image-puller` RoleBinding, not a broader namespace-wide trust relationship. AdminContext's PriorityClasses/StorageClass check/ClusterRoleBinding consolidation must not silently grant broader cluster-admin-equivalent access than the single existing ArgoCD application-controller binding already requires.

## Operational considerations

`make day0 all` / `make d0 all` (no component) must be able to bring a bare cluster to "platform-installable" state in one command, matching today's `make prepare && make configure` two-step equivalent. `make day1 build <component>` must fail loudly (not silently skip) if the corresponding `zuno-ai-build` `BuildConfig` doesn't reach `status.phase: Complete`.

## Implementation state

This ADR records an agreed architectural change. **No implementation is claimed by this ADR.** The status remains `To be implemented` until the Makefile restructuring, the new `admin_context`/`namespaces` roles, the `datascience`→`openshift_ai` merge, the `zuno-ai`→`zuno-ai-run`/`zuno-ai-build` split, and the Day 1 build mechanism all exist and are verified, per this repository's standing convention of only marking an ADR `Implemented` once code proves the decision is in effect.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0003
- ADR-0023
- ADR-0037
- ADR-0047
- ADR-0048
- ADR-0051

## Review evidence

This decision is grounded in real-cluster operational friction discovered this session (CloudNativePG and Crunchy Postgres Operator catalog/channel/package-name mismatches) plus explicit operator requirements for a Day 0/Day 1 deployment split, a uniform per-component check/install/configure lifecycle, and a build/run namespace separation.
