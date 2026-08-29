# ADR-0421: Reshape Day 0/Day 1 boundaries around an "always-on infra" core

- **Status:** Implemented
- **Target:** v0.4
- **Date:** 2026-08-30
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0418's own Context section (v0.4, still `Proposed`) already named a
broader reshaping idea it deliberately did not commit to: "collapsing
today's Day 0 into a smaller 'always-on infra' tier (ArgoCD, Keycloak,
Vault, External Secrets, AAP, and whatever else is strictly mandatory),
demoting the rest of today's Day 0 components into a new Day 1... Whether
and how to restructure Day 0/Day 1/Day 2 is reserved for a future ADR,
once there is concrete evidence... that routing execution through AAP
actually works well enough to justify redesigning the sequencing model
around it."

This ADR is that reserved future decision, scoped narrowly rather than as
a full Day 0/1/2 renumbering: it moves exactly the components ADR-0418
already named as the "always-on infra" core (`postgresql`, `keycloak`,
`aap`, `aap-config` - PostgreSQL because both Keycloak and AAP need a
dedicated database on it) from Day 1 into Day 0, and moves an equal-sized
group of Day 0 components with no comparable "always-on" role
(`nvidia-gpu`, `custom-metrics-autoscaler`, `nfd`, `smtp`) into Day 1 in
exchange, so Day 0's total component count is unchanged.

ADR-0060 (Implemented, 2026-08-22) had moved `postgresql`/`mariadb`/
`tempo`/`keycloak` out of Day 0 into Day 1 for a *categorization* reason
only - Day 0 was redefined as "bare cluster prerequisites", Day 1 as "the
AI-platform-operator stack" - not for any technical/circular-dependency
blocker. The ArgoCD mechanism (`-d0`/`-d1` Application pair per
component) is identical regardless of which Makefile day-tier invokes it;
the day tier is purely a sequencing grouping. Every real prerequisite of
`postgresql`/`keycloak`/`aap`/`aap-config` - `vault`, `external-secrets`,
`machines` - already lives in Day 0 and is unaffected by this move.
`openshift-oauth` is not moved: its only real dependency is `keycloak`,
which is satisfied regardless of tier since all of Day 0 completes before
Day 1 starts.

This ADR is also the acknowledged prerequisite for extending ADR-0418's
AAP Job/Workflow Template execution to Day 2 and Day 3 (tracked
separately): a Job Template's `playbook` field is `day<N>_<verb>.yml`, so
its identity depends on each component's final day-tier placement.

## Decision

1. **`postgresql`, `keycloak`, `aap`, `aap-config` move from Day 1 to Day
   0**, inserted immediately after `machines` (their real prerequisites -
   `vault`, `external-secrets`, `machines` - all precede them already):

   ```
   New Day 0: argocd, admin_context, namespaces, image_mirrors,
     openshift_rbac_groups, vault, cert_manager, external_secrets,
     machines, postgresql, keycloak, aap, aap_config
   ```

2. **`nvidia-gpu`, `custom-metrics-autoscaler`, `nfd`, `smtp` move from
   Day 0 to Day 1**, inserted at the head of the Day 1 sequence. None of
   the three GPU-node components need anything beyond `machines` (stays
   Day 0, unaffected - `nfd` still precedes `nvidia_gpu`); `smtp` only
   needs `vault`/`external-secrets` (Day 0):

   ```
   New Day 1: smtp, nfd, nvidia_gpu, custom_metrics_autoscaler, redis,
     observability, service_mesh, mesh_monitoring, kiali, grafana,
     mariadb, tempo, openshift_oauth, connectivity_link, lws, jobset,
     kueue, openshift_ai, lightspeed, aiagent_operator
   ```

   `openshift_oauth` now sits where `keycloak` used to (right before
   `connectivity_link`) - its dependency on Keycloak's Ingress/TLS Secret
   is now satisfied by Day 0's `keycloak` instead of a Day 1 one.

3. **This is a pure component-placement change - no new deployment
   mechanism, no renamed Makefile target or playbook file, no change to
   any component's own Ansible role or Helm chart.** The internal
   `-d0`/`-d1` Application-pair naming (ADR-0060's "operator vs. instance"
   convention, independent of macro day-tier) is unchanged for every
   moved component: `zuno-postgresql-d0`/`-d1`, `zuno-keycloak-d0`/`-d1`,
   `zuno-aap-d0`/`-d1`, `zuno-aap-config-d0`/`-d1` keep their names.

