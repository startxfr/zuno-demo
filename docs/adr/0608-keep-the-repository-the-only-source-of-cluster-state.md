# ADR-0608: Keep the repository the only source of cluster state

- **Status:** Implemented
- **Target:** v0.16
- **Date:** 2026-11-07
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0312](0312-route-operator-installs-through-argocd-applications.md), [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md), [ADR-0559](0559-follow-the-cluster-version-and-never-branch-by-ocp-version.md), [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0607](0607-pin-gate-and-schedule-pre-ga-dependencies.md)

## Context

The platform is meant to be rebuilt from this repository alone (ADR-0517, ADR-0547). The 2026-11-07 review found state
on demo333 that the repository does not explain.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Two operators run without a declaration. | `elasticsearch-eck-operator-certified` and `nfs-provisioner-operator` appear only in `platform/olm/known-good-demo333.yaml`; no role, chart or Application installs them. |
| F2 | A chart depends on one of them. | `gitops/charts/unifai/values.yaml` sets `sharedStorageClass: nfs`, used by the `UnifaiStack` template. A fresh cluster built from the repository would have no `nfs` storage class. |
| F3 | Rollouts apply objects by hand first. | WP-224 applied PeerAuthentications by hand in PERMISSIVE before ArgoCD owned them; nothing lists such objects or checks that they were adopted. |
| F4 | Live state ran ahead of the records. | WP-223's Vault migration was live on demo333 while the tracker still said `Not started`; images have been built in the cluster from commits that were not yet pushed. |
| F5 | The deployment branch is misdocumented. | `RELEASING.md` said `main` is what demo333 deploys. The manifests default to `main`, but `ansible/tasks/apply_gitops_app.yml` overrides it with `zuno_gitops_target_revision`, set outside the repository: 110 of the 112 live Applications tracked `devel` on 2026-11-07. |

## Decision

**Everything that runs on a cluster is declared in the repository, or listed as external with an owner, and a check
reports anything else.**

1. **Every Subscription is declared or listed as external.** An operator on the cluster is installed by a role or a
   chart, or appears in `platform/drift/external-operators.yaml` with an owner and a reason (a file of its own: the
   known-good file is regenerated at every pin). ECK is either declared
   by a role or removed, by the owner's decision; nfs-provisioner gets a role, because the UnifAI chart depends on it.
2. **A chart dependency is installed by the repository.** A storage class, CRD or operator that a chart needs is
   installed by a role that runs before the chart, or the chart's precheck fails with the missing name.
3. **Hand-applied objects are temporary.** An object applied by hand during a rollout carries the label
   `zuno.io/applied-by-hand: <WP>`. It is adopted by ArgoCD or deleted before that work package can be `Done`.
4. **Nothing goes live from an unpushed commit.** An in-cluster build and a pin start only from a commit that is on
   `origin`, and the build records that commit.
5. **Live state is recorded the same day.** A work package whose change is live gets its tracker row and brief updated
   that day, even when the work is not finished (`Operator pending` exists for that).
6. **`make d3 check drift` reports the gaps.** It lists undeclared Subscriptions (clause 1), missing chart dependencies
   (clause 2), objects labelled `zuno.io/applied-by-hand` (clause 3) and running first-party images whose recorded
   commit is not on `origin` (clause 4). It reports only until the first clean run, then fails on any finding.
7. **The deployment branch is written down as it is.** `RELEASING.md` says which branch each cluster's Applications
   track (`zuno_gitops_target_revision`, `devel` on demo333), that a push to that branch is a deployment, and that
   `main` carries the tags. The value moves from the confidential file to `ansible/clusters/<cluster>.yml`, since it is
   not a secret.

## Alternatives considered

- **Delete everything undeclared.** ECK may serve a purpose outside this repository; deleting it without its owner's
  decision could break that. Rejected; clause 1 asks for the decision.
- **Point the Applications at `main` and deploy by merge.** It would make a merge the deployment step, which is cleaner,
  but it changes every Application and the daily flow of every working session. Not decided here; it can be a later ADR
  once the drift check is clean.

## Consequences

- A rebuild from the repository gets the storage class UnifAI needs.
- Rollouts keep their hand-applied first step, but each one is labelled and has an end.
- The drift check is one more read-only probe, and it can join the golden-path baseline run (ADR-0605).

## Security considerations

An undeclared operator is an unreviewed cluster-scoped privilege. Clause 1 brings each one under review or removes it.

## Operational considerations

The drift check reads Subscriptions, labelled objects and pod images through the Kubernetes API and compares commits
with `git ls-remote origin`. It changes nothing.

## Work packages

[WP-241](../roadmap/work-packages/wp-241-drift-check-nfs-provisioner-role-and-eck-decision.md).

## Update 2026-11-07 (WP-241): the drift check runs

`platform/drift/check_drift.py`, run by `make d3 check drift` (report-only until `zuno_drift_strict`), first run on
demo333 on 2026-11-07: two undeclared Subscriptions (nfs-provisioner-operator, elasticsearch-eck-operator-certified),
no missing storage class, no hand-applied or unowned security object in zuno-* namespaces, no first-party image built
from a commit missing on origin. Decisions of the owner the same day: ECK is unused and is uninstalled after the
demonstration of 2026-11-09 (listed in `platform/drift/external-operators.yaml` until then); nfs-provisioner gets its
role this weekend and is adopted live with the owner's go. The skip on an AAP execution environment (no `oc`, no git
checkout) is deliberate: the check runs from a workstation.

## Update 2026-11-07 (WP-241): implemented

nfs-provisioner was adopted live on demo333 with the owner's go (one AppProject destination applied from
`ansible/roles/argocd/kustomize/appproject`, then `make d1 install nfs-provisioner`): same NFS server pod with no
restart, the `NFSProvisioner` at generation 1, the three UnifAI volumes still Bound; the only change is the
Subscription's ADR-0607 pin (`Manual`, `startingCSV` v0.0.9). The known-good file was regenerated and its gate passes.
`make d3 check drift` is clean and runs in strict mode on demo333 (`zuno_drift_strict: true`). ECK stays listed in
`platform/drift/external-operators.yaml` until it is uninstalled after the 2026-11-09 demonstration, which is an
operation, not a gap in this record. Clause 3's label is in `docs/platform/parallel-sessions.md`; clause 4 holds
because OpenShift builds label their images with `io.openshift.build.commit.id`, which the drift check reads; clause 7
is in `RELEASING.md`.
