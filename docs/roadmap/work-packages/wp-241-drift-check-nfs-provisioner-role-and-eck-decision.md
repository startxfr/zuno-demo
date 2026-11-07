# WP-241: Drift check, nfs-provisioner role and the ECK decision

- **State:** Repo work in review
- **ADRs:** [ADR-0608](../../adr/0608-keep-the-repository-the-only-source-of-cluster-state.md)
- **Depends on:** [WP-240](wp-240-pre-ga-classes-known-good-gate-and-upgrade-runbook.md) (the regenerated known-good file and its `external:` section)
- **Related:** [WP-224](wp-224-network-and-gitops-hardening-mesh-egress-appproject-jwks.md) (hand-applied objects during its rollout)
- **Target:** v0.16
- **Estimated files touched:** ~15: a new `ansible/roles/nfs_provisioner/` and its Application, `gitops/charts/unifai` (precheck for the storage class), a drift check under `platform/` with tests, `Makefile` and `ansible/playbooks/day3_check.yml` (the `drift` component), the known-good file

> Why: two operators run on demo333 with no declaration, the UnifAI chart depends on one of them, and nothing lists
> hand-applied objects or images built from unpushed commits. Every cluster action needs the user's go.

## Goal

A rebuild from the repository installs what the charts need, and `make d3 check drift` lists everything on the cluster
that the repository does not explain.

## Steps

1. **nfs-provisioner:** a role that installs it before UnifAI and a UnifAI precheck that fails when the `nfs` storage
   class is missing.
2. **ECK:** ask the user who uses it. Then either declare it with a role, or remove it in a window. **Decided
   2026-11-07:** unused, uninstalled after the 2026-11-09 demonstration; listed in
   `platform/drift/external-operators.yaml` until then.
3. **The label `zuno.io/applied-by-hand: <WP>`:** documented in the rollout runbooks, and applied to anything still
   hand-applied from WP-224.
4. **`make d3 check drift`:** reads Subscriptions, labelled objects and first-party pod images, and compares each image's
   recorded commit with `git ls-remote origin`. It reports at first, and fails once a clean run is recorded. **Done
   2026-11-07** (`platform/drift/check_drift.py`, role `drift`); first report recorded in ADR-0608's update.
5. **The commit in the build:** in-cluster builds record the source commit as an image label, where they do not already.

## Acceptance

- `make d3 check drift` runs on demo333 and its first report is recorded in this brief. Every finding is fixed, declared
  or owned.
- A UnifAI install on a cluster without the `nfs` class fails at its precheck with that name.
- ADR-0608 can then move to `Implemented`.
