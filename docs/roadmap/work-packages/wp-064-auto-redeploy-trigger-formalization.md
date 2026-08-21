# WP-064: Formalize the in-cluster build → auto-redeploy trigger (ADR-0059)

- **State:** Done (2026-08-21 - retroactive documentation of already-shipped code; no new implementation required)
- **ADRs:** ADR-0059 (Implemented, written directly - the mechanism predates this WP)
- **Depends on:** —
- **Blocks:** —
- **Estimated files touched:** 15 (1 new ADR + 1 index row + 12 comment fixes + 1 Go comment fix)

> This brief documents work that was already live before it was written, per
> this repo's retroactive-ADR convention. There is no repo-change checklist
> to execute - only the documentation trail below.

## Goal

The user asked to confirm and formalize the platform's build philosophy:
first-party images build via the in-cluster `BuildConfig`, push to the local
`ImageStream`, and that should trigger a deployment automatically - with an
ADR and WP recording the decision, since none existed.

## What was found

Commit `649243c` ("Add `image.openshift.io/triggers` so a fresh Build
auto-redeploys consuming pods") already implemented exactly this, hours
before this WP was written: an OpenShift annotation-based image-trigger
controller (not `DeploymentConfig`/`ImageChangeTrigger` - this repo has none)
patches each Deployment's container image directly from its `ImageStreamTag`
whenever a `Build` completes, with matching ArgoCD `ignoreDifferences` (12
`application-d1.yaml` files) and an `aiagent-operator`-specific
`preserveLiveImages()` guard so neither ArgoCD's `selfHeal` nor the
operator's own reconcile loop reverts the trigger's patch.

It was undocumented at the ADR level - only in code comments (several
mislabeled "ADR-0411 follow-up", ADR-0411 being an unrelated Keycloak-CA
decision) and one dated finding in `docs/platform/slo.md` explaining why the
historical manual fallback (`oc rollout restart`) didn't work against
ArgoCD's `selfHeal`, and why `oc delete pod` did.

**Real regression found and fixed along the way**: this session's own WP-04
release-pinning work (`tag_local_release.py`, same day) had repointed 16
charts' `image.tag` from `latest` to a frozen `v0.1.0`, which also repointed
the trigger annotation - silently stalling the auto-redeploy for all 16
components. Confirmed live (another concurrent session's fresh
`agent-bff:latest` build sat undeployed) and reverted; see ADR-0115's and
WP-04's dated notes for the full trace. ADR-0059 makes explicit why
`:latest`-tracking is the required steady state so this doesn't silently
regress again the next time a release is pinned.

## Repo changes made

1. **`docs/adr/0059-auto-redeploy-on-in-cluster-build-via-image-triggers.md`**
   (new) - full decision record, `Status: Implemented`.
2. **`docs/adr/README.md`** - index row added (`v0` section, after ADR-0058).
3. **12× `gitops/apps/*/application-d1.yaml`** - comment corrected from
   "ADR-0411 follow-up" to "ADR-0059".
4. **`operator/aiagent-operator/internal/controller/aiagent_controller.go`**
   - same comment correction in `preserveLiveImages()`'s docstring.
5. **`docs/adr/0115-...md`** - ADR-0059 added to Related ADRs (cross-reference
   for "why pinning reverts to `:latest`").
6. **`docs/roadmap/work-packages/wp-04-supply-chain-completion.md`** - dated
   note recording the regression and its fix.

## Status updates (already applied)

- ADR-0059 → `Implemented`; index row added.
- `MEMORY.md` dated bullet.
- `python3 platform/docs/check_docs.py` → must PASS.

## Out of scope / deferred

- `rag-ingestion` and `mlops` (Tekton `Pipeline`-based, no `Deployment`) -
  nothing to trigger, not a gap.
- Any change to `oc delete pod` remaining as the fallback for a non-build
  re-pull need (e.g. forcing a restart with no new image).
