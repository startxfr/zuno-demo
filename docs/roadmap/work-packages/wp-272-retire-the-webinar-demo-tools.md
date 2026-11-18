# WP-272: Retire the webinar demo tools

- **State:** Done (2026-11-15)
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-270](wp-270-build-the-make-demo-lifecycle-engine.md)
- **Related:** [ADR-0550](../../adr/0550-demonstrate-sovereign-ai-through-classification-specialization-and-resilience.md), [WP-136](wp-136-webinar-demo-orchestration.md), [ADR-0536](../../adr/0536-live-node-failover-drill-for-qwen-model-fallback.md)
- **Target:** v0.16
- **Estimated files touched:** ~16: the eight demo playbooks, `ansible/tasks/demo_persona_probe_job.yml`, `evaluations/demo_presenter_probe.py` and its test, five pages under `docs/`

> Why: ADR-0616 clause 13. The webinar steps open surfaces retired in October 2026, and `make demo check` cannot mean two
> things. The webinar probe also left a copy of the persona password in `zuno-ai-run`.

## Goal

The WP-136 helpers are gone, what they read that still matters lives in the per-demo checks, no page names a retired
verb, and the cluster holds no leftover of the webinar probe.

## Steps

1. Delete `ansible/playbooks/demo_check.yml`, `demo_reset.yml`, `demo_step_1.yml` to `demo_step_5.yml`,
   `ansible/tasks/demo_persona_probe_job.yml`, `evaluations/demo_presenter_probe.py` and
   `evaluations/tests/test_demo_presenter_probe.py`. Keep `make d3 scenario-failover-node` and its playbooks.
2. Salvage into `ansible/demos/_lib/`: the Ready-condition read (`cr_ready.yml`: the Keycloak CR, the
   LLMInferenceServices) and the TrainJob lookup (`trainjob_evidence.yml`), if WP-270 has not already done it.
3. Update the pages that name the old verbs: `docs/demo/freeze-protocol.md` (the allowed list names `make demo check`;
   add `make demo freeze on` to the step where every session is contacted), `docs/demo/golden-path.md`,
   `docs/demo/rollback.md`, `docs/demo/scenarios/foundation/gitops-day0-3.md` (row 14:15 and the paragraph on the step
   verbs), `docs/platform/shared-password-rotation.md`.
4. **Operator action, with the owner's named go:** delete Secret `demo-persona-probe-credentials`, ConfigMaps
   `demo-persona-probe-ca` and `demo-persona-probe-scripts`, and Job `zuno-demo-persona-probe` in `zuno-ai-run`
   (`oc delete ... -n zuno-ai-run`; the Job with `--cascade=background`). Check first that no Argo CD Application owns
   them (`oc get <kind> <name> -o jsonpath='{.metadata.labels}'`).

## Acceptance

- `grep -rn "demo-step\|make demo reset\|make demo step-[0-9]\|all-check" Makefile ansible docs evaluations` finds
  nothing outside dated history (ADR bodies, evidence, change logs).
- The catalogue test of WP-271 passes (it checks every `make demo <verb>` in `docs/`).
- `oc get secret,cm,job -n zuno-ai-run | grep demo-persona-probe` is empty.

## Result (2026-11-15)

- Code (zuno-demo-reorg-coder, reviewed and merged by zuno-demo-reorg): `demo_check.yml`, `demo_reset.yml`,
  `demo_step_1.yml` to `demo_step_5.yml`, `ansible/tasks/demo_persona_probe_job.yml`,
  `evaluations/demo_presenter_probe.py` and its test are deleted (1 122 lines); `make d3 scenario-failover-node` is
  untouched. Their Ready and TrainJob reads live on in `ansible/demos/_lib/cr_ready.yml` and `trainjob_evidence.yml`.
  The operator checks of lightspeed, openclaw and image-signing-admission read a CSV by name prefix with phase
  Succeeded, so an OLM upgrade does not fail them; `consistency.py` refuses a CSV pinned by name and warns when a
  page's Status or Check names an object its file does not read.
- Docs (zuno-demo-reorg-writer): `freeze-protocol.md` (`make demo freeze on|off` on every presenter workstation,
  install/uninstall/rehearse refused while it is set, the new meaning of `make demo check`),
  `shared-password-rotation.md`, and `gitops-day0-3.md`, which moves to its `## Presenter lifecycle` form with this WP
  (row 14:15 shows `make demo list`).
- Cluster (2026-11-14, owner's go, zuno-demo-reorg-demo333): the four leftovers of the webinar probe deleted from
  `zuno-ai-run`.
- `grep` finds no retired verb outside dated history; the syntax-check loop passes on the 32 remaining playbooks.

