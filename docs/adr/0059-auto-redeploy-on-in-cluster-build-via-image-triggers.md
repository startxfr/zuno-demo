# ADR-0059: Auto-redeploy consuming pods when an in-cluster build completes

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0056 established `make d1 build <component>` as the day-to-day path from source to a running in-cluster image (`BuildConfig` → `ImageStream:latest`, `image.repository` pointing at the in-cluster mirror, `imagePullPolicy: Always`). ADR-0115 separately governs the GitHub Actions → Quay path, kept as the supply-chain provenance proof, not the deployment source (2026-08-21 note: local `BuildConfig`/`ImageStream` remains the default runtime-image source; see also ADR-0353, not yet written, for a possible future Quay cutover).

Neither ADR ever specified what happens *after* a build completes. Until 2026-08-21 this repo's own operational history shows the honest answer was: nothing, automatically. `docs/platform/slo.md`'s own dated finding records the manual workaround operators actually used:

> `oc rollout restart` alone doesn't reliably work here - ArgoCD's `selfHeal: true` on the agent Applications reverted `arkos-bff`'s and `naveo-bff`'s restart within ~1s as drift, since the `restartedAt` annotation isn't tracked in Git. Deleting the running pod directly worked for both: `imagePullPolicy: Always` means the ReplicaSet's replacement pod re-pulls `:latest`, and pod deletion isn't something ArgoCD's Application-level diffing reverts.

Commit `649243c` ("Add `image.openshift.io/triggers` so a fresh Build auto-redeploys consuming pods") closed this gap for real, live, before this ADR was written - this record formalizes an already-shipped decision rather than proposing a new one, the same retroactive-documentation convention this repo already uses elsewhere (e.g. ADR-0410/0-series promotions).

**Why this needed writing down now**: with no ADR to anchor it, the mechanism's own source comments mislabeled it "ADR-0411 follow-up" (ADR-0411 is an unrelated Keycloak-CA-trust decision) in 12 `gitops/apps/*/application-d1.yaml` files and `operator/aiagent-operator/internal/controller/aiagent_controller.go` - fixed as part of this ADR landing. More importantly, this session's own WP-04 release-pinning work (`platform/supply-chain/tag_local_release.py`, earlier the same day) briefly broke it for 16 components by repointing chart `image.tag` from `latest` to a frozen `v0.1.0` - confirmed live, another concurrent session's fresh `agent-bff:latest` build sat undeployed while the trigger annotation watched the now-static release tag instead. Reverted (see ADR-0115's dated note); this ADR makes the "why `:latest`-tracking is the required steady state" reasoning explicit so it doesn't get silently broken by a future release-pinning pass again.

## Decision

**1. `image.openshift.io/triggers` annotation, not `DeploymentConfig`/`ImageChangeTrigger`.** This repo uses plain `apps/v1 Deployment` objects throughout (no `DeploymentConfig` exists anywhere in the tree) - `ImageChangeTrigger` is a `DeploymentConfig`-only feature and doesn't apply. OpenShift's separate, lesser-known annotation-based image-trigger controller works on any `Deployment`: the annotation names an `ImageStreamTag` and a `fieldPath`; whenever a `Build` pushes a new image to that tag, the controller patches the named container's `image` field directly to the resolved digest, and that patch (changing the pod template) is what causes the `Deployment` controller to roll a new `ReplicaSet` - no human action, no `oc rollout restart`, no pod deletion.

   Each chart defines this once as a helper (`gitops/charts/<name>/templates/_helpers.tpl`, e.g. `rag-service.imageTrigger`) parameterized by `.Values.image.repository`/`.tag`/container name, and renders it as an annotation on the Deployment (`gitops/charts/<name>/templates/deployment.yaml`). 13 charts carry it: `rag-service`, `agent-runtime`, `ai-gateway`, `aiagent-operator`, `mcp-gateway`, `mcp-confluence`, `mcp-sales-db`, `mcp-salesforce`, `mcp-git-forge`, `tekos`, `advantage`, `comage`, `finage` (the last four carry it twice, once per `frontend`/`bff` container).

