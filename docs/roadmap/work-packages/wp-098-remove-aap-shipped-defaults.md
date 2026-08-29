# WP-098: Remove AAP's shipped default Project/Job Template/Inventory

- **State:** Repo work merged - live verification pending.
- **ADRs:** ADR-0354 (clause 4, Project/Job Template registration).
- **Depends on:** WP-073 (Gateway URL/admin-password bootstrap this task
  reuses).
- **Unblocks:** none.
- **Estimated files touched:** 3 (new `tasks/remove_aap_defaults.yml`,
  `tasks/install.yml`, `README.md`).

> Execute this brief as a standalone task from the repository root.

## Goal

A fresh AAP install ships "Demo Project" / "Demo Job Template" (pointing
at `github.com/ansible/ansible-tower-samples`) and, on some versions, a
"Demo Inventory" - all organization-less, all unrelated to this repo.
Remove them as part of `aap-config`'s own install, idempotently, so a
live Controller only ever shows objects this repo actually manages.

This closes out the operator's explicit ask following the
`make d0 install aap-config` failure investigation: confirm every
`tower.ansible.com` CRD kind (`AnsibleProject`, `AnsibleInventory`,
`AnsibleCredential`, `JobTemplate`, `WorkflowTemplate`) is already
deployed declaratively via ArgoCD/Helm (it is - WP-072/073/094/095), and
add cleanup of AAP's own shipped defaults as an ansible-task-driven step
(not a CR - see below for why).

## ADR references

ADR-0354 clause 4 (Project/Job Template registration) - this WP is a
hygiene addition to that clause's existing scope, not a new clause.

## Preconditions (verify before starting)

- Confirmed live 2026-08-30: `oc explain jobtemplates.tower.ansible.com.spec`
  and `oc explain ansibleprojects.tower.ansible.com.spec` list no `state`
  field (unlike `ansibleinventories.tower.ansible.com.spec`, which does:
  `enum: present, absent, exists`). A uniform "declare `state: absent` in
  the chart" approach can't cover all three object kinds, hence the API
  route for all three, for consistency.
- Confirmed live 2026-08-30 against `api.demo222.startx.fr`'s AAP: "Demo
  Project" (id 5, `organization: null`) and "Demo Job Template" (id 6,
  `project: 5`, `organization: null`) exist; no separate "Demo Inventory"
  object exists on this install (defensively checked for anyway, in case
  a different AAP version ships one).

## Repo changes (step by step)

1. New `ansible/roles/aap_config/tasks/remove_aap_defaults.yml`: GET each
   of `job_templates?name=Demo Job Template`, `projects?name=Demo
   Project`, `inventories?name=Demo Inventory` (in that order - the
   Controller API 400s deleting a Project a Job Template still
   references, so the Job Template is looked up and deleted first), then
   DELETE by resolved id wherever `count > 0`. Same idempotent
   `ansible.builtin.uri` Basic-auth pattern as the rest of `aap_config`.
2. `ansible/roles/aap_config/tasks/install.yml`: `include_tasks:
   remove_aap_defaults.yml` right after "wait for the Gateway API to
   answer" - before organization creation, since this cleanup doesn't
   depend on the `zuno` organization/Project/Job Template this role
   registers further down.
3. `ansible/roles/aap_config/README.md`: new row in the CR-vs-API
   mechanism table.

## What NOT to touch

- The "Ansible Galaxy" credential (id 2 on demo222, `organization: null`)
  - a shipped default too, but not named in scope and still potentially
    useful (collection/role dependency resolution); only the three
    explicitly-named objects are removed.
- The "Default" organization itself - confirmed live to hold neither
  Demo Project nor Demo Job Template (both `organization: null`, not
  `68`/Default) on this install; removing an organization is a larger,
  unrequested blast radius for zero observed benefit here.
- `gitops/charts/aap-config/templates/*.yaml` - none of the three default
  objects are represented as CRs this repo manages, so there is nothing
  to add a `state: absent` entry for; this is purely an
  ansible-task-driven cleanup of objects AAP itself created outside any
  chart.

## Acceptance checks

- `ansible-playbook --syntax-check ansible/playbooks/day0_install.yml`
  passes (exercises the new task file through the `aap_config` role).
- `python3 platform/docs/check_docs.py` passes.
- Live (operator follow-up): after `make d0 install aap-config`,
  `GET /api/controller/v2/job_templates/` and `/projects/` no longer list
  "Demo Job Template"/"Demo Project"; re-running the same install is a
  no-op (both GETs return `count: 0`, no DELETE attempted).

## Operator / human follow-up

- Run `make d0 install aap-config` (already the pending live-verification
  step from WP-094/095/097) and confirm the Demo objects are gone
  afterward via the Controller API or UI.

## Status updates

- 2026-08-30: Repo changes merged (offline `--syntax-check` green). State:
  `Repo work merged - live verification pending`.

## Rollback

`git revert` - the deleted Demo objects are AAP's own out-of-the-box
seed data, not repo-managed state; nothing else in this repo references
them, so there is nothing to restore even if reverted.

## Out of scope / deferred

- WP-095's own open item (workflow_nodes reconciliation not yet
  live-confirmed) - unrelated, still pending on the same
  `make d0 install aap-config` run.
- WP-098 was going to be the tentative number for live resource tuning on
  `zuno-aap` per WP-097's own "Out of scope" note; that work remains
  unstarted and will take the next free number (WP-099) when it begins.
