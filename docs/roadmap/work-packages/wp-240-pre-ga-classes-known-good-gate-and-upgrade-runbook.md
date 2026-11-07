# WP-240: Pre-GA classes, known-good gate and upgrade runbook

- **State:** Not started
- **ADRs:** [ADR-0607](../../adr/0607-pin-gate-and-schedule-pre-ga-dependencies.md)
- **Depends on:** [WP-238](wp-238-golden-path-check-freeze-protocol-and-demo-day-runbook.md) (the golden-path run that follows an upgrade)
- **Related:** [WP-195](wp-195-update-every-operator-on-demo333-through-the-repository.md) (the known-good file and the audit)
- **Target:** v0.16
- **Estimated files touched:** ~8: `platform/olm/audit_operator_updates.py` and its tests, `platform/olm/known-good-demo333.yaml`, `ansible/roles/operators/tasks/precheck.yml`, `ansible/confidential.example.yml` (the pinning text), `docs/platform/pre-ga-upgrade.md`

> Why: the platform's most visible features run on early-access, alpha and staging components, the known-good file
> went stale in two days, and the audit never compares the cluster with it. Every cluster action needs the user's go.

## Goal

Every operator has a support class, the known-good file is regenerated from the cluster and gates `make d3 check
operators`, and a pre-GA upgrade follows one written routine.

## Steps

1. Add `class:` (`ga`, `tech-preview`, `early-access`, `alpha`, `staging`) to each entry of the known-good file, read
   from the channel and the vendor's support statement.
2. `audit_operator_updates.py --against <known-good file>`: fail when an installed CSV differs from the recorded one or
   a Subscription is missing from the file; unit tests for both and for a clean pass.
3. Regenerate `known-good-demo333.yaml` from the cluster (read-only), outside any freeze, then switch `make d3 check
   operators` to the gate mode.
4. Rewrite the pinning paragraph of `ansible/confidential.example.yml` to match ADR-0607 clause 2 (it still says only
   OpenShift AI has a `startingCSV`).
5. `docs/platform/pre-ga-upgrade.md`: backup, record, go, pin commits, the role run, the CSV walk that continues after
   `make` exits, the image digests, the golden-path run, and the restore path (OLM does not downgrade).

## Acceptance

- `make d3 check operators` passes on demo333 against the regenerated file and fails on a synthetic mismatch.
- The next pre-GA pin (the first UnifAI release after this WP) follows the runbook, and its commit carries the go and the
  known-good change.
- ADR-0607 can then move to `Implemented`.
