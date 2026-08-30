# WP-103: Model Controller RBAC for who may launch which Job/Workflow Template

- **State:** Done.
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

## Two pre-existing SSO bugs found and fixed during live verification

Nobody had ever completed a real browser/OAuth login into AAP before this
WP - WP-073/WP-094-099's "Keycloak SSO confirmed live" claims only ever
verified that the authenticator/map *objects* existed via the admin API,
never an actual login round-trip. Both bugs below are pre-existing,
unrelated to launch-RBAC itself, and would have blocked **any** SSO login
(including the existing `aap_admin` superuser path) - fixed here because
they blocked this WP's own verification, not because they are in scope.

1. **`ACCESS_TOKEN_URL` pointed at the external HTTPS Route** - the
   gateway pod fetches this URL itself (server-to-server, never the
   user's browser) and has no reason to trust the Route's cert (edge TLS,
   issued by this cluster's own Vault PKI CA - `CN=zuno-demo.internal` -
   not a public CA, and no `REQUESTS_CA_BUNDLE` wires that CA into the
   gateway pod's trust store). Every login failed with
   `CERTIFICATE_VERIFY_FAILED`. Fixed by pointing `ACCESS_TOKEN_URL` at
   the in-cluster HTTP listener (`http://zuno-service.zuno-auth.svc:8080/...`,
   the same one `gitops/charts/keycloak`'s own client-reconcile Job
   already uses) - `AUTHORIZATION_URL` stays external, the user's browser
   is redirected there directly and never touches the gateway pod's trust
   store. Fixed in `install.yml`'s authenticator-creation task (survives
   reinstall) and applied live via a direct `PATCH` (the task is
   create-only, per this role's existing "never PATCHed" convention -
   README.md).
2. **The `aap` Keycloak client had no audience protocol mapper** - only
   the `groups` mapper existed. The ID token's `aud` claim then failed
   `ansible_base`'s audience check (`jwt.exceptions.InvalidAudienceError`)
   after bug 1 was fixed. Fixed by adding an `oidc-audience-mapper`
   (`included.client.audience: aap`) to the `aap` client's
   `protocolMappers` in `realm-zuno.json` - this client is already one of
   the ones ADR-0530's client-reconcile Job merges on every sync, so the
   fix reaches a live realm through the *existing* mechanism, no new
   reconciliation path needed.

**Trap hit applying fix 2 live, for any future session doing the same:**
extracting a client block directly from `realm-zuno.json` and feeding it
to `kcadm update -m` bypasses a REQUIRED step - both `realmimport.yaml`
and `configmap-clients.yaml` `replace "apps.mycluster.example.com"
.Values.clusterBaseDomain` on the RAW FILE TEXT before parsing JSON.
Skipping that step merged the literal placeholder domain into the live
`aap` client's `rootUrl`/`redirectUris`/`webOrigins`, breaking every login
with "Invalid parameter: redirect_uri" until caught and fixed by hand.
Never extract a client block from this file without running it through
the same string-`replace` first (or just let the reconcile Job apply it).

**Separate, unresolved finding, not fixed here:** `consultant-03` (no
`aap_ops`/`aap_admin` group) sees **zero** Job/Workflow Templates -
`allow-authenticated` (`map_type: allow`) only permits login, it does not
grant object-level view the way `install.yml`'s own comment ("viewer-level
until Controller RBAC grants more") and `README.md` claim. That claim
predates this WP and was, like the two bugs above, never live-verified
before now. Practical effect on this WP's own design: the "ungated
templates stay open to any authenticated user" premise behind the
differentiated-gating decision does not hold today for a user with no
`aap_*` group at all - only `aap_ops`/`aap_admin`/superuser can currently
see anything. Left as a documented gap for a future WP (a Team/role
grant for "every authenticated user" is the likely fix, mirroring
`aap-reader-team` but organization-wide) rather than expanded into here.

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

## Operator / human follow-up (live) - completed 2026-08-30

1. Ran the "Live group provisioning" `kcadm` commands above - all 3
   groups created, all 5 users joined, confirmed via `kcadm get
   users/$uid/groups`.
2. `make d0 install aap-config` - first run created the Teams/
   role_definitions/role_team_assignments/authenticator maps cleanly
   (`failed=0`); hit one real bug along the way (`map_type: team` needs a
   `role` field, see below - not yet known to this repo before now) that
   was fixed and re-run to a clean pass; a second re-run confirmed
   idempotent (`changed=0`).
3. Real Keycloak SSO login (full OAuth authorization-code round-trip, not
   just an API check) exercised for one persona per tier and verified via
   `GET /api/controller/v2/job_templates|workflow_job_templates|projects/`
   as that authenticated session:
   - `consultant-03` (`aap_reader`): sees exactly the 7 gated Job
     Templates, all `user_capabilities.start: false` - read-only,
     confirmed, cannot launch. Sees zero ungated templates (see the
     "allow-authenticated" finding above).
   - `paas-dev-01` (`aap_ops`): sees the 7 gated Job Templates + 3 gated
     Workflow Templates + the `zuno-demo` Project, all with
     `start: true`, `edit`/`delete: false` on every object - can launch
     and sync, cannot manage RBAC.
   - `paas-ops-01` (`aap_admin`): `GET /api/gateway/v1/me/` confirms
     `is_superuser: true`.
4. `paas-ops-01` did not lose access during the authenticator-map cutover
   - its `aap_admin` group membership (step 1) was applied and confirmed
   live before the map replacement ran, matching the ordering warning
   above.
5. `consultant-02`/`consultant-01` (the second user in the ops/admin
   tiers) were not individually login-tested - both carry the same group
   membership as the tested persona in their tier and the authorization
   path is entirely group/Team-driven, not per-user, so this is
   considered covered by the tested persona rather than a real gap.

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
