# ADR-0022: Use GitOps-managed declarative agent tasks and policies

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

## Decision

Keep tasks, deterministic tools, prompts, model policy and authorization policy reviewable in Git.

**Bootstrap architecture (added 2026-08-04):** Ansible (ADR-0003) is a thin bootstrapper, not the configuration engine. `make prepare` installs the OpenShift GitOps (ArgoCD) operator and applies a single root `Application` (App-of-Apps) from `gitops/root-app-of-apps.yaml`, pointing at `gitops/apps/`. Every subsequent Ansible role's `configure` task applies one child `Application` manifest under `gitops/apps/<component>/application.yaml` rather than performing configuration inline - ArgoCD then reconciles the referenced Helm chart or Kustomize overlay under `gitops/charts/<component>/`. This makes the entire platform installable from exactly one manual credential (see ADR-0024) and keeps every configured component's desired state in Git, satisfying this ADR's intent literally rather than only for agent tasks/policies.

**Amended by [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md) (2026-08-06):** the root App-of-Apps is no longer applied by Ansible - every component's `configure` task applying its own child `Application` (described above) is now the sole mechanism `make day0|d0`/`day1|d1` uses. `gitops/root-app-of-apps.yaml` is kept only as a documented example of a pure-GitOps, Ansible-free bootstrap (`docs/platform/installation.md`). This paragraph is left as originally written per this project's "ADRs are immutable" convention; ADR-0311 is the current record of the bootstrap architecture's App-of-Apps handling.

See [Standard clauses](README.md#standard-clauses) for Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution and Related ADRs.
