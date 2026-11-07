# WP-237: World-model final acceptance and rehearsal (delivers ADR-0604 §9, §15)

- **State:** Not started
- **ADRs:** ADR-0604
- **Depends on:** WP-232, WP-236
- **Blocks:** none
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root.

## Goal

The demo works live on the target GPU from a presenter's laptop, the measurements are recorded as measured, and the switch
turns everything off again.

## ADR references

ADR-0604 §9 gates G0 to G7, §9.1, §9.2, §15.

## Operator steps (the user's go for the day, then for each cluster action)

1. Enable: switch on, `make d0 install world-model-gpu`, `make d2 install world-model`, `make d2 check world-model`.
2. Measure from an external laptop (Chrome or Edge) on the presenter network: displayed FPS at 720p, p95
   input-to-display latency, time to a visible prompt change, 2-minute navigation, 10-minute stability, a second user
   gets "busy".
3. Negative tests: a user outside the groups gets 403; a C2 request is refused; no egress outside the allowed targets;
   prompts appear neither in logs nor in metric labels.
4. Record one fallback video per preset, labelled "recorded" in the file and on screen.
5. Rehearse the runbook end to end with the presenter.
6. Run the golden-path check (ADR-0605) with the world-model probe; it must pass before any audience sees the demo
   (ADR-0606 clause 1).
7. Disable: `make d2 uninstall world-model`, `make d0 uninstall world-model-gpu`; Machine and EC2 instance gone; switch
   off; the cost alert stays silent. This is the rollback of ADR-0606 clause 1, tested once and recorded.

## Repo changes

`docs/testing/world-model-acceptance-<date>.md` with every number as measured (failures included); the ADR-0604 Definition
of Done checkboxes; ADR status in the body and the index; tracker, briefs and memory updated together.

## Verification

The acceptance file covers every row of ADR-0604 §9.1 and every gate; `check_docs.py` passes.
