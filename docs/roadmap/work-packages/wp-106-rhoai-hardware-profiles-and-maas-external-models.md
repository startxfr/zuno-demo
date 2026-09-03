# WP-106: RHOAI HardwareProfiles for local models + ExternalModel/MaaSModelRef for mistral and gpt-oss-120b

- **State:** Not started
- **ADRs:** ADR-0537 (Proposed)
- **Depends on:** WP-27/ADR-0201 (MaaS governance plane live), WP-076/ADR-0521
  (per-group `MaaSSubscription` pattern this WP reuses)
- **Estimated files touched:** ~10 (2 new `HardwareProfile` Helm templates, 5
  annotated `LLMInferenceService`/`InferenceService` templates, 2 new
  `ExternalModel`+mirror-Secret Helm templates, `values.yaml`,
  `provider-routing.yaml`, `providers.py`/`maas_adapter.py` env wiring)

> Execute this brief as a standalone task from the repository root.

## Goal

Close the two gaps ADR-0537 documents: give local models the same
Dashboard hardware-profile visibility as a manually deployed model
(`granite-7b-redhat-lab`), and bring `mistral`/`gpt-oss-120b` under the same
MaaS governance (group-based access, rate limiting) that every local model
has had since ADR-0521.

## Why

Live diagnostic of `granite-7b-redhat-lab`'s `CrashLoopBackOff` found its
Dashboard-assigned `HardwareProfile` (`default-profile`) declares no
`Accelerator` identifier, so vLLM got scheduled with zero GPU. Our own
models sidestep that failure mode by setting `resources` directly in Helm,
but as a side effect never show a hardware profile in the Dashboard at all.
Separately, `mistral` and `gpt-oss-120b` are the only two chat providers
still called directly from `ai-gateway`, outside MaaS - a gap the platform
already has the transport code for (`maas_adapter.py`'s dormant
`MAAS_EXTERNAL_EGRESS_ENABLED` gate) but has never activated.

## ADR references

