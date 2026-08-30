# WP-103: Model Controller RBAC for who may launch which Job/Workflow Template

- **State:** Not started.
- **ADRs:** ADR-0418 (Security considerations - Phase 3/4 launch-RBAC).
- **Depends on:** WP-094 (Job Templates registered), WP-097 (launch
  mechanism itself).
- **Unblocks:** ADR-0418 clause 1's Phase 3 (`day0/day1 install`) and
  Phase 4 (`uninstall`/`reinstall`) - both are explicitly gated on this
  existing before those verbs get exposed as Job Templates at all.

> Execute this brief as a standalone task from the repository root.

## Goal

Model, inside Controller's own RBAC (Organizations/Teams/Users, Job
Template `execute` role assignments), *who* may launch each Job/Workflow
Template - not just what the launched job can do to the cluster (the
`zuno-cluster-reader`/`zuno-aap-installer` credential tiers WP-094 already
built, which govern the launched job's own permissions, not who's allowed
to click launch). ADR-0418's own Security considerations section has
flagged this as open since its first draft; WP-094/095/097/099 all
explicitly deferred it as out of scope while proving the launch mechanism
itself works.

## ADR references

ADR-0418, Security considerations: "*who* (which Controller user/team) may
launch each Job Template ... remains open, unaddressed by WP-094 and still
deferred to whichever WP implements Phase 3/4 for real." This is that WP.

## Preconditions (verify before starting)

- WP-094/095/097 merged and live-verified (all 14 Job Templates/7 Workflow
  Templates registered and launchable).
- Live inventory of Controller's current Organization/Team/User setup
  (`GET /api/controller/v2/organizations/`, `/teams/`, `/users/`) - today
  only the `admin` superuser and the `zuno` organization exist; there is no
  existing team/role structure to build on.

## Scope (not yet designed - this WP starts from a blank slate)

- Decide the granularity: per-Job-Template `execute` role grants (AAP's
  native mechanism, no new concept needed) vs. a coarser
  read-only-verbs-team / mutating-verbs-team split matching the two
  credential tiers.
- Phase 3 (`install`) and Phase 4 (`uninstall`/`reinstall`) are the actual
  targets - Phase 1/2 (`check`/`build`) carry little risk and may not need
  gating at all, a design decision this WP should make explicitly rather
  than gating everything uniformly.
- Whether launch-RBAC is managed by hand in the Controller UI (fastest,
  but undeclared/undocumented state, same class of problem ADR-0418 itself
  was written to avoid) or declared via `AnsibleTeam`/role-binding-style
  CRs the `tower.ansible.com` operator supports (if it does - unconfirmed,
  needs the same "read the CRD/operator source before assuming" discipline
  WP-095 used for `WorkflowTemplate`).

## Out of scope / deferred

- Any change to the `zuno-cluster-reader`/`zuno-aap-installer` credential
  tiers themselves (WP-094) - this WP is about *who* can launch, not what
  the launch can do.
- Actually flipping Phase 3/`install` verbs onto AAP as the primary path -
  clause 1 gates that on Phase 1/2 reliability, now demonstrated, but is a
  separate decision from having launch-RBAC ready.
