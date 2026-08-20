# ADR-0418: Execute Day 0 and Day 1 operations as AAP Job Templates

- **Status:** Proposed
- **Target:** v0.4
- **Date:** 2026-08-20
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0354 (v0.3) installs Ansible Automation Platform as a new Day 0
component and defines one AAP Job Template per top-level playbook, but
nothing executes through them yet. `make day0|d0 <verb> [component]` and
`make day1|d1 <verb> [component]` still run `ansible-playbook` directly
from whichever shell invokes `make` (an operator's terminal or a CI
runner), with no central execution history, scheduling, or RBAC-gated
launch surface beyond git history and ArgoCD sync history.

Candidate operations, read directly off the current Makefile/playbook
surface:

- `make day0|d0 reconcile` - already the closest thing this repository has
  to a safe, idempotent-by-design operation (ADR-0344's blocked-resource
  diagnosis and auto-remediation), and `make day0|d0 check`/`make day1|d1
  check` alongside it, including the ADR-0053 acceptance/security gate run
  by `day1 check agents`.
- `make day1|d1 build` - image builds, already namespace-isolated into
  `zuno-ai-build` (ADR-0056).
- `make day0|d0 install`/`make day1|d1 install` - the primary bootstrap
  path, and eventually `uninstall`/`reinstall`.
- Maintenance actions that today run entirely outside Ansible/Make, as
  native Kubernetes objects: the Vault backup `CronJob`
  (`gitops/charts/vault/templates/cronjob-backup.yaml`, disabled by
  default) and the MariaDB/PostgreSQL scheduled backup CRs. These are
  natural long-run candidates for AAP-scheduled Job Templates instead of
  cluster-native CronJobs/CRs, but converting them is not decided by this
  ADR.

