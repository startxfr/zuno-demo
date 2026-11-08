# WP-229: On-demand world-model GPU pool (delivers ADR-0604 D5)

- **State:** Operator pending
- **ADRs:** ADR-0604
- **Depends on:** WP-228
- **Blocks:** WP-232, WP-235
- **Estimated files touched:** ~14

> Execute this brief as a standalone task from the repository root.

## Goal

A third GPU node (one full RTX PRO 6000, no MIG) that exists only while `zuno_world_model_enabled` is true: created by
`make d0 install world-model-gpu`, deleted with its EC2 instance by `make d0 uninstall world-model-gpu`, and left alone by
`make d0 install all` while the switch is off.

## ADR references

ADR-0604 D5 items 1 to 4, §1.2 (Machine API boundary, driver upgrade policy).

## Preconditions

- Read `gitops/charts/machines/values.yaml` (pool list, `zuno-gpu-burst-a` shape), `gitops/apps/machines/application-d0.yaml`
  (`ignoreDifferences` on replicas), `ansible/roles/machines/tasks/install.yml` and
  `ansible/tasks/resolve_cluster_aws_identity.yml`.
- The vendored `cluster-machine` chart renders every list entry; there is no per-entry `enabled` flag.

## Repo changes

1. `gitops/apps/machines-world-model/application-d0.yaml`: name and releaseName `zuno-machines-world-model-d0`, path
   `gitops/charts/machines`, `machineSet.enabled: true`, `machineAutoscaler.enabled: false`,
   `cluster.autoscaler.enabled: false` (the ClusterAutoscaler singleton stays owned by `zuno-machines-d0`), the same
   `ignoreDifferences`/`RespectIgnoreDifferences` block, prune and selfHeal.
2. `ansible/roles/world_model_gpu/` with `install.yml`, `uninstall.yml`, `precheck.yml`, `defaults/main.yml`:
   - load `ansible/tasks/load_cluster_vars.yml`, then `ansible/confidential.yml` if present (stat + `include_vars`, as
     `check_confidential_var_loaders` requires);
   - switch off: if `zuno-world-model-d1` exists, fail and name `make d2 uninstall world-model`; otherwise delete
     `zuno-machines-world-model-d0` if present and stop;
   - switch on: `resolve_cluster_aws_identity.yml`; build a list with **only** `zuno-gpu-world-model-a`
     (`g7e.4xlarge`, AZ `a` unless `zuno_world_model_gpu_az` or `zuno_machines_az_override` says otherwise, group `gpu-world-model`, gp3 250 GB,
     replicas 1, labels `nvidia.com/mig.config: all-disabled` and `zuno.io/gpu-workload: world-model`, taint
     `zuno.io/gpu-world-model=true:NoSchedule`); always inject `machineSet.list`, `cluster.id` and `cluster.region` (the
     chart default list would otherwise render a second copy of the fleet); `apply_gitops_app.yml`; wait (25 min) for the
     node Ready, `nvidia.com/mig.config.state=success` and allocatable `nvidia.com/gpu: 1`;
   - uninstall: refuse while `zuno-world-model-d1` exists; `delete_gitops_app.yml` with
     `gitops_app_delete_wait_timeout: 600`; wait until no Machine of the set remains.
3. `Makefile`: `world-model-gpu` in `DAY0_COMPONENTS`; `ansible/playbooks/day0_{install,check,uninstall}.yml` lists (last).
4. `ansible/roles/nvidia_gpu/tasks/install.yml`: add `{key: zuno.io/gpu-world-model, operator: Exists, effect: NoSchedule}`
   to the DaemonSet tolerations.
5. `gitops/charts/namespaces/values.yaml`: `zuno-world-model` (display name, ADR-0604 description,
   `zuno.io/managed: "true"`, `zuno.io/experience-client: "true"`, no injection label, `resourceQuota` with
   `requests.nvidia.com/gpu: "1"` and CPU/memory ceilings).
6. `ansible/clusters/demo333.yml`: `zuno_world_model_enabled: false`; a commented line in `ansible/confidential.example.yml`.
7. Cost alert `ZunoWorldModelGpuNodeUpTooLong` (warning, 8 h) in `gitops/charts/observability/templates/`, on
   `time() - mapi_machine_created_timestamp_seconds{name=~"zuno-gpu-world-model-.*"}`; confirm the metric name read-only first.
8. `ansible/roles/world_model_gpu/README.md` and a line in `gitops/charts/machines/README.md`.

## Operator steps (each with the user's own go)

1. Read-only first: how the GPU Operator reacts to a DaemonSet template change (`upgradePolicy.autoUpgrade: true`,
   driver DaemonSet `OnDelete`).
2. Announced maintenance window (peers told): `make d1 install nvidia-gpu`; watch the driver pods on both MIG nodes and the
   predictors in `zuno-ai-run` until they are Ready again.

## Verification

`helm template` of the machines chart with the injected one-entry list renders exactly one MachineSet and no autoscaler;
`ansible-playbook --syntax-check` on the day-0 playbooks; `python3 -B platform/docs/check_docs.py`. The live create/delete
cycle is proven in WP-232.

## Result (2026-11-08)

The toleration window ran on 2026-11-07 (about 30 minutes, the drivers restarted, no model pod evicted). The node came up in
eu-central-1b: eu-central-1a answered `InsufficientInstanceCapacity` for `g7e.4xlarge` and the machine controller retried
about 2900 times, so the cluster file now carries `zuno_world_model_gpu_az: "b"` (a variable of its own, because
`zuno_machines_az_override` is one map that a workstation's `confidential.yml` replaces whole). The node was Ready with one
whole GPU about 20 minutes after the first apply. The removal path is proven after the 2026-11-09 demo, when the node is deleted.
