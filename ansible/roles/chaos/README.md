# chaos

Chaos engineering of the cluster infrastructure and of the Zuno platform, with krkn and Tekton. Day 2 component
(`make d2 install|check|uninstall chaos`), Day 3 action (`make d3 chaos infra|platform`, or the AAP workflows
`zuno-day3-chaos-infra-workflow` and `zuno-day3-chaos-platform-workflow`). `make d3 check chaos` is the same read-only
check as `make d2 check chaos`.

The chart is `gitops/charts/chaos` (cerberus, the startx krkn pipelines, the Zuno provider-cut and steady-state Tasks),
applied as `gitops/apps/chaos/application-d1.yaml`. The namespace `zuno-chaos` and its baseline come from
`gitops/charts/namespaces` (`make d0 install namespaces`, then `make d2 install namespaces`); OpenShift Pipelines from
`make d1 install openshift-pipelines`. The targets and the infra tiers are the closed catalogue
`platform/chaos/targets.yaml`, checked by `platform/chaos/targets.py`.

## The switch

`zuno_chaos_enabled` (default `false`, set in `ansible/inventories/<cluster>/cluster.yml`):

- **Off:** `make d2 install chaos` removes the Application if it exists, and nothing else happens.
- **On:** the namespace and the Tekton API must exist; the role applies the Application with the cerberus URL routes of
  the cluster (`chaos_watch_urls`) and waits for cerberus. Nothing runs at install.

## One run

| Step | Playbook | Tasks | What it does |
|---|---|---|---|
| pre-check | `ansible/playbooks/day3_chaos_precheck.yml` | `precheck.yml` | reads only: the request is in the catalogue, the pipeline is installed, no other chaos PipelineRun runs (the lock), cerberus `True`, `check_recovery.py` green, the node of the hog/latency tiers (one, labelled, not control plane, not GPU), each platform target whole and its selector matching a running pod |
| approval | AAP approval node, or the Makefile's TTY pause | | a person reads the pre-check and decides |
| run | `ansible/playbooks/day3_chaos_run.yml` | `run.yml` | ONE PipelineRun `chaos-<kind>-*` in `zuno-chaos` as `chaos-pipeline`; waits; reaps leftovers once it is over; prints `CHAOS_RESULT {json}` and, on a workstation, writes `~/.local/share/zuno/chaos/<run>.json` |
| post-check | `ansible/playbooks/day3_chaos_postcheck.yml` | `postcheck.yml` | reads only: each target's workload ready within its `recover_within`, no chaos policy left, nodes Ready without pressure and no helper pod (infra), cerberus `True` again, `check_recovery.py`, and the golden-path probe of each target (on a workstation; AAP prints the command); prints `CHAOS_POSTCHECK {json}` |

Variables: `chaos_kind` (`infra` | `platform`), `chaos_tier` (infra: `pods` | `hog` | `latency`), `chaos_targets`
(platform: catalogue ids, comma separated; a provider cut runs alone). The plan comes from
`python3 platform/chaos/targets.py plan`:

| Request | Pipeline | Scenarios |
|---|---|---|
| `infra`, tier `pods` | `chaos-infra` | `10-pods-monitoring`, `11-pods-ingress`, `12-pods-apiserver` |
| `infra`, tier `hog` | `chaos-infra` | `20-hog-cpu-worker`, `21-hog-memory-worker` (on the node labelled `zuno.io/chaos-target=true`) |
| `infra`, tier `latency` | `chaos-infra` | `22-network-latency-worker` (same node) |
| `platform`, pod targets | `chaos-application` | the target ids, run in alphabetical order |
| `platform`, `provider-cut-mistral` | `zuno-chaos-provider-cut` | the cut, then the ai-gateway whole again |

The cerberus signal is read through the API server's service proxy
(`oc get --raw /api/v1/namespaces/zuno-chaos/services/http:cerberus:8080/proxy/`): the same call from a workstation and
from an AAP execution environment, no pod to start, no route. The chart's Role `zuno-chaos-signal-reader` grants it to
the two AAP credentials; the namespace baseline admits the API server (`allowApiServerWebhooks`). The pre- and
post-check need `oc` (`check_recovery.py` and the signal), so their AAP job templates use the custom execution
environment.

## Stop and clean up

A failed post-check leaves the workflow failed; `make d3 check recovery` gives the next step. The provider cut removes
its AdminNetworkPolicy itself (trap) and its Pipeline reaps every policy labelled `zuno.io/chaos=true` in `finally`;
`run.yml` reaps krkn helper pods of `zuno-chaos` once the run is over. `make d2 uninstall chaos` removes the Application
(Tasks, Pipelines, cerberus, RBAC) and any chaos policy left; the PipelineRuns stay as the record of the runs, and the
node label is removed by hand (`oc label node <node> zuno.io/chaos-target-`).
