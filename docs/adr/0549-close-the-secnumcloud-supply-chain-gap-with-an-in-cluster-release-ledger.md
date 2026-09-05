# ADR-0549: Close ADR-0111's last SecNumCloud gap with an in-cluster release ledger

- **Status:** Implemented - live-verified 2026-09-05: `make d3 release TAG=v0.2.0` built, RHTAS-signed and ledgered all 14 components (`platform/supply-chain/pinned-releases.yaml`, 18 pins/1 skipped, every digest real and `signed: true`); `:latest` digests and every live `zuno-ai-run` pod were confirmed untouched throughout; `make d2 check supply-chain` (signature verification + `check_release_ledger.py`) is green. A real, pre-existing bug was found and fixed along the way - see the Implementation note below.
- **Target:** v0.9
- **Date:** 2026-09-05
- **Decision owners:** Zuno Demo architecture team

## Implementation note (2026-09-05) — a real bug found and fixed live

The first `make d3 release TAG=v0.2.0` run built all 14 components
successfully, then failed at signing: every `run_image_signing_job.yml`
invocation errored with `cosign initialize (TUF root, ...) failed: Error:
creating cached local store: mkdir /.sigstore: permission denied`.
`ansible/tasks/verify_image_signatures.yml` had already carried the fix
for this exact failure mode (`HOME: /tmp` in the pod env, with a comment
explaining why `sign_in_cluster.py`'s own `env.setdefault("HOME", ...)`
isn't sufficient) since WP-070 - but `run_image_signing_job.yml`, the
signing job this ADR's mechanism reuses, had never carried the matching
fix. Fixed by adding the identical `HOME: /tmp` override.

This also explained an unrelated, independently-discovered symptom: an
`image-signing-supply-chain-signer` Job had failed with the same error
~87 minutes before this ADR's first release attempt (a routine
post-build signing, nothing to do with this ADR), and `make d2 check
supply-chain` was failing for all 14 `:latest` images ("no matching
signatures") - both were the same bug hitting whatever `:latest` builds
ran during the window before the fix landed. Re-running the (now-fixed)
signing job for all 14 `:latest` images resolved that too; `make d2
check supply-chain` is green again.

## Context

ADR-0111's SecNumCloud-oriented control matrix (`docs/security/secnumcloud-controls.md`) has exactly one `gap` row left: *"Deployable chart image tags are immutable (no `latest`)"*. That row is owned by WP-04 (`docs/roadmap/work-packages/wp-04-supply-chain-completion.md`), itself **Closed — deferred** since 2026-08-22: its stage 3 (retargeting charts to real Quay-published, signed, SBOM-attested tags) needs a real, credentialed run of `.github/workflows/build-publish.yml`, which is blocked on an external GitHub Actions billing lock on `startxfr/zuno-demo` with no repo-side fix (`docs/roadmap/versions.md`'s v0.7 band: *"ADR-0111 and ADR-0115 are both hard-blocked on an external GitHub-billing/Quay-cutover decision with no repo-side fix"*).

**This ADR's operator decision (2026-09-05): do not wait on, or route around, that external dependency.** Close the gap instead with a mechanism that depends on nothing outside this cluster - no GitHub Actions, no Quay, no new registry or CI/CD operator.

Two things made this possible without inventing new infrastructure:

