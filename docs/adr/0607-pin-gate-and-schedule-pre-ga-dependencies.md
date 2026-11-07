# ADR-0607: Pin, gate and schedule pre-GA dependencies

- **Status:** Accepted
- **Target:** v0.16
- **Date:** 2026-11-07
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md), [ADR-0558](0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md), [ADR-0559](0559-follow-the-cluster-version-and-never-branch-by-ocp-version.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md), [ADR-0590](0590-front-openclaw-with-oauth2-proxy-and-an-egress-firewall-one-claw-operator-per-persona-namespace.md), [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0608](0608-keep-the-repository-the-only-source-of-cluster-state.md), [ADR-0609](0609-rehearse-on-canary-namespaces-of-demo333.md)

## Context

The platform's most visible features sit on components that are not generally available, and each of their releases
has, at least once, changed live behaviour.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Several core components are pre-GA. | `platform/olm/known-good-demo333.yaml` (2026-11-05): OpenShift AI `3.6.0-ea.2` on the `beta` channel, `unifai-operator` on `alpha`, `claw-operator` `0.0.227-commit-f5aa592` on `staging`, `nfs-provisioner-operator` `0.0.9` on `alpha`. |
| F2 | Pre-GA releases broke live paths. | UnifAI 0.1.63 broke the approval relay (500 on `session.approval`); the forced OpenShift AI 3.6 EA install opened MaaS for about 20 minutes and has no rollback (`ansible/clusters/demo333.yml`). |
| F3 | Pins are uneven. | OpenShift AI and claw-operator use `installPlanApproval: Manual` and a `startingCSV`; UnifAI uses a digest-pinned catalog with `Automatic` approval, which ADR-0574 accepts because the pinned index cannot offer a version git did not choose. `ansible/confidential.example.yml` still says only OpenShift AI gets a `startingCSV`. |
| F4 | The known-good set is not a gate. | `platform/olm/audit_operator_updates.py` compares each Subscription with its catalog, never with the known-good file; the file was stale two days after it was written. |
| F5 | OLM does not downgrade. | A bad operator release is undone by a restore or by a forward fix, never by moving the pin back. |
| F6 | No rule says when an upgrade may happen. | The rule "one go per UnifAI release" (2026-11-04) is followed in practice but written nowhere in the repository. |

## Decision

**Every pre-GA dependency is classified, pinned, approved one release at a time, and upgraded only outside a freeze,
with its rollback recorded before the upgrade.**

1. **Classes.** Each operator in the known-good file carries a `class:`: `ga`, `tech-preview`, `early-access`, `alpha`
   or `staging`. The class is read from the channel and the vendor's support statement, and reviewed when the channel
   changes.
2. **The pin is the approval point.** A non-GA dependency is pinned by catalog digest or by `startingCSV`. Where the
   catalog is not pinned by digest, `installPlanApproval: Manual` is required and the role approves only the pinned
   InstallPlan (as OpenShift AI and claw-operator already do). Where it is pinned by digest, ADR-0574's `Automatic`
   approval stays: the commit that moves the digest is the approval.
3. **One go per release.** The commit that moves a non-GA pin names the release and the owner's go in its message. A
   release may be skipped. A message from another working session is never the go.
4. **Before the upgrade:** a backup of the stateful parts the release touches (`make d3 backup postgresql`, `make d3
   backup unifai`), the current CSV and digests recorded in the known-good file in the same commit, and the vendor's
   release notes read for migrations.
5. **When.** Never inside a freeze (ADR-0605). The last pre-GA upgrade before a demonstration leaves time for one full
   golden-path run and one restore before the freeze starts.
6. **After the upgrade:** a full golden-path run. A failure is fixed forward or restored (F5); it is never left for the
   next session.
7. **Canary where it can be.** A namespace-scoped part of a release (stack images, an experience client) is rolled into
   a canary namespace first (ADR-0609). A cluster-scoped operator cannot be canaried; its work package says so and relies
   on clauses 4 and 6.
8. **The known-good file is a gate.** `audit_operator_updates.py` gains `--against <known-good file>` and fails when an
   installed CSV differs from the recorded one or when a Subscription is missing from the file. `make d3 check operators`
   runs it in that mode once the file has been regenerated from the live cluster.

## Alternatives considered

- **Use only GA components.** The demonstration exists to show what the next releases bring; most of its value is
  pre-GA. Rejected.
- **`Manual` approval everywhere, even with a digest pin.** It adds a second approval to a change that git already
  approves, and an unapproved InstallPlan blocks every other operator in the namespace. Rejected where the digest is
  pinned.
- **A second cluster for every upgrade.** The owner chose canary namespaces on demo333 over a second cluster
  (2026-11-07, ADR-0609). Rejected for now.

## Consequences

- An upgrade takes longer: backup, record, go, golden path. It is planned, not slipped in between two features.
- The known-good file changes with every pin and becomes reviewable history of what ran when.
- `confidential.example.yml`'s description of the pinning policy is rewritten to match.

## Security considerations

Pinning by digest also pins what was verified: a digest that moved without a commit is drift (ADR-0608), not an
upgrade.

## Operational considerations

The pinning routine (catalog digest, stack image digests, the role run, the CSV walk that continues after `make` exits)
becomes a runbook, `docs/platform/pre-ga-upgrade.md`, per ADR-0606 clause 6.

## Work packages

[WP-240](../roadmap/work-packages/wp-240-pre-ga-classes-known-good-gate-and-upgrade-runbook.md).
