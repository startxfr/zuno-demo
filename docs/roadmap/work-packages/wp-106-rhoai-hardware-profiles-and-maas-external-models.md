# WP-106: RHOAI HardwareProfiles for local models

- **State:** Done
- **ADRs:** ADR-0537 (Implemented)
- **Estimated files touched:** ~7 (2 new `HardwareProfile` Helm templates, 5
  annotated `LLMInferenceService`/`InferenceService` templates)

> Execute this brief as a standalone task from the repository root.

## Goal

Close the gap ADR-0537 documents: give local models the same Dashboard
hardware-profile visibility as a manually deployed model
(`granite-7b-redhat-lab`).

## Why

Live diagnostic of `granite-7b-redhat-lab`'s `CrashLoopBackOff` found its
Dashboard-assigned `HardwareProfile` (`default-profile`) declares no
`Accelerator` identifier, so vLLM got scheduled with zero GPU. Our own
models sidestep that failure mode by setting `resources` directly in Helm,
but as a side effect never show a hardware profile in the Dashboard at all.

## ADR references

ADR-0537, Decision 1-2. Read that ADR first - it has the full CR YAML and
the explicit scope boundary (Granite stays manual).

## Sequencing (two phases, each gated on the previous)

### Phase 1 - HardwareProfile CRs (ADR-0537 Decision 1)

- New templates: `gitops/charts/models/templates/hardwareprofile-mig-1g-24gb.yaml`,
  `hardwareprofile-mig-2g-48gb.yaml`, rendering the two CRs from ADR-0537's
  YAML verbatim, namespace `redhat-ods-applications` (corrected 2026-09-02
  from an initial `zuno-ai-run` placement - the Dashboard's Settings >
  Hardware profiles page is RBAC-scoped to `redhat-ods-applications` only,
  see ADR-0537 Decision 1's correction).
- Live check: `oc apply --dry-run=server` against the live cluster schema
  before merging (the schema was confirmed live during ADR authoring, but
  operator versions can drift).

### Phase 2 - Annotate existing InferenceServices (ADR-0537 Decision 2)

- Patch `llminferenceservice-qwen35.yaml`, `-gptoss.yaml`,
  `inferenceservice-embedding.yaml` (→ `mig-1g-24gb`) and
  `llminferenceservice-wesh.yaml`, `-qwen.yaml` (→ `mig-2g-48gb`) with the
  two `opendatahub.io/hardware-profile-*` annotations.
- Live check: after ArgoCD sync, the Dashboard's Model Serving page shows a
  hardware profile for all five, matching Granite's presentation.
- ~~Granite itself: fix by hand in the Dashboard (select `mig-1g-24gb` at
  redeploy) - not part of this chart, no repo change.~~ **Moot since
  2026-09-03: `granite-7b-redhat-lab` was deleted.** The hardware-profile fix
  had in fact already been applied by hand (the live ISVC carried
  `opendatahub.io/hardware-profile-name: mig-1g-24gb`) and it did *not* make
  the model Ready - the real blocker was `minReplicas: 2` against a saturated
  GPU quota, so its HPA demanded a second replica that could never be
  admitted, the Deployment stalled at `1/2`, and its one running pod held the
  last free `mig-1g.24gb` slice for 47h. That starved `embeddings` (down 9
  days), which starved `rag-service` of an embedding endpoint, which failed
  `ragas-eval` and the six `zuno-day2-stresstest-*` Jobs. Deleting the ISVC
  and its ServingRuntime released the slice; `embeddings` went Ready and
  retrieval recovered on the same query `ragas-eval` had reported empty.
  If Granite is ever redeployed, set `minReplicas: 1` - the quota cannot
  admit two of anything.

**Result, 2026-09-02: both phases live-verified.** Dashboard shows a
hardware profile badge for all five annotated InferenceServices, matching
Granite's presentation. Phase 2's rollout triggered a live incident (a
`ResourceQuota`-blocked `embeddings` surge pod - see ADR-0537 Consequences)
that was recovered manually; no further repo change was needed. ADR-0537's
`Status` moved to `Implemented` 2026-09-03.

## What NOT to touch

- Do not fold `granite-7b-redhat-lab` into `gitops/charts/models` - it stays
  a manual Dashboard deployment by decision.

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0.
- `helm lint` / `helm template` on `gitops/charts/models` renders the new
  `HardwareProfile` resources with no errors, and leaves every pre-existing
  rendered resource unchanged.

## Live verification (operator step)

Confirmed live 2026-09-02: Dashboard hardware-profile display shown for all
five models, side by side with Granite. ADR-0537's `Status` updated to
`Implemented` and this WP's `State` to `Done` 2026-09-03.

## Related work

Publishing `mistral`/`gpt-oss-120b` as `ExternalModel`+`MaaSModelRef` was
originally scoped as later phases of this same WP. That work is unrelated
to hardware profiles beyond sharing a diagnostic session, and is blocked on
a separate upstream defect - it now lives in
[WP-125](wp-125-external-models-through-maas.md) against
[ADR-0541](../../adr/0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md).
