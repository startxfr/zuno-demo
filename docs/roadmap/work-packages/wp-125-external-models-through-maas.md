# WP-125: mistral and gpt-oss-120b as ExternalModel/MaaSModelRef

- **State:** Repo work merged (blocked upstream - `payload-processing`
  ext_proc plugin defect, root-caused 2026-09-03 - see Phase 1 result
  below)
- **ADRs:** ADR-0541 (Proposed - blocked upstream)
- **Depends on:** WP-27/ADR-0201 (MaaS governance plane live), WP-076/ADR-0521
  (per-group `MaaSSubscription` pattern this WP reuses); split from WP-106
  2026-09-03 (see that brief's "Related work")
- **Estimated files touched:** ~3 (2 new `ExternalModel`+mirror-Secret Helm
  templates, `values.yaml`; `provider-routing.yaml`/`providers.py`/
  `maas_adapter.py` env wiring for Phase 2, not yet touched)

> Execute this brief as a standalone task from the repository root.

## Goal

Bring `mistral`/`gpt-oss-120b` under the same MaaS governance (group-based
access, rate limiting) that every local model has had since ADR-0521.

## Why

`mistral` and `gpt-oss-120b` are the only two chat providers still called
directly from `ai-gateway`, outside MaaS - a gap the platform already has
the transport code for (`maas_adapter.py`'s dormant
`MAAS_EXTERNAL_EGRESS_ENABLED` gate) but has never activated.

## ADR references

ADR-0541, Decision 1-2. Read that ADR first - it has the full CR YAML,
the Secret-key-mismatch resolution, and the explicit scope boundaries
(`mistral` stays on its native API, not OVHcloud; Finage's exclusion stays
in `ai-gateway`, not duplicated into MaaS).

## Sequencing (two phases, each gated on the previous)

### Phase 1 - ExternalModel + MaaSModelRef + per-group quotas (ADR-0541 Decision 1)

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
- Live check (blocking, do not proceed to Phase 2 without it): a real
  completion request succeeds through each new `MaaSModelRef`, and the
  `MaaSSubscription`/`MaaSAuthPolicy` route-identity question from ADR-0541
  Decision 1 is resolved by direct observation (inspect what
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
  `TokenRateLimitPolicy`). See ADR-0541 Decision 1's `2026-09-02`
  correction for the full evidence. **Phase 2 does not proceed** - see
  below.

  **Re-tested, 2026-09-03 (RHOAI 3.5.0 GA): still FAILED, different
  reason.** The Gateway-attachment defect above is fixed on this build -
  both `MaaSModelRef`s are now `phase: Ready`, correctly attached to
  `maas-default-gateway`, all 6 `MaaSSubscription`s `Active`. But a real
  completion request (once sent with the correct `<namespace>/<name>-maas`
  identity - a working local-model control proved AuthZ itself is fine)
  now times out reaching the real upstream through the MaaS gateway's
  Envoy passthrough proxy for both `ExternalModel`-backed routes. Ruled
  out live: double-TLS (WP-124's plaintext `DestinationRule` correctly
  wins), `NetworkPolicy` (ingress-only), general pod egress/DNS/TLS (a
  direct call from the same pod straight to the real upstream succeeds in
  0.1s). Root cause not identified. See ADR-0541 Decision 1's `2026-09-03`
  note for the full evidence. **Phase 2 still does not proceed.**

  **Root-caused, same day.** Not a network/TLS issue - the request never
  reaches `api.mistral.ai`/OVHcloud at all. RHOAI's own `payload-processing`
  ext_proc filter (`envoy.filters.http.ext_proc.ipp`, wired Gateway-wide by
  `gitops/charts/openshift-ai/templates/maas-gateway-ipp-anchor.yaml`,
  `failure_mode_allow: false`) rejects the request before the upstream
  router runs: its `model-provider-resolver` plugin compares the request
  body's `model` field against the bare `ExternalModel` CR name and errors
  `"model mismatch between request body and ExternalModel"`, because the
  body must carry the full `<namespace>/<name>-maas` identity to satisfy
  Kuadrant's `AuthPolicy` earlier in the same chain - no value satisfies
  both checks. This never triggers for local `InferencePool`-backed
  routes (the comparison is `ExternalModel`-specific), which is why only
  these two routes are affected. Full evidence: ADR-0541 Decision 1's
  2026-09-03 "Root-caused" note. **Not attempted**: scoping the `ipp`
  filter away from these two routes via `typed_per_filter_config` (the
  same mechanism the anchor file already documents) is a live change to
  a Gateway shared with every local model's production traffic - out of
  scope for this investigation pass. **Phase 2 still does not proceed.**

### Phase 2 - ai-gateway cutover (ADR-0541 Decision 2) - BLOCKED, not started

**Do not execute this phase.** Its precondition (Phase 1's live check) is
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
  is the point at which ADR-0541 can move to `Implemented`.

**Re-entry condition, updated 2026-09-03 (root cause identified same
day)**: RHOAI's `payload-processing` ext_proc plugin (see Phase 1's
"Root-caused" note above and ADR-0541 Decision 1) either stops rejecting
`ExternalModel` requests as a model mismatch, or this repo scopes the
`ipp` filter away from these two routes - and Phase 1's live check is
re-run and passes. This is no longer pinned to a RHOAI version bump - the
originally-diagnosed Gateway-attachment defect that motivated the
`3.6-EA2` target is already fixed on the 3.5.0 GA build now running, but a
different, still-open defect took its place. Until the timeout is fixed,
`mistral`/`ovhcloud-gpt-oss-120b` in `provider-routing.yaml` stay
untouched - the pre-existing direct-call path remains the only functional
one for these two providers.

## What NOT to touch

- Do not change `mistral`'s upstream endpoint or credential - it stays on
  `api.mistral.ai`, never OVHcloud.
- Do not touch `mistral-codestral` - out of scope for this WP.
- Do not add Finage (or any exclusion) into `MaaSAuthPolicy` - the exclusion
  stays solely in `ai-gateway`'s routing/classification layer.
- Do not remove the direct-call branches in `providers.py` before Phase 2's
  live checks pass.

## Acceptance checks (repo-side)

- `python3 platform/docs/check_docs.py` exits 0.
- `helm lint` / `helm template` on `gitops/charts/models` renders the new
  `ExternalModel`/mirror-`ExternalSecret` resources with no errors, and
  leaves every pre-existing rendered resource unchanged.

## Live verification (operator step)

1. Phase 1: confirm a real completion via each new `MaaSModelRef`, and
   record the observed route/subscription identity for `ExternalModel`
   backends (new information, not previously known on this cluster).
2. Phase 2: confirm the full cutover (both providers via MaaS only), the
   per-group quota behavior, and the Finage denial - record results in a new
   evidence doc (`docs/roadmap/evidence/adr-0541-...md`, same template as
   `adr-0521-maas-local-traffic.md`).
3. Update ADR-0541's Status to `Implemented` and this WP's `State` to `Done`
   only after both steps above are live-verified - which requires this
   platform to first be upgraded to RHOAI 3.6-EA2 (or later).

## Out of scope / deferred

- Migrating `mistral-codestral` or any other SaaS provider to MaaS - not
  requested, not evaluated here.
- Relaxing or patching the `credentialRef` key-name requirement upstream -
  the mirror-Secret approach is a repo-side workaround, not a fix to RHOAI
  itself.