1. **Signing is already fully in-cluster and unrelated to this gap.** ADR-0420 (Vault Transit) and its successor ADR-0535 (RHTAS - Fulcio/Rekor/Trillian/TUF, keyless, identity issued by this cluster's own Keycloak) already sign every image built via `make d1/d2 build <component>`, automatically, via an in-cluster `Job` (`ansible/tasks/run_image_signing_job.yml`) - no GitHub OIDC involved since 2026-08-22. WP-111 (Done, 2026-09-02) live-verified the RHTAS cutover for all 14 production images. This ADR reuses that mechanism unchanged; it does not touch signing.
2. **`platform/supply-chain/tag_local_release.py` already proves the remaining piece works.** Built for WP-04's stage-3 prep (2026-08-19/21), it rebuilds a component in-cluster from an exact tagged commit, landing the result at `<component>:<release_tag>` in the same internal ImageStream registry (`image-registry.openshift-image-registry.svc:5000/zuno-ai-build`) every chart already deploys from - `:latest` is never the build's output during the whole operation (a `finally` block always reverts the BuildConfig's `spec.output.to.name` back to `:latest`, even on failure). It was run for real against `v0.1.0` and produced real, live-verified immutable tags for every locally-buildable component.

**What stopped WP-04 from finishing this way already:** its stage-3 plan paired `tag_local_release.py`'s output with `pin_release.py`, which permanently rewrites `gitops/charts/*/values.yaml`'s `tag:` fields to the release tag. That is fundamentally incompatible with this platform's continuous-deployment architecture: ADR-0059 makes `:latest` load-bearing - the `image.openshift.io/triggers` annotation on 13 charts watches exactly that tag to auto-redeploy on every fresh build, and `gitops/apps/*` deliberately stays on `targetRevision: main`. Pinning `values.yaml` away from `latest` on `main` was tried for real on 2026-08-19/21, confirmed live to break auto-redeploy for 16 components (a concurrent session's fresh build sat undeployed), and was reverted the same day. WP-04's stage-3 design never had a safe path to "permanent immutable tag" without also cutting `image.repository` over to an external registry (Quay) - the exact step blocked by the billing lock.

**The reframing this ADR makes:** "immutable chart image tags" cannot mean "`values.yaml` never says `latest`" for a chart `main` continuously deploys - that would have to stay permanently false, by design, for this platform to keep auto-redeploying. It means instead: **the platform can, on demand, produce a named release that is provably immutable, signed and traceable end-to-end, entirely in-cluster** - without ever touching the continuous-deployment path. That is a real, verifiable, narrower claim than WP-04's original one, and it is the one this ADR actually closes.

## Decision

**Supersedes ADR-0111 in full.** ADR-0111 retains its historical control matrix and first-increment work (WP-11) unchanged; this ADR closes its one remaining `gap` row and both ADRs move to their terminal status together (ADR-0111 → Retired, this ADR → Implemented, once the live pass below has run).

**Does not supersede ADR-0115.** ADR-0115's GitHub Actions/Quay pipeline is a different, still-legitimate, still-mothballed mechanism (real, working, proven once for `v0.1.0`, kept available for the day the billing lock lifts or ADR-0353's external-registry cutover is written). ADR-0115 gets a dated correction note pointing here for this specific sub-scope and stays `Deferred`.

**Mechanism - `make day3|d3 release [supply-chain] TAG=<tag>`** (`ansible/playbooks/day3_release.yml`, WP-134):