ADR-0537, Decision 1-4. Read that ADR first - it has the full CR YAML,
the Secret-key-mismatch resolution, and the explicit scope boundaries
(Granite stays manual; `mistral` stays on its native API, not OVHcloud;
Finage's exclusion stays in `ai-gateway`, not duplicated into MaaS).

## Sequencing (four phases, each gated on the previous)

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

### Phase 3 - ExternalModel + MaaSModelRef + per-group quotas (ADR-0537 Decision 3)

- New templates: `gitops/charts/models/templates/externalmodel-mistral.yaml`,
  `externalmodel-ovhcloud-gpt-oss-120b.yaml`, each rendering: (a) a mirror
  `ExternalSecret` targeting the existing Vault path
  (`providers/mistral`/`providers/ovhcloud`) with a Secret carrying data key
  `api-key`; (b) the `ExternalModel` CR; (c) a `maas.models[]` entry
  (`modelRef.kind: ExternalModel`) added to `values.yaml`, flowing through
  the existing `maas.yaml` range loop to emit `MaaSModelRef` +
  `MaaSSubscription` (per-group: `agent_tekos`/`sales`/catch-all
  `ai-gateway` SA, same priorities as local models) + `MaaSAuthPolicy`.
- **Do not** add Finage to any subject list here, and do not remove it from
  anywhere - its exclusion is out of scope for this phase (stays in
  `ai-gateway`).
- Live check (blocking, do not proceed to Phase 4 without it): a real
  completion request succeeds through each new `MaaSModelRef`, and the
  `MaaSSubscription`/`MaaSAuthPolicy` route-identity question from ADR-0537
  Decision 3 is resolved by direct observation (inspect what
  `maas-controller` actually publishes/keys on for an `ExternalModel`
  backend - do not assume it matches the `LLMInferenceService` case).

  **Result, 2026-09-02: FAILED, blocked upstream.** Repo work (templates,
  Secrets, values.yaml) merged and deployed clean (`helm lint`/`template`
  and a full server-side dry-run against the live cluster both passed with
  zero errors), but the live check above failed: both
  `mistral-large-maas`/`gpt-oss-120b-ovhcloud-maas` `MaaSModelRef`s report
  `phase: Failed` - `maas-controller` attaches their auto-generated
  `HTTPRoute` to a non-existent `Gateway/default-gateway` instead of the
  real `maas-default-gateway`. Confirmed as a known, currently-open
  upstream defect in `opendatahub-io/models-as-a-service`
  ([#1417](https://github.com/opendatahub-io/models-as-a-service/issues/1417),
  [#1399](https://github.com/opendatahub-io/models-as-a-service/issues/1399)
  - fix labelled `3.6-EA2`,
  [#1240](https://github.com/opendatahub-io/models-as-a-service/issues/1240)),
  not a manifest or config error on our side - no field in
  `ExternalModel.spec`/`MaaSModelRef.spec`/the cluster-wide `Config` CRD
  offers a workaround, and renaming an existing Gateway (`zuno-agent-
  gateway`) to either candidate name was evaluated and ruled out (would
  only mask the symptom, not attach Kuadrant's actual `AuthPolicy`/
  `TokenRateLimitPolicy`). See ADR-0537 Decision 3's `2026-09-02`
  correction for the full evidence. **Phase 4 does not proceed** - see
  below.

### Phase 4 - ai-gateway cutover (ADR-0537 Decision 4) - BLOCKED, not started

**Do not execute this phase.** Its precondition (Phase 3's live check) is
FAILED, not passed - see above. Switching `ai-gateway` to `via_maas` for
`mistral`/`ovhcloud-gpt-oss-120b` today would break them outright (no
working `MaaSModelRef` to route to). The plan below stays recorded for when
this unblocks, unchanged:

- `provider-routing.yaml`: add `via_maas: true` + `maas_model_ref` to the
  `mistral` and `ovhcloud-gpt-oss-120b` entries.
- Set `MAAS_EXTERNAL_EGRESS_ENABLED=true` (`gitops/charts/ai-gateway/
  values.yaml`, wherever `maasAdapter.enabled` is already wired for
  ADR-0521).
- Live check (blocking): both providers answer correctly end-to-end via
  MaaS, per-group quotas apply as expected (`agent_tekos`/`sales`/
  catch-all), and Finage is still denied `gpt-oss-120b`.
- Only after all of the above pass: remove the old direct-call branches for
  these two providers from `components/ai-gateway/app/providers.py`. This
  is the point at which ADR-0537 can move to `Implemented`.

**Re-entry condition**: this platform is upgraded to RHOAI 3.6-EA2 (or
later, carrying opendatahub-io/models-as-a-service#1399), and Phase 3's
live check is re-run and passes. Until then, `mistral`/`ovhcloud-gpt-
oss-120b` in `provider-routing.yaml` stay untouched - the pre-existing
direct-call path remains the only functional one for these two providers.

## What NOT to touch

- Do not change `mistral`'s upstream endpoint or credential - it stays on
  `api.mistral.ai`, never OVHcloud.
- Do not touch `mistral-codestral` - out of scope for this WP.
- Do not fold `granite-7b-redhat-lab` into `gitops/charts/models` - it stays
  a manual Dashboard deployment by decision.
- Do not add Finage (or any exclusion) into `MaaSAuthPolicy` - the exclusion
  stays solely in `ai-gateway`'s routing/classification layer.
- Do not remove the direct-call branches in `providers.py` before Phase 4's
  live checks pass.

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0.
- `helm lint` / `helm template` on `gitops/charts/models` renders the new
  `HardwareProfile`/`ExternalModel`/mirror-`ExternalSecret` resources with
  no errors, and leaves every pre-existing rendered resource unchanged.

## Live verification (operator step)

1. Phase 1-2: confirm Dashboard hardware-profile display for all five
   models, side by side with Granite.
2. Phase 3: confirm a real completion via each new `MaaSModelRef`, and
   record the observed route/subscription identity for `ExternalModel`
   backends (new information, not previously known on this cluster).
3. Phase 4: confirm the full cutover (both providers via MaaS only), the
   per-group quota behavior, and the Finage denial - record results in a new
   evidence doc (`docs/roadmap/evidence/adr-0537-...md`, same template as
   `adr-0521-maas-local-traffic.md`).
4. Update ADR-0537's Status to `Implemented` and this WP's `State` to `Done`
   only after all three steps above are live-verified.

## Out of scope / deferred

- Migrating `mistral-codestral` or any other SaaS provider to MaaS - not
  requested, not evaluated here.
- Relaxing or patching the `credentialRef` key-name requirement upstream -
  the mirror-Secret approach is a repo-side workaround, not a fix to RHOAI
  itself.
