# ADR-0056: Restructure deployment into Day 0 / Day 1 sequencing

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0003 established Ansible and `make` as the deployment entry point, with a two-level `make <verb> [component]` dispatch (`precheck`/`prepare`/`configure`/`install`/`check`) that has carried this repository through nine phases of ADR implementation. Real-cluster use of that interface (fixing CloudNativePG's and then Crunchy Postgres Operator's catalog/channel discovery) surfaced that the interface doesn't express two things operators actually need: a distinct, checkable "is the cluster ready at all" milestone before "is the platform running" (today both are interleaved across `precheck`/`prepare`/`configure`/`install`), and a uniform three-verb lifecycle applied consistently to every component (today some components, like namespace creation, only exist implicitly inside another component's `configure` step, with no independent check/install/configure of their own).

## Decision

Restructure the deployment interface into two named stages:

- **Day 0** - every cluster-level prerequisite needed before the Zuno AI platform can be installed at all: AdminContext (PriorityClass/StorageClass/ClusterRoleBinding), Namespaces, ArgoCD, Vault, Keycloak, NFD, NVIDIA GPU, External Secrets, Observability, PostgreSQL, SMTP, and OpenShift AI (now including the DataScienceCluster, merging the former separate `datascience` role). Each Day 0 component gets a uniform `check` / `install` / `configure` lifecycle, plus a convenience `all` that runs all three in sequence.
- **Day 1** - building the platform's own component images (`build`: `mcp`, `rag`, `agent`, via native OpenShift `BuildConfig`/`ImageStream`, no new operator dependency) and running the platform itself (`run`: `llm`, `rag`, `mcp`, `agents`, plus `models`/`sql_schema`/`mlops` - broader than this decision's original `run` list, since those three have no other trigger in this repository and dropping them would be a functional regression, not just a naming choice - reusing each component's existing configuration logic unchanged).

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

**Implemented (2026-08-05)**, landed as four separate commits: the ADR itself; the Day 0 restructuring (new roles, new playbooks, Makefile `day0`/`d0` dispatch, every operator-facing doc/fail-message reference to the old command names); the `zuno-ai`→`zuno-ai-run`/`zuno-ai-build` rename, deliberately isolated so a mistake in a 59-file mechanical rename is easy to bisect/revert independently; and the Day 1 build mechanism plus Makefile `day1`/`d1` dispatch.

- **Day 0**: `admin_context` (new role - `check` verifies cluster API reachability; `install` verifies at least one `StorageClass` exists (discover-only) and applies two `PriorityClass` objects; `configure` re-applies the PriorityClasses and non-fatally reports on `argocd`'s `ClusterRoleBinding`, since `admin_context` runs before `argocd` and that binding legitimately doesn't exist yet the first time). `namespaces` (new role, moved out of `agents` - `check` reads the expected namespace list directly from `gitops/charts/namespaces/values.yaml`, never a hardcoded duplicate). `openshift_ai` absorbed the former `datascience` role's namespace-creation and GPU `ResourceQuota` tasks. The formerly separate `api` role was retired into `agents` (once namespace-apply moved out of `agents`'s `configure.yml`, it was doing exactly what `api` did).
- **Day 1**: `run` components (`llm`, `models`, `sql_schema`, `rag`, `mcp`, `agents`, `mlops`) reuse each role's existing `precheck.yml`/`configure.yml` unchanged - `configure` and `run` are literal aliases. `day1_check.yml` special-cases `agents` to run `tasks_from: check` (the real ADR-0053 acceptance/security gate) rather than `tasks_from: precheck`, so that capability wasn't silently lost in the rename.
- **Day 1 build**: new `ansible/tasks/apply_openshift_build.yml` and roles `ansible/roles/{mcp,rag,agent}_build` apply an `ImageStream` + git-source `BuildConfig` (Docker strategy, `ConfigChange` trigger, no new operator dependency) per image in `zuno-ai-build`, wait for `status.phase: Complete`, fail loudly otherwise. Idempotent: a `ConfigChange` trigger only starts a new build when content actually changed; forcing a rebuild needs deleting the BuildConfig or `oc start-build` directly (documented manual escape hatch, same pattern as `models_vllm_image_override`). Covers 6 of the 8 images the CI matrix already builds (`mcp`→mcp-gateway+mcp-sales-db; `rag`→rag-service; `agent`→agent-runtime+agent-bff+agent-frontend) - `ai-gateway` and the `postgresql-pgvector` base image aren't part of any Day 1 build component, an explicit flagged gap; both still build via the existing GitHub Actions pipeline (ADR-0051). `zuno-ai-build` gets a `default-deny-all-ingress` NetworkPolicy and grants exactly the three namespaces that run a build-produced image (`zuno-ai-run`, `zuno-data`, `zuno-agent-tekos`) scoped `system:image-puller` access via a RoleBinding to the `system:serviceaccounts:<namespace>` group. This grant is created at Day 1 build time, not by the Day 0 `namespaces` role, since `zuno-ai-build` doesn't exist until a build first runs.
- **`zuno-ai` → `zuno-ai-run`/`zuno-ai-build`**: renamed across every chart, `Application` destination, service default and current (non-ADR) doc mention - a `grep -rn` sweep confirmed zero bare `zuno-ai` references remain outside `docs/adr/*.md`'s historical ADRs (0007/0023/0037/0052/0053), correctly left untouched per this project's "ADRs are immutable" convention. One real bug caught mid-rename: a blind `sed` pass double-mangled this ADR's own already-forward-looking `zuno-ai-run`/`zuno-ai-build` mentions into `zuno-ai-run-run`/`zuno-ai-run-build` - found and fixed by grepping for that exact double-suffix pattern before committing.
- **`make day0|d0 all`/`make day1|d1 all`**: `day0`'s `all` runs check→install→configure unconditionally. `day1`'s `all` handles build components (`mcp`, `rag`, `agent`) and run components (`llm`, `models`, `sql_schema`, `rag`, `mcp`, `agents`, `mlops`) as different, overlapping-but-not-identical sets - `agent` (singular) only builds, `agents` (plural) only runs, a real distinct name pair. `make d1 all <component>` checks set membership in both lists independently and only runs the stages that apply.
- **Verified**: `ansible-playbook --syntax-check` (all playbooks), `helm lint` (every chart), and the new dispatch logic (`make -n` dry runs plus real invocations of deliberately-invalid combinations, confirming each fails with the intended diagnostic) were actually run and pass. **Not executed**: no live OpenShift cluster exists in this environment, so the actual `BuildConfig`/`Build` lifecycle, the cross-namespace pulls, and the full Day 0 → Day 1 sequence were not exercised against a real cluster.

See [Standard clauses](README.md#standard-clauses) for Acceptance criteria.

## Related ADRs

- [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md)
- [ADR-0023](0023-use-a-namespace-per-agent-isolation-model.md)
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
- [ADR-0047](0047-manage-the-complete-openshift-ai-prerequisite-lifecycle.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0051](0051-use-immutable-and-verifiable-software-supply-chain-artifacts.md)

## Review evidence

This decision is grounded in real-cluster operational friction discovered this session (CloudNativePG and Crunchy Postgres Operator catalog/channel/package-name mismatches) plus explicit operator requirements for a Day 0/Day 1 deployment split, a uniform per-component check/install/configure lifecycle, and a build/run namespace separation.
