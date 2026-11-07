# WP-242: Canary namespace pattern on demo333

- **State:** Not started
- **ADRs:** [ADR-0609](../../adr/0609-rehearse-on-canary-namespaces-of-demo333.md)
- **Depends on:** none
- **Related:** [WP-179](wp-179-common-preparation-for-experience-clients.md) (the scratch namespaces), [WP-227](wp-227-hardened-deployment-profile.md), [WP-211](wp-211-keycloak-internal-external-mode.md)
- **Target:** v0.16
- **Estimated files touched:** ~6: `ansible/tasks/canary_namespace.yml` (create and remove), a playbook entry point, `docs/platform/canary-rehearsal.md`, the drift check's leftover-canary rule

> Why: there is no second cluster. WP-227 and the external-mode work packages each need somewhere to rehearse, and the
> existing scratch namespaces were made by hand. Every cluster action needs the user's go.

## Goal

One shared task creates and removes a labelled, quota-bound, default-deny canary namespace for a work package, and one
page says what can and cannot be rehearsed there.

## Steps

1. `ansible/tasks/canary_namespace.yml`: create `zuno-canary-<wp>` with the labels `zuno.io/canary=true` and
   `zuno.io/work-package`, a ResourceQuota, a default-deny NetworkPolicy, and the egress the work package lists. Remove
   it the same way.
2. `docs/platform/canary-rehearsal.md`: the lists of ADR-0609 clauses 2 and 3, and how a work package records "not
   rehearsed".
3. A canary left after its work package is Done is a drift finding (WP-241).
4. Rehearse the pattern once with a simulated external Keycloak in a canary namespace. This is the first step of WP-211.

## Acceptance

- A canary namespace is created and removed by the task, and nothing outside it can reach it.
- WP-227 and WP-211 cite the pattern in their steps.
- ADR-0609 can then move to `Implemented`.
