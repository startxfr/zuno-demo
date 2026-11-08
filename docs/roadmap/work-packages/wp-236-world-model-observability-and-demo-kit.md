# WP-236: World-model observability and demo kit (delivers ADR-0604 D7, §10)

- **State:** Repo work merged
- **ADRs:** ADR-0604
- **Depends on:** WP-235
- **Blocks:** WP-237
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root.

## Goal

A presenter can run the demo from a runbook, with three curated scenes and a dashboard that shows what the GPU is doing.

## ADR references

ADR-0604 D7, §9.2, §10.

## Repo changes

1. `gitops/charts/grafana/templates/dashboard-world-model.yaml` (GrafanaDashboard, folder "Zuno Platform"): DCGM panels
   for the world-model node, `zuno_world_*` panels (sessions, step time, displayed FPS, latency, prompt apply, busy,
   resets, encoder). The Perses copy is phase 2.
2. `platform/world-model/config/presets.yaml`: a logistics warehouse, a city at night (rain starts), a snowy village (the
   sky turns red and a volcano erupts); each with its pre-generated image (WP-232), seed, base prompt and mid-session event.
3. `docs/demo/world-model.md` (structure of `docs/demo/five-experiences.md`): audience and message; enable sequence with
   timings (start about 40 minutes ahead); preflight `make d2 check world-model`; an 8-minute script in short segments
   with resets (the model's context is about 10 seconds); what it does not show; if something goes wrong (the labelled
   recording); disable sequence and the cost alert.
4. `docs/architecture/world-model.md`: one page, the §4 diagram and the switch.

## Result (2026-11-07)

`platform/world-model/config/presets.yaml` (three scenes, validated by `components/world-model-web/tests/test_presets.py` against the visitor
rules; no image shipped: the pre-generated first images come with the GPU smoke test), `gitops/charts/grafana/templates/
dashboard-world-model.yaml` (20 panels over the zuno_world_* series, DCGM and the machine age; rendered and its JSON parsed),
`docs/demo/world-model.md` (written without the GPU and marked not-to-be-shown until WP-237) and `docs/architecture/world-model.md`.

## Verification

`check_docs.py` passes (doc links, make commands in the runbook); the dashboard JSON loads in Grafana with the mock
metrics from a local run.
