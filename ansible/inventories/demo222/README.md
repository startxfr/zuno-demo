# demo222: per-cluster inventory skeleton

demo222 was retired on 2026-10-23. This directory is a documented skeleton: it shows what a second cluster needs,
and CI checks it like any other inventory. Do not run it. `resolve_cluster_name.yml` refuses it against any cluster
whose apps domain does not give `demo222`.

## Layout of a cluster inventory

```
ansible/inventories/<cluster>/
  hosts.yml                     localhost only (every play is local and talks to the cluster API)
  group_vars/all/main.yml       zuno_cluster_name: <cluster>, plus the workstation settings
  group_vars/all/auto.yml       derived names and zuno_repo_root (the same in every inventory)
  group_vars/all/passwords.yml  ADR-0595 password scheme (the same in every inventory)
  cluster.yml                   committed, NON-SECRET per-cluster values (buckets, branch, pins, switches)
  confidential.yml              operator secrets: gitignored, ansible-vault encrypted, never committed
```

Where a value goes:

| File | Read by | Read in AAP | For |
|------|---------|-------------|-----|
| `group_vars/all/*.yml` | Ansible's inventory, on a workstation | no (AAP has its own inventory) | the workstation settings: org, environment, `zuno_security_profile`, `zuno_validate_route_certs` |
| `cluster.yml` | `ansible/tasks/load_cluster_vars.yml` (include_vars) | yes, from the project checkout | everything AAP jobs also need: buckets, branch, version pins, feature switches |
| `confidential.yml` | `ansible/tasks/load_confidential_vars.yml` (include_vars, after `cluster.yml`) | no (never in git) | secrets and anything that must override `cluster.yml` locally |

The cluster's name selects the files. On a workstation it is `zuno_cluster_name` from `group_vars/all/main.yml`,
checked against the live apps domain. In AAP it comes from the apps domain alone. Precedence is the same as
before the per-cluster inventories: `confidential.yml` wins over `cluster.yml`, which wins over `group_vars`.

## Creating demo<N>

1. Copy this directory: `cp -r ansible/inventories/demo222 ansible/inventories/demo<N>`.
2. In `group_vars/all/main.yml`, set `zuno_cluster_name: demo<N>`. It must equal the directory name and the first
   label after `apps.` of the cluster's apps domain. Keep `zuno_validate_route_certs: false` until the cluster's
   ACME wildcard is issued.
3. In `cluster.yml`, set `zuno_gitops_target_revision` to the branch the cluster's Applications follow, and fill
   the ADR-0546 bucket names `zuno-demo<N>-<purpose>` and their region. Copy from
   `ansible/inventories/demo333/cluster.yml` the other keys the cluster needs.
4. Copy `ansible/confidential.example.yml` to `ansible/inventories/demo<N>/confidential.yml`, fill in the values the
   cluster needs and encrypt it (`ansible-vault encrypt`, see `ansible/README.md`). `.gitignore` keeps it out of git.
5. Check offline:
   `python3 platform/gitops/tests/test_cluster_inventories.py` and
   `ansible-playbook --syntax-check -i ansible/inventories/demo<N>/hosts.yml ansible/playbooks/day0_check.yml`.
6. Log in to the cluster (`oc login`), then run every target with `CLUSTER=demo<N>`, for example
   `make CLUSTER=demo<N> d0 check`. `auto.yml` and `passwords.yml` must stay identical to demo333's (the test
   checks it): a per-cluster value goes in `main.yml` or `cluster.yml`.
