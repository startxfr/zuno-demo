# WP-093: Move postgresql/keycloak/aap/aap-config to Day 0, nvidia-gpu/custom-metrics-autoscaler/nfd/smtp to Day 1

- **State:** Repo work merged - live verification pending.
- **ADRs:** ADR-0421 (new), amends ADR-0056/ADR-0060 placement; amends
  ADR-0418's header (dependency note only, its Decision content is
  unchanged by this WP).
- **Depends on:** none.
- **Unblocks:** the follow-up work extending ADR-0418's AAP Job/Workflow
  Template execution to Day 2/Day 3 - a Job Template's `playbook` field is
  `day<N>_<verb>.yml`, so it needs this placement settled first.
- **Estimated files touched:** ~25 (Makefile; 8 day0/day1 playbooks; ~10
  role READMEs; `ansible/README.md`; `README.md`; 2 ADR files;
  `docs/adr/README.md`; 3 auto_fix/hint strings across
  `ansible/roles/{postgresql,aap_config,openshift_oauth}`).

> Execute this brief as a standalone task from the repository root.

## Goal

Move `postgresql`, `keycloak`, `aap`, `aap-config` from Day 1 into Day 0
(right after `machines`), and move `nvidia-gpu`, `custom-metrics-
autoscaler`, `nfd`, `smtp` from Day 0 into Day 1 (at the head of the
sequence) - in every verb (`install`/`check`/`reconcile`/`uninstall`),
with no other behavioral change to any of the eight components' own
Ansible roles or Helm charts.

## ADR references

- ADR-0421 (new, this WP's decision record).
- ADR-0056/ADR-0060 (extended, not superseded).
- ADR-0418 (amended: header note only, points at ADR-0421 as a
  prerequisite for its own future Day 2/Day 3 scope extension).

## Preconditions (verify before starting)

- Confirm no other in-flight session is editing `Makefile` or
  `ansible/playbooks/day{0,1}_*.yml` (`git status`/`git log` clean on
  those paths before starting).
- Confirm ADR-0421's number is still free (`ls docs/adr/ | grep 0421`)
  and WP-093 is still the next free WP number
  (`ls docs/roadmap/work-packages/ | sort`).

## Repo changes (step by step)

1. `Makefile`: reorder `DAY0_COMPONENTS`/`DAY1_RUN_COMPONENTS` (lines
   ~11/34), rewrite the surrounding comment blocks to describe the new
   placement, fix the Day 1 help example (`make d1 install keycloak` →
   `make d1 install kiali`, since `keycloak` is no longer a Day 1
   component).
2. `ansible/playbooks/day0_{install,check,reconcile,uninstall}.yml`: move
   `postgresql`/`keycloak`/`aap`/`aap_config` into `day0_components`,
   right after `machines`; remove `smtp`/`nfd`/`nvidia_gpu`/
   `custom_metrics_autoscaler`. Fix `day0_reconcile.yml`'s pre-existing
   missing-`machines` bug while touching this list (present in
   install/check, absent from reconcile since the file was introduced).
   `day0_uninstall.yml` gets the reverse order.
3. `ansible/playbooks/day1_{install,check,reconcile,uninstall}.yml`: move
   `smtp`/`nfd`/`nvidia_gpu`/`custom_metrics_autoscaler` to the head of
   `day1_components`; remove `postgresql`/`keycloak`/`aap`/`aap_config`.
   `openshift_oauth` now sits where `keycloak` used to (right before
   `connectivity_link`). `day1_uninstall.yml` gets the reverse order.
   `day1_build.yml` is untouched (none of the 8 moved components build).
4. Update role READMEs to describe the new placement as current state:
   `ansible/roles/{postgresql,keycloak,aap,aap_config,nvidia_gpu,nfd,
   custom_metrics_autoscaler,smtp,openshift_oauth,connectivity_link}/
   README.md`, plus `ansible/README.md`'s Day 0/Day 1 walkthrough and
   `README.md`'s Day 1 example. Two of these (`custom_metrics_
   autoscaler`, `connectivity_link`) carried pre-existing stale "Day 0
   ordering" claims from before ADR-0060 - corrected as encountered, not
   left further out of date.
5. Fix three hardcoded `make day1 ...`/`make d1 ...` hints that now point
   at the wrong tier for `keycloak`: `ansible/roles/postgresql/tasks/
   backup.yml` (`make d1 install postgresql` → `make d0 install
   postgresql`), `ansible/roles/aap_config/tasks/install.yml` (two
   messages: `make d1 install aap` → `make d0 install aap`, `make d1
   install keycloak` → `make d0 install keycloak`), `ansible/roles/
   openshift_oauth/tasks/install.yml` (two `make day1 check keycloak` →
   `make day0 check keycloak`, one `auto_fix: "make day1 install
   keycloak"` → `auto_fix: "make d0 reconcile keycloak"`, matching this
   repo's standard `make d<N> reconcile <component>` auto_fix convention
   - and `day0_reconcile.yml` now actually carries `keycloak` in its list,
   so the fix is reachable).
