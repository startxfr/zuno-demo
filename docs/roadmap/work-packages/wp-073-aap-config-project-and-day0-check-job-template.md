# WP-073: Register the zuno-demo Project and day0_check Job Template in AAP

- **State:** Not started. Blocked on WP-072's live CRD inventory (its
  step 10) - the mechanism this WP implements (Path A vs Path B below) is
  not chosen until that inventory is in hand.
- **ADRs:** ADR-0354 (clause 4 and clause 6's AAP-side authenticator
  question)
- **Depends on:** WP-072 (`aap` component live, Ready, and its CRD
  inventory recorded).
- **Unblocks:** WP-074/ADR-0355 (`mcp-aap` needs a working Job Template
  and a scoped launch token to wrap).
- **Estimated files touched:** Path A ~8 (role: 3, chart: ~3, apps: 2);
  Path B ~6 (role: 3, `ansible/requirements.yml`: 1, docs: ~2) - final
  count depends on which path WP-072's inventory selects.

> Execute this brief as a standalone task from the repository root. Read
> ADR-0354 clause 4 and clause 6 in full before starting, and read
> WP-072's recorded CRD inventory findings first - **do not start
> implementation until that inventory exists and has been reviewed.** If
> the inventory shows a mechanism this brief did not anticipate, stop and
> report before writing code, per the standing instruction to be warned
> before any new Ansible-executed action code is authored.

## Goal

Register exactly two things in the live AAP instance once `aap` (WP-072)
is Ready:

1. a **Project** named `zuno-demo`, pointing at
   `https://github.com/startxfr/zuno-demo.git` @ `main`, with SCM
   auto-sync;
2. a **Job Template** named `zuno-day0-check`, running
   `ansible/playbooks/day0_check.yml` against this OpenShift cluster.

Nothing beyond these two objects is in scope (ADR-0354 clause 4's scope
boundary - the other seven top-level playbooks named in the original,
pre-amendment ADR draft are explicitly cut).

## ADR references

Primary: [docs/adr/0354-add-ansible-automation-platform-as-a-day-1-component.md](../../adr/0354-add-ansible-automation-platform-as-a-day-1-component.md),
clause 4 (mechanism/scope) and clause 6 (AAP-side OIDC authenticator, if
this WP's inventory places it here).

Related: ADR-0048 (discovery-over-hardcoding, applied here to the
mechanism choice itself), `ansible/tasks/vault_seed_if_missing.yml` (the
assert-or-seed idempotency shape Path B must reuse if selected).

## Preconditions (verify before starting)

- WP-072 `Done`, `aap` component live: `oc get ansibleautomationplatform
  -n zuno-aap` Ready.
- WP-072's step-10 CRD inventory output is available and reviewed:
  `oc api-resources | grep -Ei 'ansible|aap|awx'` output, and the
  `oc explain` output for any `JobTemplate`/`AnsibleJob`/
  `AnsibleProject`-shaped type found.
- `python3 platform/docs/check_docs.py` exits 0.

## Decision checkpoint: Path A vs Path B

Read WP-072's recorded inventory and pick exactly one path. Do not
implement both.

### Path A - CRDs exist (preferred)

If the inventory shows a **separate AAP resource operator** (distinct OLM
package from the platform operator WP-072 installed) publishing
Kubernetes CRDs for Project/JobTemplate-shaped objects:

1. That resource operator becomes a second Subscription. Decide whether
   it belongs in `aap`'s own `-d0` Application (same chart, an additional
   toggle) or a dedicated `-d0` half of `aap-config` itself - prefer
   keeping it inside `aap-config`'s own `-d0`/`-d1` pair so `aap` (WP-072)
   stays exactly as already shipped and does not need a follow-up change.
2. `ansible/roles/aap_config/tasks/install.yml`: apply `zuno-aap-config-d0`
   (resource-operator subscription) then `zuno-aap-config-d1` (the
   Project + JobTemplate CRs) via `apply_gitops_app.yml`, same
   wait-Synced+Healthy-between pattern as every other component.
3. `gitops/charts/aap-config/`: `templates/project.yaml` (repo URL,
   branch, SCM auto-sync toggle), `templates/jobtemplate-day0-check.yaml`
   (playbook path, credential ref, inventory ref, survey for
   `target_component` mirroring the Makefile's optional argument -
   ADR-0354 clause 4 keeps this single-template scope, so no survey
   fan-out beyond that one variable).
4. `gitops/apps/aap-config/application-d0.yaml` (sync-wave `-154`) /
   `application-d1.yaml` (`-153`).
5. Machine/kubeconfig credential and inventory: rendered as CRs if the
   resource operator's CRD set covers them; otherwise seed them via a
   narrowly-scoped `k8s_exec`/API call in `install.yml`, following the
   precedent `ansible/roles/postgresql`'s monitoring-role Job seeding
   already sets (SQL/config mounted from a ConfigMap, not inlined - avoid
   the `$$`-mangling class of bug documented in that role's recent fix
   commits).

### Path B - no CRDs exist (fallback)

If the inventory shows Project/JobTemplate are Controller-API-only
objects with no Kubernetes CRD anywhere:

**Stop and get explicit confirmation from the user before writing this
path's Ansible action code** - this is the "prevent me before coding an
Ansible action" gate the user set for this project.

If confirmed:

