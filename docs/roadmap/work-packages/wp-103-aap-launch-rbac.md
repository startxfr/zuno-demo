# WP-103: Model Controller RBAC for who may launch which Job/Workflow Template

- **State:** Repo work merged.
- **ADRs:** ADR-0418 (Security considerations - Phase 3/4 launch-RBAC).
- **Depends on:** WP-094 (Job Templates registered), WP-097 (launch
  mechanism itself).
- **Unblocks:** ADR-0418 clause 1's Phase 3 (`day0/day1 install`) and
  Phase 4 (`uninstall`/`reinstall`) - both are explicitly gated on this
  existing before those verbs get exposed as Job Templates at all.

> Execute this brief as a standalone task from the repository root.

## Goal

Model, inside Controller's own RBAC (Organizations/Teams, Job/Workflow
Template `execute`/`view` role assignments), *who* may launch each gated
Job/Workflow Template - not just what the launched job can do to the
cluster (the `zuno-cluster-reader`/`zuno-aap-installer` credential tiers
WP-094 already built, which govern the launched job's own permissions,
not who's allowed to click launch). ADR-0418's own Security
considerations section flagged this as open since its first draft;
WP-094/095/097/099 all explicitly deferred it as out of scope while
proving the launch mechanism itself works.

## ADR references

ADR-0418, Security considerations: "*who* (which Controller user/team) may
launch each Job Template ... remains open, unaddressed by WP-094 and still
deferred to whichever WP implements Phase 3/4 for real." This is that WP.

## Design (finalized 2026-08-30)

Three Keycloak groups drive Controller RBAC via the existing Keycloak SSO
authenticator (`install.yml:963-1116`):

- **`aap_admin`** - full Controller superuser, via a single `is_superuser`
  authenticator map triggered by this group (replaces the old
  `superuser-ocp-paas-ops` map - `ocp-paas-ops` is a cluster-access
  dimension, orthogonal to AAP RBAC, and is no longer AAP's source of
  truth for "administers AAP"). No Controller Team needed.
- **`aap_ops`** - maps (authenticator `map_type: team`) onto the
  `aap-ops-team` Controller Team: view+execute on every *gated* Job/
  Workflow Template, view+sync (`awx.update_project`) on the `zuno-demo`
  Project.
- **`aap_reader`** - maps onto the `aap-reader-team` Controller Team:
  view-only on the same gated objects. A dedicated Team was chosen over
  relying on the pre-existing `allow-authenticated` viewer default, for
  declared/auditable state even though the practical effect is similar.

**Gating is differentiated, not uniform** - only the higher-risk verbs are
restricted; `check`/`build`/plain read-mostly templates stay open to
every authenticated user via the pre-existing `allow-authenticated` map
(`order: 10`), unchanged.

### Partition of the 14 Job Templates + 7 Workflow Templates

Source: `gitops/charts/aap-config/values.yaml` (`jobTemplates`/
`workflowTemplates`), cross-checked against each entry's credential tier
in the same file.

| Job Template | Credential tier | Gated? |
|---|---|---|
| `zuno-day0-check` | cluster-reader | No |
| `zuno-day1-check` | cluster-reader | No |
| `zuno-day1-build` | aap-installer | No (WP-103 brief exempts build) |
| `zuno-day1-install` | aap-installer | **Yes** |
| `zuno-day1-reconcile` | aap-installer | **Yes** |
| `zuno-day2-check` | cluster-reader | No |
| `zuno-day2-build` | aap-installer | No (WP-103 brief exempts build) |
| `zuno-day2-install` | aap-installer | **Yes** |
| `zuno-day3-test` | cluster-reader | No |
| `zuno-day3-stresstest` | aap-installer | **Yes** |
| `zuno-day3-backup` | aap-installer | **Yes** |
| `zuno-day3-restore` | aap-installer | **Yes** |
| `zuno-day3-check` | cluster-reader | No |
| `zuno-day3-sign` | aap-installer | **Yes** |

Decision on the 4 ambiguous Day 3 templates (stresstest/backup/restore/
sign): all 4 gated, by strict coherence with the existing
`zuno-aap-installer` (mutating) credential tier rather than a per-case
risk judgment - every mutating-tier template is gated except
`*-build` (explicitly exempted by this WP's own original brief).

| Workflow Template | Underlying Job Template | Gated? |
|---|---|---|
| `zuno-day1-install-workflow` | zuno-day1-install | **Yes** |
| `zuno-day1-check-workflow` | zuno-day1-check | No |
| `zuno-day1-reconcile-workflow` | zuno-day1-reconcile | **Yes** |
| `zuno-day1-build-workflow` | zuno-day1-build | No |
| `zuno-day2-install-workflow` | zuno-day2-install | **Yes** |
| `zuno-day2-check-workflow` | zuno-day2-check | No |
| `zuno-day2-build-workflow` | zuno-day2-build | No |

No Day 3 Workflow Templates exist.

### User -> group assignments

| User | Group |
|---|---|
| `paas-ops-01`, `consultant-01` | `aap_admin` |
| `paas-dev-01`, `consultant-02` | `aap_ops` |
| `consultant-03` | `aap_reader` |

## Live group provisioning (Keycloak)

**ADR-0530 clause 4 explicitly excludes groups from its client-
reconciliation Job** ("Groups, users, realm roles, identity providers,
client scopes and realm settings remain create-only and are not
reconciled") - this WP does not amend that ADR or its Job. Group
creation and membership are instead:

1. Declared in `gitops/charts/keycloak/files/realm-zuno.json` (the 3
   `aap_*` groups and the 5 users' `groups[]` arrays) - this only seeds a
   **future fresh install** via the create-only `KeycloakRealmImport`,
   it does not reach an already-live realm.
2. Applied to the live realm **by hand, once**, via `kcadm.sh` inside the
   Keycloak pod - same precedent as the earlier hand-applied group edit
   referenced in ADR-0530's Context (commit `de1524e1`). This is a
   deliberate, documented divergence, not an oversight - see ADR-0530
   clause 4's own reasoning for why groups are not auto-reconciled.

```bash
oc exec -it -n zuno-auth zuno-0 -c keycloak -- bash -c '
  KCADM=/opt/keycloak/bin/kcadm.sh
  CFG="--config /tmp/kcadm.config"
  $KCADM config credentials $CFG \
    --server http://zuno-service.zuno-auth.svc:8080 --realm master \
    --user "$(oc get secret keycloak-admin -n zuno-auth -o jsonpath="{.data.username}" | base64 -d)" \
    --password "$(oc get secret keycloak-admin -n zuno-auth -o jsonpath="{.data.password}" | base64 -d)"

  $KCADM create groups -r zuno $CFG -s name=aap_admin
  $KCADM create groups -r zuno $CFG -s name=aap_ops
  $KCADM create groups -r zuno $CFG -s name=aap_reader

  for pair in "consultant-01:aap_admin" "paas-ops-01:aap_admin" \
              "paas-dev-01:aap_ops" "consultant-02:aap_ops" \
              "consultant-03:aap_reader"; do
    user="${pair%%:*}"; group="${pair##*:}"
    uid=$($KCADM get users -r zuno $CFG -q username="$user" --fields id --format csv --noquotes | tr -d "\r\" ")
    gid=$($KCADM get groups -r zuno $CFG -q search="$group" --fields id --format csv --noquotes | tr -d "\r\" ")
    $KCADM update "users/$uid/groups/$gid" -r zuno $CFG
  done
'
```

Verify `kcadm.sh help update` for the group-join call shape against this
cluster's Keycloak version before running - not yet exercised elsewhere
in this repo. **Run this before the authenticator-map cutover below**:
until `paas-ops-01`'s `aap_admin` membership is live, cutting over the
superuser map from `ocp-paas-ops` to `aap_admin` would drop that user's
superuser access.

To remove, mirror with `kcadm delete groups -r zuno --id <gid>`.

## Live verification findings (2026-08-30, feeds `wire_launch_rbac.yml`'s header comment)

- Teams are GATEWAY resources (`/api/gateway/v1/teams/`, `organization`
  required per OPTIONS) that sync down into Controller
  (`/api/controller/v2/teams/`) with a **different id** - confirmed live:
  the `zuno` organization itself already has gateway id `2` vs controller
  id `69` on this cluster, same cross-id trap as Users.
- `/api/controller/v2/role_team_assignments/` exists (200), mirrors
  `role_user_assignments/`.
- Exact permission strings from `/api/controller/v2/role_metadata/`'s
  `allowed_permissions`: `awx.project` -> `awx.view_project`,
  `awx.update_project` (there is no separate "sync" permission - sync IS
  update); `awx.workflowjobtemplate` -> `awx.view_workflowjobtemplate`,
  `awx.execute_workflowjobtemplate` (no underscores splitting
  workflow/job/template, unlike `awx.jobtemplate`'s own strings - do not
  guess this by analogy).
- An authenticator map's `map_type: team`/`organization` fields are both
  plain NAME strings (not ids), confirmed via `OPTIONS` on
  `/api/gateway/v1/authenticator_maps/`.
- `map_type: team` also **requires** a `role` field (not surfaced by
  `OPTIONS`'s help_text - only found via the live 400: "You must specify
  a role with the selected map type"). The value is the NAME of one of
  two built-in managed role_definitions on `shared.team`: `"Team Member"`
  (inherits every role_team_assignment already granted to the Team - used
  here) or `"Team Admin"` (also grants change/delete on the Team itself -
  not needed).

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0.
- `ansible-playbook --syntax-check ansible/playbooks/day0_install.yml`
  passes (aap_config role, includes the new task files).
- `ansible-lint` on the new/changed task files shows no findings beyond
  this repo's pre-existing `name[casing]`/`name[template]` style (lower-
  case `role | verb` task names, mid-name Jinja) - both already pervasive
  throughout `install.yml`, not new to this WP.
- `python3 -c "import json; json.load(open('gitops/charts/keycloak/files/realm-zuno.json'))"`
  still succeeds (the realm file stays valid JSON).

## Operator / human follow-up (live)

1. Run the "Live group provisioning" `kcadm` commands above.
2. `make d0 install aap-config` (idempotent - re-run should change
   nothing on a second pass, only 400 "already exists" branches).
3. Log in via Keycloak SSO as `consultant-03`: read-only on the gated
   templates/Project, no Launch button/403 on launch; ungated templates
   (check/build/test) remain launchable via `allow-authenticated`,
   unchanged.
4. Log in as `paas-dev-01`/`consultant-02`: can launch gated templates
   and trigger a Project sync; no access to Controller's own RBAC/Teams/
   Users admin screens.
5. Log in as `paas-ops-01`/`consultant-01`: full superuser.
6. Confirm `paas-ops-01` did not lose access during the authenticator-map
   cutover (check `ocp-paas-ops` still grants cluster RBAC and `aap_admin`
   independently grants AAP RBAC).

## Out of scope / deferred

- Any change to the `zuno-cluster-reader`/`zuno-aap-installer` credential
  tiers themselves (WP-094) - this WP is about *who* can launch, not what
  the launch can do.
- Actually flipping Phase 3/`install` verbs onto AAP as the primary path -
  clause 1 gates that on Phase 1/2 reliability, now demonstrated, but is a
  separate decision from having launch-RBAC ready.
- Automating Keycloak group reconciliation (would require amending
  ADR-0530 clause 4) - out of scope by explicit decision, see "Live group
  provisioning" above.
