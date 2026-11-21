# WP-316: Run chaos pipelines on demo333, and the two chaos demos

- **State:** Repo work in review (2026-11-21: in progress, nothing merged; the demo pages and their files are on the local branch `chaos-demo-pages`, the chaos component on the branch `chaos-demos`; nothing has run on a cluster)
- **ADRs:** [ADR-0626](../../adr/0626-chaos-engineering-with-krkn-and-tekton-pipelines.md)
- **Depends on:** [WP-291](wp-291-install-openshift-pipelines-and-build-praxis-ai-from-source.md) (OpenShift Pipelines on demo333)
- **Related:** [WP-311](wp-311-inflict-bounded-disruptions-beside-the-stress-load.md) (its targets move to the chaos catalogue; it is marked superseded only after a live krkn run), [WP-317](wp-317-improve-the-stress-tool-after-the-2026-11-21-campaign.md), [WP-318](wp-318-lift-the-limits-found-by-the-2026-11-21-stress-campaign.md), [ADR-0624](../../adr/0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md), [ADR-0536](../../adr/0536-live-node-failover-drill-for-qwen-model-fallback.md)
- **Target:** v0.18
- **Estimated files touched:** ~40: `gitops/charts/chaos/` (wrapper chart, vendored tgz, two Zuno Tasks), `gitops/apps/chaos/`, `ansible/roles/chaos/`, the Makefile, `gitops/charts/namespaces/values.yaml`, the AppProject rights, `platform/chaos/` (catalogue, validator, tests), two workflows in `gitops/charts/aap-config/values.yaml`, `ansible/playbooks/aap_launch.yml`, two scenario pages and their `ansible/demos/<id>/` files, the demo catalogue, this brief

## Goal

Prove the startx chaos charts on demo333 and show two demos with them: chaos on the cluster's infrastructure, and chaos
on the Zuno AI platform while a person keeps chatting. Every run is approved by a person in AAP, acts on one target at
a time from a closed list, and ends with a check that the platform healed in time.

## Facts on 2026-11-21

- The charts `chaos-cerberus`, `chaos-kraken` (krkn 5.2.15) and `chaos-pipeline` were released at 21.3.391 on
  2026-11-21. They passed an admission dry-run on demo333 and have never run on a cluster.
- `chaos-pipeline` ships the Tasks `cerberus-check`, `krkn-run` and `krkn-hub-scenario` and the Pipelines `chaos-infra`
  and `chaos-application`. It never creates a PipelineRun.
- The node scenarios select `node-role.kubernetes.io/worker=` in the chart, which can select a GPU node. The owner chose
  one infra node for the node tiers, labelled `zuno.io/chaos-target=true` on Sunday 2026-11-22 (see the demo-day page).
- The target list of WP-311 (`evaluations/stress/chaos.yaml`, six entries) was never run live.

## The work

1. **Component `chaos` (Day 2).** Wrapper chart `gitops/charts/chaos` with `chaos-cerberus` and `chaos-pipeline` pinned
   from the startx stable index; namespace `zuno-chaos`, not Kueue-managed; ServiceAccount `chaos-pipeline`; health
   signal Service `cerberus` (port 8080, answers `True` or `False`); Pipelines `chaos-infra`, `chaos-application` and
   `zuno-chaos-provider-cut`; `make d2 install|check|uninstall chaos`.
2. **Target catalogue.** `platform/chaos/targets.yaml` and its validator, with the tests of WP-311 moved to it. Targets:
   `pod-ai-gateway`, `pod-mcp-gateway`, `pod-a2a-gateway`, `pod-praxis`, `pod-open-webui`, `pod-unifai`, `pod-keycloak`,
   `pod-kserve-controller`, `pod-rhoai-operator`, `provider-cut-mistral`, `pod-model-gpt-oss`.
3. **Infra tiers.** `pods` (one Prometheus pod, one router pod, one `openshift-apiserver` pod); `hog` (CPU 80 %, then
   memory 50 % of the node, about 60 s each) and `latency` (50 ms, 2 % loss, 60 s) on the labelled infra node. The
   worker reboot stays off (ADR-0626 clause 8).
4. **AAP workflows.** `zuno-day3-chaos-infra-workflow` and `zuno-day3-chaos-platform-workflow`: pre-check, approval,
   run, post-check. `make d3 chaos infra TIER=pods|hog|latency CHAOS_CONFIRM=infra` and
   `make d3 chaos platform TARGETS=<ids> CHAOS_CONFIRM=platform` route to them.
5. **Two demos.** `docs/demo/scenarios/resilience/chaos-infrastructure.md` and `chaos-platform.md`, and their files
   under `ansible/demos/`. Their start launches the workflow without waiting for its end (it stops at its approval
   node): `ansible/playbooks/aap_launch.yml` gained `aap_launch_wait: false` for that, and `aap_launch_attach: true` for
   the stop, which waits (at most 20 minutes) for the latest run of the workflow and reads its result. The default
   behaviour of the playbook is unchanged. Both pages say they were written from the design and not rehearsed.

## What is done (2026-11-21, repository only)

- The two scenario pages, their `ansible/demos/` files, the catalogue rows (41 demos, 35 scenarios), the stress-table
  rows and the regenerated stress reader rules: branch `chaos-demo-pages`, not pushed. `consistency.py` and
  `check_docs.py` pass on it.
- The chaos component, the catalogue, the workflows and `make d3 chaos`: in progress on the branch `chaos-demos`.

## Live validation plan (Sunday 2026-11-22, each step on the owner's go)

The steps and their pass criteria are in [the demo-day page](../../demo/demo-day-2026-11-24.md#window). In short:
install the component; chart test of `chaos-kraken` (one Job, then uninstalled); `chaos-infra` tier `pods` twice
through AAP; the platform targets one at a time; the node tiers on the infra node; the model pod once; a stress and
chaos run together; the 35 scenarios of the catalogue that existed before; a table per tier and per target for the
owner at 20:00. Evidence under `~/.local/share/zuno/evidence/chaos-validation-20261122/`.

## Rollback

`make d2 uninstall chaos` removes the pipelines, cerberus and their RBAC. Helper pods and network policies are reaped
by label. `make d3 check recovery` gives the next step.

## Acceptance

- `make d2 check chaos` passes; cerberus answers `True` on a healthy cluster.
- Each tier and each target ran at least once through its AAP workflow, with its PipelineRun `Succeeded` and the
  recovery within its bound, or the failure is written here with its evidence.
- `DEMO_CONFIRM=<id> make demo rehearse chaos-infrastructure 5` and `chaos-platform 5` pass, with a person approving in
  AAP; the pages carry the result in their Page status.
- WP-311 is marked superseded only after this live run.