**2. `ignoreDifferences` on every consuming Application, so ArgoCD's `selfHeal` doesn't fight the controller's patch.** `gitops/apps/*/application-d1.yaml` (12 files) declare:

   ```yaml
   ignoreDifferences:
     - group: apps
       kind: Deployment
       jsonPointers:
         - /spec/template/spec/containers/0/image
   ```

   Without this, ArgoCD would see the trigger-patched digest as drift from the Git-declared `:latest` string and revert it on the next reconcile - the exact `oc rollout restart` failure mode `docs/platform/slo.md` already documented, just automated instead of manual.

**3. `aiagent-operator`'s own reconcile loop needed the same fix, separately.** `arkos` and `naveo`'s Deployments are rendered by the operator's controller, not by a static chart - the controller `Owns()` its Deployments and re-reconciles on every change, including the trigger controller's own image patch. Without intervention, that reconcile would recompute the desired image from `.Values`-equivalent config (a floating `:latest` reference) and immediately stomp the resolved digest back, undoing the trigger on every single push. `operator/aiagent-operator/internal/controller/aiagent_controller.go`'s `preserveLiveImages()` copies each container's *live* image from the existing Deployment onto the desired one before `Update()` whenever the trigger annotation is present - the operator's equivalent of ArgoCD's `ignoreDifferences`.

**4. Steady state is `:latest`-tracking; a release tag is a snapshot, not a target.** ADR-0115's `tag_local_release.py`/`pin_release.py` can pin a chart to a frozen, named tag (e.g. `v0.1.0`) as a one-time, live-verified proof that the release pipeline works end to end - that pin necessarily stops the trigger from firing for ordinary builds, since the annotation now watches a tag nothing rebuilds. That is acceptable only as a deliberate, temporary state around a specific release moment; reverting to `:latest` immediately after is the expected, correct next step, not an afterthought - this is why the revert happened the same day as the pin in this repo's own history.

**Scope**: `rag-ingestion` and `mlops` are Tekton `Pipeline`-based components with no `Deployment` at all - nothing to trigger; excluded by design, not a gap this ADR leaves open.

## Consequences

A normal `make d1 build <component>` now reaches a running pod with zero manual steps, for every component with a `Deployment`. The historical `oc delete pod` workaround remains valid as a fallback (e.g. forcing a re-pull without a fresh build) but is no longer required for the common case. The trade-off is coupling: any future mechanism that changes what tag a chart's `image.tag` field points to (a release pin, a rollback, a manual override) must be aware it also changes what the trigger watches - `:latest` is not just a convention here, it's load-bearing for this automation.

## Security considerations

No change to trust boundaries - the trigger controller only ever resolves an `ImageStreamTag` this cluster's own `BuildConfig` already produced, in the same namespace (`zuno-ai-build`) every other build-time mechanism already trusts. `ignoreDifferences` is scoped to exactly one field path (`containers[0].image`) per Deployment, not a blanket drift exemption.

## Operational considerations

A component whose `Deployment` stops picking up fresh builds should first be checked for exactly the two failure modes this ADR exists to prevent: (a) `image.tag` no longer set to `latest` in the chart (a stale release pin, see point 4 above), or (b) the `ignoreDifferences`/`preserveLiveImages` guard missing or misconfigured for that specific component, letting ArgoCD or the operator revert the trigger's patch.

## Related ADRs

- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) - Day 0/Day 1 sequencing this build step belongs to.
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) - the Quay/release-pinning path this ADR's point 4 distinguishes itself from; ADR-0115 lists this ADR in its own Related ADRs for the reverse direction.
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md) / [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md) - the operator whose own reconcile loop needed `preserveLiveImages()`.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.
