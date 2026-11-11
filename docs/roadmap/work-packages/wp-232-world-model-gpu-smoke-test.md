# WP-232: World-model GPU smoke test (delivers ADR-0604 gates G0 to G4)

- **State:** Done (2026-11-09) - what remains (teardown, signed-in rehearsal) is carried by WP-237
- **ADRs:** ADR-0604
- **Depends on:** WP-229 (including the toleration window), WP-231
- **Blocks:** WP-237
- **Estimated files touched:** ~3

> Execute this brief as a standalone task from the repository root.

## Goal

One short, early use of the GPU node (about 3 hours) that answers the go/no-go questions before the rest is built on them,
and proves that enabling and disabling the switch really creates and deletes the node.

## ADR references

ADR-0604 §5 proof obligation, §9 gates G0 to G4, D5.

## Operator steps (the user's go for the window, then for each cluster action)

1. Set `zuno_world_model_enabled: true` (commit and push the cluster file); `make d0 install world-model-gpu`.
2. Check the node: Ready, `nvidia.com/mig.config=all-disabled`, allocatable `nvidia.com/gpu: 1`, product
   RTX PRO 6000 Blackwell Server Edition, driver version, only GPU Operator pods on it.
3. Apply `platform/world-model/tests/gpu-smoke-job.yaml` in `zuno-world-model`; keep the JSON report.
4. Generate the initial images of the three presets with FLUX and store them in S3 next to the models.
5. `make d0 uninstall world-model-gpu`; confirm the Machine is gone (`oc get machines -n openshift-machine-api`) and the
   instance terminated (`aws ec2 describe-instances`); set the switch back to `false`.

## Repo changes

`docs/testing/world-model-gpu-smoke-<date>.md` with the report, the timings (node boot, driver, cache fill) and the
decision; `platform/world-model/models.lock.yaml` gains the preset images.

## Go / no-go

Go when one quantization sustains about 20 displayed FPS at 720p or better, NVENC or the CPU encoder keeps up, and a
FLUX edit plus splice completes in about 2 seconds or less without collapsing the next frames.
Otherwise stop and decide with the user: the 360p model, EdenLive (ADR-0604 §5), or a smaller demo scope.

## Result (2026-11-08)

**GO.** Waypoint-1.5-1B sustains 80.7 FPS at 720p in bf16 and 98.6 FPS in fp8 (the bar is about 20), NVENC encodes in 4 ms a
frame, a FLUX edit takes 1.16 s and its splice 12 ms, and both models fit in 23.5 GB. The full report, with what failed
(`intw8a8`, `nvfp4`) and why it does not matter, is in
[world-model-gpu-smoke-2026-11-08.md](../../testing/world-model-gpu-smoke-2026-11-08.md). Not done here: the three preset
images in S3 (the first image takes 0.9 s, so a stored one is optional) and the removal of the node, which waits for after the
2026-11-09 demo because the demo needs it.