1. **Precondition (operator):** `git tag <tag> && git push origin <tag>` - `oc start-build --commit=<tag>` needs that ref to exist in the BuildConfig's source (`origin/main`'s history).
2. **Build:** `platform/supply-chain/tag_local_release.py --release-tag <tag> --apply` rebuilds every component in `COMPONENTS` from the exact tagged commit into `<component>:<tag>`. `:latest` is never the build output at any point; live pods pulling `:latest` are undisturbed throughout, even across a build failure. `COMPONENTS`/`NOT_LOCALLY_BUILDABLE` are corrected as part of this ADR: `mlops` and `diagram-render` both have real BuildConfigs and were wrongly excluded before (see the script's own dated note); the sole genuine, permanent carve-out is `rag-ingestion`'s `images.compiler.tag` (no BuildConfig exists for it - building one purely to satisfy this mechanism is out of scope, a separate pre-existing gap).
3. **Sign:** every freshly built `<component>:<tag>` is signed keyless via RHTAS, reusing `ansible/tasks/run_image_signing_job.yml` unchanged in mechanism (generalized to accept a `sign_image_tag` other than `latest` - every existing `:latest` caller is unaffected). Any signing failure aborts the run before the ledger is touched.
4. **Verify:** an independent verification pass (the same `verify-images` Job mechanism `make d2 check supply-chain` uses for `:latest` images) confirms each signature is actually retrievable and valid, not just that signing exited 0.
5. **Record:** `tag_local_release.py --record-release` appends one entry to `platform/supply-chain/pinned-releases.yaml` - release tag, per-field digest, `signed: true`, timestamp. **No `values.yaml` or `gitops/apps/*/targetRevision` is ever written.** The ledger entry is the release artifact.

**Enforcement - `platform/supply-chain/check_release_ledger.py`** (WP-134), wired into `make day2|d2 check supply-chain` (`ansible/roles/supply_chain/tasks/check.yml`) - static, no cluster access, no GitHub Actions. Validates that every *recorded* release entry is structurally complete (real digest, `signed: true`, consistent tag) - not that a release always exists. A ledger with zero entries passes: a cluster that has never cut a release is not a compliance failure; a claimed release that is malformed or unsigned is. This replaces `check_no_latest_tags.py`'s former role in `.github/workflows/lint.yml` (removed - its "no chart may ever say `latest`" premise is now permanently, deliberately false for `main`'s continuously-deployed charts).

**`pin_release.py` is not deleted, but is out of this flow.** It stays correct and available, unchanged, for the day ADR-0353's still-unwritten external-registry cutover is ever adopted - the one scenario where rewriting `values.yaml`'s `tag:` fields to a release tag would become the right move again.

**Registry:** the existing OpenShift-native internal ImageStream registry only. No self-hosted Quay, no new operator - consistent with ADR-0056's explicit "no new operator dependency" decision for this platform's build path.

## Consequences

ADR-0111's last open control-matrix row closes with a real, live-verifiable mechanism that depends on nothing outside this cluster. `main`'s continuous-deployment behavior is completely unchanged - `:latest` keeps tracking every push exactly as ADR-0059 requires; a release is a signed snapshot an operator produces on demand, never a deployment target. The Sigstore Policy Controller admission gate (`gitops/charts/rhtas-config/`, currently dormant per ADR-0535's own status note, since its "images must reference a digest" rule conflicts with `main`'s `:latest`+trigger pattern) is not activated by this ADR - it is a natural future consumer of the digests this ledger now proves exist, deliberately left to a later ADR, the same way ADR-0535 already deferred it.

## Security considerations

No new trust boundary: the signing/verification path is the RHTAS mechanism ADR-0535/WP-111 already established and live-verified, unchanged. The ledger is evidence, not a mechanism any deployment consumes - a corrupted or hand-edited ledger entry cannot affect what runs in the cluster, only what `check_release_ledger.py` reports about a release's provenance.

## Operational considerations

`make d3 release TAG=<tag>` spends real build and signing compute against every locally-buildable component (14 today) - an on-demand operator action, not a routine or scheduled one, same tier as `make d3 sign`/`make d3 run`. A release that fails partway (a build, a signing Job, or the verify pass) aborts before the ledger is written - no partial or misleading entry is ever recorded. `rag-ingestion`'s `images.compiler.tag` stays a permanent, documented `skipped` entry; whether that image is genuinely dead code (per the chart's own comment) is a separate, unstarted follow-up, not this ADR's concern.

## Related ADRs

- [ADR-0111](0111-strengthen-secnumcloud-oriented-security-controls.md) - superseded in full by this ADR.
- [ADR-0059](0059-auto-redeploy-on-in-cluster-build-via-image-triggers.md) - why `:latest` must stay load-bearing for `main`, and why this ADR never touches it.
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) - the GitHub Actions/Quay path this ADR does not supersede; gets a dated correction note instead.
- [ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md) / [ADR-0420](0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md) - the already-in-cluster signing mechanism this ADR reuses unchanged.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.
