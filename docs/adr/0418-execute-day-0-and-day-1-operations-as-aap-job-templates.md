# ADR-0418: Execute Day 0 and Day 1 operations as AAP Job Templates

- **Status:** Partially implemented
- **Target:** v0.4
- **Date:** 2026-08-20
- **Amended:** 2026-08-30 (depends on ADR-0421, which landed the "always-on
  infra" Day 0/Day 1 reshaping this ADR's own Context section had reserved
  for a future ADR - `postgresql`/`keycloak`/`aap`/`aap-config` are now
  Day 0 components, `nvidia-gpu`/`custom-metrics-autoscaler`/`nfd`/`smtp`
  are now Day 1; a Job Template's `playbook` field is `day<N>_<verb>.yml`,
  so this Decision's phasing below should be read against the post-
  ADR-0421 component placement, not the Day 1 placement described when
  this ADR was first drafted)
- **Amended:** 2026-08-30 (WP-094): scope extended from Day 0/Day 1 only
  to every Day 1/Day 2/Day 3 playbook - clause 1 below is updated to add
  Day 2/Day 3 phases and the two-tier credential design; clause 6 (new)
  records the routing mechanism (`zuno_make_aap_mode`) and Workflow
  Templates as separate, still-unimplemented follow-on work (WP-095/096)
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

   **(2026-08-30 amendment, WP-094): extended to Day 2 and Day 3,** phased
   by the same risk logic - `day2 check`/`day3 test`/`day3 check` alongside
   Phase 1 (read-mostly), `day2 build` alongside Phase 2, `day2 install`
   alongside Phase 3, `day3 stresstest`/`day3 backup`/`day3 restore`/
   `day3 sign` also land with Phase 3 (they mutate state - a running
   stresstest, a backup/restore, a re-signed OKF bundle - but are neither
   the primary bootstrap path nor gated the way Phase 4's uninstall/
   reinstall verbs are, so Phase 3's "AAP proven reliable" bar is the
   right one, not Phase 4's approval gate). `day0`'s own verbs get no
   Workflow Template and are never routed through AAP by `make` (clause 6)
   - Day 0 is what installs `aap` itself, a chicken-and-egg ADR-0421 also
   names.

   Two credential tiers replace the single `zuno-cluster-reader` this
   clause originally assumed: read-only verbs (`check`/`test`) keep
   `zuno-cluster-reader` (`cluster-reader` ClusterRole); every mutating
   verb (`build`/`install`/`reconcile`/`stresstest`/`backup`/`restore`/
   `sign`) uses a new `zuno-aap-installer` credential, bound to a
   purpose-built `zuno-aap-installer` ClusterRole scoped to this repo's
   own GitOps Applications, OLM objects and the CRDs each Day 1/Day 2
   operator owns - not cluster-admin, and explicitly excluding
   ClusterRole/ClusterRoleBinding write (no privilege-escalation path)
   and `aap`/`tower.ansible.com`/`automationcontroller`/`automationhub`/
   `eda.ansible.com` themselves. See `gitops/charts/aap-config/templates/
   clusterrole-installer.yaml` and `ansible/roles/aap_config/README.md`'s
   "Least-privilege machine credentials" section.

   Each mutating template's `target_component` is collected via a
   Controller Survey (`multiplechoice`, never free text) offering exactly
   the same component list the corresponding `DAY<N>_*_COMPONENTS`
   Makefile variable accepts, plus `all` - satisfying this ADR's own
   Security considerations requirement below without any new validation
   code, since an out-of-list value simply cannot be submitted through the
   launch form.

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

6. **(2026-08-30 amendment, WP-094/WP-095) Workflow Templates are decided
   and registered by this clause; routing through them is separate,
   still-open follow-on work:**
   - Day 1 and Day 2 each get AAP Workflow Templates (Day 1:
     install/check/reconcile/build; Day 2: install/check/build - no
     `reconcile` verb exists for Day 2) orchestrating that verb's
     per-component runs as a DAG, parallelizing components with no
     dependency on each other (confirmed live 2026-08-30 that the AAP
     resource operator ships a `WorkflowTemplate` CRD, `tower.ansible.com/
     v1alpha1`, same Path A as every other CR here - `oc api-resources`,
     careful to qualify `workflowtemplates.tower.ansible.com` explicitly,
     since the bare `workflowtemplate` name resolves to Argo's own
     unrelated CRD on this cluster). **Every workflow node launches the
     same underlying Job Template** (this clause's own registration, not
     a second one per component) with a different `extra_data.
     target_component` - a Workflow Template needs no credential or
     Survey of its own. The CRD's `workflow_nodes` field carries no
     CRD-documented schema (`x-kubernetes-preserve-unknown-fields`); the
     shape actually rendered (`identifier`, `unified_job_template`,
     `extra_data`, `related.{success_nodes,failure_nodes,always_nodes}`,
     `all_parents_must_converge`) is the underlying resource-operator
     role's own `awx.awx.workflow_job_template` Ansible module's
     documented argument spec, fetched from its upstream source rather
     than assumed. Day 3 gets no Workflow Template - its verbs have no
     cross-component sequencing to orchestrate (each verb already targets
     one component or a dynamically-resolved agent/platform set).
     **Repo work merged 2026-08-30 (WP-095):** all 7 Workflow Templates
     registered in `gitops/charts/aap-config`, their DAGs mechanically
     verified offline (no broken edges, no cycles, every multi-parent node
     flagged `all_parents_must_converge`, every node's `target_component`
     matching its Job Template's Survey exactly) - **not yet exercised
     against a real Controller**, and two edges (`kiali`/`grafana`
     independence; Day 2's `rag`/`rag-ingestion`/`mcp` parallel group) are
     flagged for live re-verification before being trusted, per
     `ansible/roles/aap_config/README.md`.
   - `make day1|d1`/`make day2|d2 <verb>` route through the matching
     Workflow Template, and `make day3|d3 <verb>` through its Job
     Template, when AAP is available - not decided by this clause; tracked
     as WP-096, entirely unimplemented. A new `zuno_make_aap_mode`
     variable (`local`/`remote`/`auto`, default `auto`, `ansible/
     confidential.yml`) will control this: `local` never routes through
     AAP (today's behavior, unconditionally); `remote` always routes
     through AAP and fails if unreachable; `auto` probes AAP's Gateway API
     and falls back to `local` silently if unreachable - preserving clause
     1's "AAP must never become a single point of failure" consequence for
     every mode except an operator's own explicit `remote` choice.
     `uninstall`/`reinstall` are never routed through AAP regardless of
     mode (Phase 4 stays gated as clause 1 describes).

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
launch form. **(2026-08-30, WP-094):** the Survey-as-multiplechoice design
in clause 1 satisfies this for every registered template. What remains
open, unaddressed by WP-094 and still deferred to whichever WP implements
Phase 3/4 for real: *who* (which Controller user/team) may launch each
Job Template - the two credential tiers WP-094 added govern what the
launched job can DO to the cluster, not who is allowed to click launch.

## Operational considerations

Job Template definitions (the Project's SCM revision, each template's
Survey spec) must stay in lockstep with the playbooks and components they
wrap. **(2026-08-30 correction, WP-094):** no `ansible/tasks/
aap_sync_job_templates.yml` file exists or ever existed - that was an
aspirational reference this ADR carried while still `Proposed`, never
matched by ADR-0354's actual (Path A) implementation. The real mechanism,
as WP-094 built it: `gitops/charts/aap-config/values.yaml`'s
`jobTemplates` list is the single source of truth for every template's
name/playbook/credential/Survey component list, rendered by
`templates/jobtemplate.yaml` and wired post-CR by `ansible/roles/
aap_config/tasks/wire_job_template.yml` - both re-run on every Day 0
install/reconcile of `aap-config`, the same drift-prevention property this
paragraph originally described, just against real files instead of an
assumed one.

## Acceptance criteria

This ADR delivers a decision record; implementation lands one phase at a
time via work packages (WP-094 for clause 1's registration, WP-095/096
for clause 6's Workflow Templates/routing), per this repository's
existing pattern (ADR-0352 clause 9: "roadmap briefs live under
`docs/roadmap/`, not in this ADR").

- `docs/adr/0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md`
  exists, containing the phased execution plan in clause 1 and the
  routing/Workflow Template scope in clause 6.
- The `## version 0.4` index table in `docs/adr/README.md` has the
  ADR-0418 row and its status string matches this file's own status.
- No Makefile target or playbook filename is renamed by this ADR alone -
  `day<N>_components` list *contents* change only via ADR-0421 (a
  separate, prerequisite ADR), never this one.

## Implementation state

**Partially implemented (2026-08-30, WP-094/WP-095 - repo work merged,
live verification pending).** All 14 Job Templates (clause 1's full
Day 1/2/3 list plus `zuno-day0-check`) and all 7 Workflow Templates
(clause 6) are registered by `gitops/charts/aap-config`/`ansible/roles/
aap_config`, each Job Template with its credential tier and (where
applicable) `target_component` Survey, each Workflow Template's DAG
mechanically self-consistent (no broken edges, no cycles, convergence
flagged correctly, node/Survey component sets matching exactly) -
`helm lint`/`helm template` confirm the chart renders correctly. **Not
yet live-applied or launched** - registering the CRs on the real cluster
(`make d0 install aap-config`) and confirming each new Job/Workflow
Template actually launches and reconciles successfully are deferred to
an operator-run session, per this repository's shared-cluster convention.
`make` routing/`zuno_make_aap_mode` (WP-096) and Phase 3/4 launch-RBAC
remain entirely unimplemented.

## Related ADRs

- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0344](0344-track-blocked-resources-and-add-a-day-0-reconcile-verb.md)
- [ADR-0354](0354-add-ansible-automation-platform-as-a-day-1-component.md) (companion/prerequisite, v0.2)
- [ADR-0421](0421-reshape-day-0-day-1-boundaries-around-always-on-infra.md) (prerequisite, v0.4 - moved `aap`/`aap-config` and their prerequisites into Day 0)

See [Standard clauses](README.md#standard-clauses) for Alternatives and
Review evidence.
