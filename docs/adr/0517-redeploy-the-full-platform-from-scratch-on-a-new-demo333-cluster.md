# ADR-0517: Redeploy the full platform from scratch on a new demo333 cluster

- **Status:** Proposed
- **Target:** v0.6
- **Date:** 2026-08-24
- **Decision owners:** Zuno Demo architecture team

## Context

The platform's Day 0–3 automation (Ansible + GitOps, ADR-0003/ADR-0030/
ADR-0056/ADR-0060) has only ever been exercised as incremental changes
against the existing `demo222` cluster. There is no direct evidence the
stack can be bootstrapped unattended, end-to-end, on a brand-new cluster —
any residual manual step, undocumented prerequisite, or environment-
specific assumption baked into `demo222` over time would only surface on a
genuine from-scratch run.

## Decision

1. Provision a new OpenShift cluster, `demo333`. Provisioning mechanics
   (infrastructure, base OpenShift install) are an operator decision, out
   of scope for this ADR.
2. Redeploy the full platform onto `demo333` using only the existing entry
   points — `make day0 install`, `make day1 install`, and the existing
   Day 2/Day 3 checks and stresstests. No manual `kubectl`/`oc` patches,
   no undocumented pre-seeding beyond `ansible/confidential.yml`.
3. Any step that requires manual intervention, an undocumented
   prerequisite, or a hand-edited resource is logged in this ADR's
   Implementation notes and either (a) fixed in the Ansible/GitOps
   automation before being marked closed, or (b) filed as its own
   follow-up ADR/WP when the fix is out of scope for this pass.
4. Success is demonstrated by `demo333` passing the same Day 0/Day 1/
   Day 2 acceptance gates (ADR-0053, ADR-0057/ADR-0058) as `demo222`,
   proving the automation — not just the design — is complete.

## Acceptance criteria

- A real `demo333` cluster exists and the full platform is deployed on it
  via `make day0/day1 install` only.
- `make d1 check` / `make day2 test all` pass on `demo333` at a rate
  comparable to `demo222`, or every gap is enumerated here with a closure
  plan.
- Every manual intervention required during the redeploy is recorded in
  this ADR with either a landed automation fix or a linked follow-up
  ADR/WP.
- `demo222` is left untouched — this is a parallel proof, not a migration.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Consequences, Security/Operational considerations, Migration/evolution and
Review evidence.

## Related ADRs

- [ADR-0003](0003-use-ansible-and-make-as-the-deployment-entry-point.md)
- [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md)
- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md)
- [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)