The user who requested this ADR also described a broader, longer-term
reshaping of the Day 0/Day 1 vocabulary itself: collapsing today's Day 0
into a smaller "always-on infra" tier (ArgoCD, Keycloak, Vault, External
Secrets, AAP, and whatever else is strictly mandatory), demoting the rest
of today's Day 0 components into a new Day 1, and moving today's Day 1 (the
AI stack) into a new Day 2. That would supersede ADR-0056's Day 0/Day 1
definition and touch every playbook filename, the Makefile's `DAY0_*`/
`DAY1_*` variables, and roadmap documentation across the repository. The
user was explicit that this idea is still being thought through, not
settled - so this ADR deliberately does not commit to it. It only decides
that AAP Job Templates become an additional, tracked way to execute the
verbs that exist *today*, under today's names. Whether and how to
restructure Day 0/Day 1/Day 2 is reserved for a future ADR, once there is
concrete evidence (from this ADR's own rollout) that routing execution
through AAP actually works well enough to justify redesigning the
sequencing model around it.

## Decision

1. **AAP Job Templates become the primary tracked/audited execution path
   for Day 0/Day 1 verbs, phased in by risk rather than all at once:**
   - **Phase 1 (first):** `day0 reconcile`, `day0 check`, `day1 check` -
     idempotent and read-mostly by design; `day0 reconcile` in particular
     was built (ADR-0344) specifically to be safe to re-run.
   - **Phase 2:** `day1 build` - image builds, already isolated to the
     `zuno-ai-build` namespace with no path to running workloads
     (ADR-0056).
   - **Phase 3:** `day0 install`/`day1 install` - the primary bootstrap
     path, migrated only once Phase 1 and 2 have demonstrated AAP's own
     reliability as a control-plane dependency for this repository.
   - **Phase 4 (opt-in, explicitly gated):** `day0 uninstall`/`day1
     uninstall`/`reinstall` - destructive verbs require an explicit
     approval or RBAC gate inside AAP (a Job Template's "ask on launch"
     plus Controller RBAC restricting who may launch it) before being
     exposed as a Job Template at all.

   `make day0|d0`/`make day1|d1` remain the operator-facing interface and
   keep working exactly as they do today - direct `ansible-playbook`
   invocation from the same Makefile recipe. This ADR adds a second,
   trackable execution path via AAP's API/UI/CLI; it does not remove,
   deprecate, or route the Makefile path itself through AAP. A future ADR
   may reconsider that once AAP execution is proven across all four
   phases.

2. **A Job Template launch is this repository's canonical execution record
   for that run.** Who launched it, when, with what Survey answers
   (`target_component`), the full output, and success/failure become an
   audit trail this repository does not have today - additive to, not a
   replacement for, existing git history and ArgoCD sync history.

3. **Scheduling/CronJob consolidation is named as a future candidate, not
   decided here.** The Vault backup `CronJob` and the MariaDB/PostgreSQL
   backup schedules are listed as natural next candidates for becoming
   AAP-scheduled Job Templates instead of native Kubernetes CronJobs/CRs,
   once Phases 1-3 above are stable. No conversion is committed to by this
   ADR.

4. **This ADR explicitly does not redefine Day 0/Day 1 into Day 0/Day 1/
   Day 2, rename any Makefile target or playbook file, or change either
   `day0_components`/`day1`-component list.** It only adds a trackable
   execution path for verbs that already exist, under their existing
   names. Superseding ADR-0056's Day 0/Day 1 vocabulary - if it happens at
   all - is reserved for a separate, future ADR once there is a concrete
   reason to justify it (for example, once enough real execution has moved
   onto AAP that installing AAP itself no longer needs to be a Day 0
   bootstrap special case, a genuine chicken-and-egg question this ADR
   does not attempt to resolve).

5. **Failure and rollback semantics are unchanged from today's direct-CLI
   path.** An AAP-launched Job Template runs the exact same playbook with
   the exact same `target_component` extra-var Ansible already validates
   (`ansible/playbooks/day0_*.yml`/`day1_*.yml`) - no new success/failure
   logic is introduced anywhere in this decision, only a new caller of
   the same, unchanged automation.

## Consequences

- This repository gets, for the first time, a queryable execution history
  for its own operational verbs, and a path toward RBAC-gated self-service
  (for example, a specific team could be granted "launch `day1 check
  agents`" without cluster-admin access).
- AAP becomes critical-path infrastructure only in the narrow sense that
  clause 1 explicitly forbids it from becoming a hard dependency: if
  Controller is down, `make day0|d0`/`make day1|d1` must keep working
  standalone exactly as today. AAP must never become a single point of
  failure for operators who need to run these verbs.
- Phasing by risk means the highest-value case - a centralized audit trail
  for `install` itself - lands last (Phase 3), an accepted trade-off for
  safety over immediate completeness.
- Destructive verbs (Phase 4) gain a second, additional gate (AAP launch
  RBAC) beyond whatever access already lets someone run `make d0
  uninstall` from a shell - a net security improvement, not a regression,
  once implemented.

## Security considerations

Job Template launch access becomes a new authorization boundary - who can
trigger `day0 uninstall` against a real environment through AAP - that
must be modeled inside Controller's own RBAC before Phase 3 or Phase 4 go
live; it is a new surface, not an extension of an existing one, since no
comparable launch-gate exists for the direct-CLI path today. Survey-
provided `target_component` values must be validated against the same
component allow-list the Makefile already enforces (`DAY0_COMPONENTS`/
`DAY1_RUN_COMPONENTS`/`DAY1_BUILD_COMPONENTS`), never passed to
`ansible-playbook` as unchecked free text sourced from a Job Template
launch form.

## Operational considerations

Job Template definitions (the Project's SCM revision, each template's
Survey spec) must stay in lockstep with the playbooks and components they
wrap. `ansible/tasks/aap_sync_job_templates.yml` (ADR-0354) re-running on
every Day 0 install/reconcile of `aap` is what prevents that drift - a
Job Template pointing at a playbook argument that no longer exists, or
missing one that was just added, is caught the same way any other Day 0
component's reconcile already catches configuration drift.

## Acceptance criteria

This ADR delivers a decision record only. Implementation lands one phase
at a time via future work packages, per this repository's existing
pattern (ADR-0352 clause 9: "roadmap briefs live under `docs/roadmap/`,
not in this ADR").

- `docs/adr/0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md`
  exists, containing the four-phase execution plan in clause 1.
- The `## version 0.4` index table in `docs/adr/README.md` has the
  ADR-0418 row and its status string matches this file's `Proposed`.
- No implementation surface has changed by this ADR alone: no Makefile
  target, playbook filename, or `day0_components`/`day1`-component list
  differs from what ADR-0354 already establishes.

## Implementation state

**To be implemented.** No Job Template has been launched by anything but
an interactive operator/CI shell as of this ADR; Phase 1 is the first
implementation milestone against this decision.

## Related ADRs

- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0344](0344-track-blocked-resources-and-add-a-day-0-reconcile-verb.md)
- [ADR-0354](0354-add-ansible-automation-platform-as-a-day-0-component.md) (companion/prerequisite, v0.3)

See [Standard clauses](README.md#standard-clauses) for Alternatives and
Review evidence.