6. Author `docs/adr/0421-reshape-day-0-day-1-boundaries-around-always-on-
   infra.md` and add its row to `docs/adr/README.md`'s `## version 0.4`
   table, right after ADR-0420.
7. Amend `docs/adr/0418-*.md`'s header (an `**Amended:**` line noting the
   ADR-0421 dependency) and its `Related ADRs` list (add ADR-0421; also
   fixed a pre-existing broken link to ADR-0354's actual filename/target
   version while touching this section).
8. Run `python3 platform/docs/check_docs.py` and fix whatever it flags -
   it caught two of the six hint-string fixes in step 5 that a plain grep
   missed (`README.md`'s own example, `openshift_oauth`'s `auto_fix`
   string).

## What NOT to touch

- `docs/adr/0056-*.md`, `0060-*.md`, `0354-*.md` - immutable historical
  records once `Implemented`; ADR-0421 exists precisely so these don't
  need editing.
- `docs/roadmap/work-packages/wp-072-*.md`/`wp-073-*.md` - same
  immutability convention; they correctly describe `aap`/`aap-config` as
  Day 1 components, which was true when they were written.
- Any component's own `tasks/{install,check,precheck,uninstall}.yml`
  role-internal logic, or its Helm chart - only which day-tier playbook
  lists the component changes, never how the component itself installs.
- The `-d0`/`-d1` Application-pair naming inside any role (`zuno-
  postgresql-d0`/`-d1`, `zuno-keycloak-d0`/`-d1`, etc.) - this is a
  per-component "operator vs. instance" convention independent of macro
  day-tier (ADR-0060), not touched by this move.
- Live cluster state. This WP's own verification was repo-only; do not
  run `make d0`/`make d1` with a real (non-bogus) component name against
  a shared cluster as part of "just checking the Makefile" - two such
  commands were run by mistake during this WP's own execution
  (`make d0 install keycloak`, `make d1 install nvidia-gpu`) and, while
  both confirmed `changed=0` (no actual mutation), a real component name
  always executes for real against the configured inventory - it does
  not stay local. Use `ansible-playbook --syntax-check` or a bogus
  component name for pure validation instead.

## Acceptance checks

- `ansible-playbook --syntax-check` passes on all 8 touched playbooks.
- `make help`, `make day0`, `make day1` render the new component lists
  (verified: Day 0 ends `...machines postgresql keycloak aap aap-config`;
  Day 1 starts `smtp nfd nvidia-gpu custom-metrics-autoscaler...`).
- `make d0 install bogus-component` / `make d1 install bogus-component`
  fail with the expected diagnostic.
- `make d1 install keycloak` / `make d0 install nvidia-gpu` are rejected
  (wrong tier); `make d0 install keycloak` / `make d1 install nvidia-gpu`
  are accepted by Makefile validation (verified against the live
  Makefile case-statements; the two real executions that happened here
  by mistake also confirm this end to end, with `changed=0`).
- `python3 platform/docs/check_docs.py` passes (`RESULT: PASS - no
  documentation drift detected`).

## Operator / human follow-up

- A full live `make d0 install all` → `make d1 install all` run (or
  `reconcile`/`check` equivalents) against a real cluster, to confirm the
  new sequencing actually reconciles cleanly end to end - not yet done by
  this WP (see "What NOT to touch": live execution was deliberately kept
  out of this session's scope after the accidental live-but-no-op runs
  above). Needs explicit operator go-ahead per this repository's shared-
  cluster convention before running for real.
- Once live-verified, flip ADR-0421's own "Implementation state" section
  from "not yet live-verified end to end" to a dated live-verification
  note, and update `MEMORY.md`.

## Status updates

- 2026-08-30: Repo changes merged, `check_docs.py` green, Makefile
  validation paths exercised without a cluster. State: `Repo work merged,
  live verification pending`.

## Rollback

Pure `git revert` of this WP's commit(s) - no live cluster state is owned
by this WP (no component was actually installed/uninstalled/reconfigured
as a result of it; the two accidental live commands were no-ops against
already-correct state).

## Out of scope / deferred

- Extending AAP Job/Workflow Template execution (ADR-0418) to the
  now-settled Day 0/Day 1 placement, and to Day 2/Day 3 - separate
  follow-up work, unblocked by this WP but not part of it.
- Any further Day 0/Day 1/Day 2 renumbering beyond these 8 named
  components (ADR-0418's originally-floated full reshape) - not decided
  by ADR-0421, which is deliberately narrow in scope.
