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

**Implemented (2026-08-05)**, landed as four separate commits (ADR-level
review evidence + code, in order): the ADR itself; the Day 0 restructuring
(new roles, new playbooks, Makefile `day0`/`d0` dispatch, and every
operator-facing doc/fail-message reference to the old command names);
the `zuno-ai`→`zuno-ai-run`/`zuno-ai-build` rename, deliberately isolated
so a mistake in a 59-file mechanical rename is easy to bisect/revert
independently of the rest; and the Day 1 build mechanism plus Makefile
`day1`/`d1` dispatch.

**Day 0** (`ansible/playbooks/day0_{check,install,configure}.yml`,
`Makefile`'s `day0`/`d0` targets): `admin_context` (new role - `check`
verifies cluster API reachability; `install` verifies at least one
`StorageClass` exists, discover-only, and applies two `PriorityClass`
objects, `zuno-platform-critical`/`zuno-workload-default`; `configure`
re-applies the PriorityClasses and reports on the `argocd` role's
`ClusterRoleBinding`, non-fatally, since `admin_context` runs before
`argocd` in sequence and that binding legitimately doesn't exist yet the
first time). `namespaces` (new role, moved out of `agents` - `check`
reads the expected namespace list directly from `gitops/charts/
namespaces/values.yaml`, never duplicated as a hardcoded list, and fails
naming exactly which are missing; `install`/`configure` apply/re-apply
the same GitOps Application `agents`'s `configure.yml` used to apply
itself). `openshift_ai` absorbed the former `datascience` role's
namespace-creation and GPU `ResourceQuota` tasks (one role for one
conceptual prerequisite). The formerly separate `api` role was retired
into `agents`: once namespace-apply moved out of `agents`'s
`configure.yml`, it was doing exactly what `api` did.

**Day 1** (`ansible/playbooks/day1_{check,configure,build}.yml`,
`Makefile`'s `day1`/`d1` targets): `run` components (`llm`, `models`,
`sql_schema`, `rag`, `mcp`, `agents`, `mlops`) reuse each role's existing
`precheck.yml`/`configure.yml` unchanged - `configure` and `run` are
literal aliases, same playbook. `day1_check.yml` special-cases `agents`
to run `tasks_from: check` (the real ADR-0053 acceptance/security gate,
what bare `make check` used to run) rather than `tasks_from: precheck`,
so that capability wasn't silently lost in the rename - every other Day 1
component's `check` verb is a genuine dependency precheck.

**Day 1 build** (new `ansible/tasks/apply_openshift_build.yml`, new
roles `ansible/roles/{mcp,rag,agent}_build`): applies an `ImageStream` +
git-source `BuildConfig` (Docker strategy, `ConfigChange` trigger - no
new operator dependency) per image in `zuno-ai-build`, waits for
`status.phase: Complete`, fails loudly (naming the exact `oc logs`
command to inspect) otherwise. Idempotent, not "always rebuild": a
`ConfigChange` trigger only starts a new build when the BuildConfig
content actually changed, matching every other `kubernetes.core.k8s`
task's idempotency in this repository - to force a rebuild against
unchanged source, delete the BuildConfig first or run `oc start-build`
directly (a documented manual escape hatch, same pattern as
`models_vllm_image_override`). Covers 6 of the 8 images
`.github/workflows/build-publish.yml`'s CI matrix already builds
(`mcp` → `mcp-gateway`+`mcp-sales-db`; `rag` → `rag-service`; `agent` →
`agent-runtime`+`agent-bff`+`agent-frontend`) - `ai-gateway` and the
`postgresql-pgvector` base image aren't part of any named Day 1 build
component, an explicit, flagged gap rather than a silent omission; both
still build via the existing GitHub Actions pipeline (ADR-0051).
`zuno-ai-build` gets a `default-deny-all-ingress` `NetworkPolicy` (build
pods pull source and push images out; nothing needs inbound access) and
grants exactly the three namespaces that actually run a build-produced
image (`zuno-ai-run`, `zuno-data`, `zuno-agent-tekos`) scoped
`system:image-puller` access via a `RoleBinding` to the
`system:serviceaccounts:<namespace>` group (not a shared "default"
ServiceAccount name, since every workload uses its own dedicated
least-privilege ServiceAccount per ADR-0052). This grant is created here,
at Day 1 build time, deliberately not by the Day 0 `namespaces` role:
`zuno-ai-build` doesn't exist until a build first runs, so granting on it
any earlier would make Day 0 depend on Day 1 having partially run first -
the same reasoning `gitops/charts/namespaces/values.yaml`'s own comment
gives for why `zuno-ai-build` isn't in that chart's `platformNamespaces`
list either. The five affected charts' `image.repository`/
`frontendRepository`/`bffRepository` defaults now point at
`zuno-ai-build` instead of each workload's own run namespace.

**`zuno-ai` → `zuno-ai-run`/`zuno-ai-build`**: renamed across every
chart `values.yaml`/`NetworkPolicy` namespaceSelector, every GitOps
`Application` destination, every Go/Python service default, and every
current (non-ADR) doc mention - a `grep -rn` sweep confirmed zero bare
`zuno-ai` references remain outside `docs/adr/*.md`'s historical ADRs
(0007/0023/0037/0052/0053), which are correctly left untouched per this
project's "ADRs are immutable" convention - they accurately recorded the
name that existed when they were written. One real bug caught mid-rename:
a blind `sed` pass double-mangled this ADR's own already-forward-looking
`zuno-ai-run`/`zuno-ai-build` mentions (written that way from the start,
in the Phase 1 commit) into `zuno-ai-run-run`/`zuno-ai-run-build` - found
and fixed by grepping for that exact double-suffix pattern across every
touched file before committing.

**`make day0|d0 all [component]`/`make day1|d1 all [component]`**:
`day0`'s `all` runs check→install→configure unconditionally, since every
Day 0 component has all three (even if some are documented no-ops).
`day1`'s `all` is not that simple: build components (`mcp`, `rag`,
`agent`) and run components (`llm`, `models`, `sql_schema`, `rag`, `mcp`,
`agents`, `mlops`) are different, overlapping-but-not-identical sets -
most visibly, `agent` (singular) only builds and `agents` (plural) only
runs, a real distinct name pair, not a typo. `make d1 all <component>`
checks set membership in both lists independently and only runs the
stages that actually apply, rather than assuming one shared list or
hard-failing on `agent`/`agents` cross-verb combinations that are
individually valid but not simultaneously so.

**Verified**: every `ansible-playbook --syntax-check` (all playbooks,
including the 6 new ones), `helm lint` (every chart, including the 5 with
new `zuno-ai-build` image references), and the new Day 0/Day 1 Makefile
dispatch logic (`make -n` dry runs across representative verb/component
combinations, plus real invocations of the deliberately-invalid ones -
`make d1 build agents`, `make d1 check agent`, bad verbs, bad components -
confirming each fails with the intended clear diagnostic) were actually
run in this environment and pass. **Not executed**: no live OpenShift
cluster exists in this environment (the same constraint as every other
cluster-dependent change in this repository), so the actual `BuildConfig`/
`Build` lifecycle, the `system:image-puller` cross-namespace pulls, and
the full Day 0 → Day 1 sequence end to end were not exercised against a
real cluster.

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