1. Add `infra.aap_configuration` to `ansible/requirements.yml`.
2. `ansible/roles/aap_config/tasks/install.yml`: bootstrap an admin API
   token from `zuno/aap/admin` (Vault), then use
   `infra.aap_configuration.project`/`.job_template` modules with an
   assert-or-seed idempotency shape mirroring
   `ansible/tasks/vault_seed_if_missing.yml` - check whether the Project/
   Job Template already exists (by name) before creating it, so a re-run
   never duplicates or clobbers manual edits made in the AAP UI.
3. `ansible/roles/aap_config/tasks/precheck.yml`: query the Controller API
   for the Project's last SCM sync status and the Job Template's
   existence; never fail; end with `ansible/tasks/record_state.yml`.
4. `ansible/roles/aap_config/tasks/uninstall.yml`: delete the Job
   Template then the Project via the same collection, in reverse order.
5. No `gitops/charts/aap-config` or `gitops/apps/aap-config/` in this
   path - `aap-config` is Ansible-only, day0-neutral (it has no Day 0
   half at all, matching ADR-0354's description).

### Both paths

- **Machine credential:** the Controller/resource-operator's ability to
  reach this cluster must use a credential no more broadly scoped than
  the existing Ansible bootstrap's own cluster-admin kubeconfig already
  requires - not a new, separately-privileged identity (ADR-0354's
  Security considerations).
- **AAP-side Keycloak authenticator (clause 6):** if the inventory shows
  an authenticator CRD (Path A) or an `infra.aap_configuration`-covered
  authenticator resource (Path B), wire it here, pointing at the `aap`
  Keycloak client WP-072 already registered. If neither exists, leave
  this explicitly undone and record it as a known gap in this WP's State
  section - do not fall back to a manual one-time UI setup without
  flagging it as such.

## Repo changes (step by step)

1. Implement the selected path's role/chart/apps as above.
2. `Makefile` `DAY1_RUN_COMPONENTS`: insert `aap-config` immediately after
   `aap`.
3. `ansible/playbooks/day1_install.yml`/`day1_check.yml`: insert
   `aap_config` immediately after `aap` in `day1_components`.
4. `ansible/playbooks/day1_uninstall.yml`: insert `aap_config` in the
   reverse-order list immediately *before* `aap`.
5. Docs: `gitops/apps/README.md` (if Path A), `ansible/README.md`,
   `docs/platform/installation.md`.
6. Execution environment check: confirm the default AAP execution
   environment includes `kubernetes.core` and `community.hashi_vault` (
   `day0_check.yml`'s own dependencies, per `ansible/requirements.yml`).
   If it does not, this is a blocking finding - report it rather than
   building a custom execution environment inside this WP without
   confirming that's wanted.

## What NOT to touch

- Do not register Job Templates for any playbook other than
  `day0_check.yml` - ADR-0354 clause 4's scope boundary is explicit about
  this cut.
- Do not implement both Path A and Path B.
- Do not write Path B's Ansible action code without the explicit
  user confirmation the Decision checkpoint requires.
- Do not route `make day0|d0`/`make day1|d1` execution through this Job
  Template - that is ADR-0418 (v0.4), unrelated to this WP.
- Do not widen the Machine credential beyond what the existing cluster-
  admin bootstrap kubeconfig already grants.

## Acceptance checks

1. `make day1 install aap-config` (or the Ansible-only equivalent for
   Path B) completes; in the AAP UI, Project `zuno-demo` shows a
   successful SCM sync against `main`.
2. Job Template `zuno-day0-check` exists, targeting
   `ansible/playbooks/day0_check.yml`.
3. Manually launch `zuno-day0-check` from the AAP UI/API - the run
   succeeds, and its output is consistent with a local `make d0 check`
   run against the same cluster.
4. `make day1 check aap-config` reports installed; idempotency holds
   under a second `make day1 install aap-config` (no `day1_reconcile.yml`
   exists).
5. `python3 platform/docs/check_docs.py` exits 0.
6. If the AAP-side Keycloak authenticator was wired: log into the AAP
   Gateway via Keycloak SSO with a `zuno` realm persona.

## Operator / human follow-up

1. Deploy the GitOps/Ansible change.
2. Manually launch `zuno-day0-check` once and confirm output.
3. If Path B was used, confirm no duplicate Project/Job Template was
   created on a second run (re-run `make day1 install aap-config` and
   diff the Controller API's object count before/after).

## Status updates

On repository merge but before live confirmation:

- WP-073 -> `Repo work merged, live verification pending`.

After all live acceptance checks pass:

- WP-073 -> `Done`.
- ADR-0354 -> `Implemented` (both `aap` and `aap-config` live; unless the
  Keycloak authenticator gap from the Decision checkpoint remains open, in
  which case record that explicitly rather than claiming full
  implementation).
- Update `docs/roadmap/v0.1-v0.3-implementation-roadmap.md` and
  `MEMORY.md`.
- Run `python3 platform/docs/check_docs.py` again.

## Rollback

1. `make day1 uninstall aap-config` (or the Path B role's `uninstall.yml`).
2. Revert the Git commit if the chart/role itself is at fault.
3. `aap` (WP-072) is unaffected by this rollback - it stays installed.

## Out of scope / deferred

- `mcp-aap` (agent-facing audit tools wrapping this Job Template) -
  WP-074/ADR-0355.
- Any Job Template beyond `zuno-day0-check`.
- Routing `make day0|d0`/`make day1|d1` execution through AAP - ADR-0418
  (v0.4).