4. **A pre-existing bug is fixed incidentally**: `day0_reconcile.yml`'s
   component list had never included `machines` (present in
   `day0_install.yml`/`day0_check.yml` but absent from reconcile since it
   was introduced) - fixed as part of touching this file's list for this
   ADR's own anchor point.

## Consequences

- Day 0 grows from 12 to 13 components; Day 1 stays at 20 (loses 4, gains
  4). Total component count across Day 0+Day 1 is unchanged.
- Day 0 now provisions genuinely stateful, heavier services (a Postgres
  cluster, Keycloak, the full AAP Gateway/Controller/Hub/EDA stack) that
  it previously never touched - Day 0's wall-clock install time grows
  substantially, and its "bare cluster prerequisites" framing (ADR-0060)
  now more precisely reads as "cluster prerequisites plus this repo's
  always-on infra core".
- `nvidia-gpu`/`nfd`/`custom-metrics-autoscaler`/`smtp` moving to Day 1
  has no material effect on their own behavior - only the tier issuing
  their `make` command changes.
- Several role READMEs and one Makefile/ansible comment block previously
  described stale, pre-ADR-0060 placements as fact (`custom_metrics_
  autoscaler`, `connectivity_link` READMEs both claimed a Day 0 ordering
  that was already false before this ADR) - corrected alongside this
  change rather than left to drift further.

## Security considerations

No new authorization surface is introduced by this ADR alone - every
moved component keeps its existing RBAC/credential shape. Day 0 becoming
responsible for AAP's own bootstrap does sharpen a chicken-and-egg
property already implicit in ADR-0418: Day 0 can never be routed through
an AAP Job/Workflow Template, since Day 0 is what brings AAP itself up.

## Operational considerations

`docs/roadmap/work-packages/wp-072-*.md`/`wp-073-*.md` (ADR-0354,
`Done`) and their own "Related"/dependency text describe `aap`/
`aap-config` as Day 1 components, matching the state that was true when
they were written - left unedited per this repository's "ADRs/closed WPs
are immutable historical records" convention. `ansible/roles/{postgresql,
keycloak,aap,aap_config,nvidia_gpu,nfd,custom_metrics_autoscaler,smtp,
openshift_oauth}/README.md` and `ansible/README.md` are updated to
describe the new placement as current state.

## Acceptance criteria

- `Makefile`'s `DAY0_COMPONENTS`/`DAY1_RUN_COMPONENTS` and all eight
  `ansible/playbooks/day{0,1}_{install,check,reconcile,uninstall}.yml`
  component lists reflect the new placement.
- `ansible-playbook --syntax-check` passes on all eight touched
  playbooks.
- `make help`, `make day0`, `make day1` render the new component lists.
- `make d0 install <moved-in-component>` / `make d1 install
  <moved-in-component>` are accepted by Makefile validation; the old
  tier now rejects them (`make d1 install keycloak` fails with
  "Unsupported day1 install component").
- `python3 platform/docs/check_docs.py` passes.

## Implementation state

**Implemented (2026-08-30).** Repo-level change only (Makefile, the eight
day0/day1 playbooks, affected role READMEs, `ansible/README.md`,
`README.md`, `check_docs.py`-flagged auto_fix hints) - Makefile validation
paths exercised without a cluster (`make d0 install bogus-component`,
`make d1 install bogus-component`, and the moved components validating
against their new tier and being rejected by their old one all behave as
expected). Not yet live-verified end to end against a real cluster (a
full `make d0 install all` → `make d1 install all` run) - deferred to
whichever follow-up work package first needs a live Day 0/Day 1 run after
this change (this repository's shared cluster was not mutated for this
ADR beyond two no-op idempotent installs confirming `changed=0`).

## Related ADRs

- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) -
  extended, not superseded: the Day 0/Day 1 split concept is preserved,
  only these 8 components' boundary placement moves.
- [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md) -
  extended, not superseded, for the same reason.
- [ADR-0354](0354-add-ansible-automation-platform-as-a-day-1-component.md) -
  `aap`/`aap-config`'s prior Day 1 placement, now superseded by this ADR
  (WP-072/WP-073 remain unedited historical records of the Day 1 state).
- [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md) -
  named this reshaping as reserved future work; this ADR is that future
  decision, and is itself a prerequisite for extending ADR-0418's
  execution model to Day 2/Day 3.

See [Standard clauses](README.md#standard-clauses) for Alternatives and
Review evidence.
