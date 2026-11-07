# world_model_gpu (Day 0, local)

ADR-0604 D5, WP-229. The on-demand GPU node of the world-model demo: MachineSet `zuno-gpu-world-model-a`
(g7e.4xlarge, one whole RTX PRO 6000, `nvidia.com/mig.config: all-disabled`, label
`zuno.io/gpu-workload: world-model`, taint `zuno.io/gpu-world-model=true:NoSchedule`), rendered by the Application
`zuno-machines-world-model-d0` from `gitops/charts/machines`, apart from the GPU fleet's `zuno-machines-d0`.

| Command | Switch `zuno_world_model_enabled` | Effect |
|---|---|---|
| `make d0 install world-model-gpu` | `true` | Applies the Application, waits (up to 25 min) for the node Ready, MIG disabled and `nvidia.com/gpu: 1` allocatable |
| `make d0 install world-model-gpu` | `false` | Removes a left-over node; refuses while `zuno-world-model-d1` is installed |
| `make d0 uninstall world-model-gpu` | any | Removes the node (Application, MachineSet, Machine, EC2 instance); refuses while the app is installed |
| `make d0 check world-model-gpu` | any | Reports the node against the switch; reads Nodes only, so it also runs under AAP |

The switch lives in `ansible/clusters/<cluster>.yml` (committed: AAP reads the SCM checkout) and can be overridden
locally from `ansible/confidential.yml`. `zuno_machines_az_override['zuno-gpu-world-model-a']` moves the node to another
zone letter that offers g7e.

**Local only.** The AAP installer credential has no Machine API rights by design
(`gitops/charts/aap-config/templates/clusterrole-installer.yaml`); this role runs with the operator's own credentials,
like `machines`.

**Prerequisite once per cluster.** The GPU Operator DaemonSets must tolerate `zuno.io/gpu-world-model`
(`ansible/roles/nvidia_gpu/tasks/install.yml`), or the node never advertises its GPU. Applying that toleration may
restart the driver on the MIG fleet (`driver.upgradePolicy.autoUpgrade: true`), so it runs in an announced window.

**Cost.** The node bills by the hour. `ZunoWorldModelGpuNodeUpTooLong`
(`gitops/charts/observability/templates/prometheusrule-world-model.yaml`) warns after 8 hours; nothing deletes it
automatically.
