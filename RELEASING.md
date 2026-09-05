# Releasing (ADR-0115, ADR-0549)

**Three independent, parallel image paths exist — don't conflate them.**

Deploying to a live cluster (`make day0|d0`, `make day1|d1`) only uses the
first path and never needs anything below this note.

1. **In-cluster build (what actually deploys today).** Every first-party
   image is built in-cluster by an OpenShift `BuildConfig`
   (`ansible/roles/*_build/`, `ansible/tasks/apply_openshift_build.yml`),
   pushed to the internal `zuno-ai-build` `ImageStream` mirror, and
   **always tagged `:latest`** — a BuildConfig never produces any other
   tag. Every `gitops/charts/*/values.yaml` whose `image.repository`
   points at that internal registry must therefore keep `image.tag:
   latest`, not a version pin, or its Deployment goes `ImagePullBackOff`
   (`manifest unknown`) the moment ArgoCD tries to resolve a tag that was
   never pushed. This has bitten multiple charts already; the fix is
   always the same: revert to `latest`.
   `platform/supply-chain/check_no_latest_tags.py` is the live source of
   truth for which charts still need it.

2. **Supply-chain release (`quay.io/zuno/*`, currently disabled).**
   Tagging `v0.1.0`, `build-publish.yml` publishing to Quay, and
   `pin_release.py` rewriting chart `image.tag` are a **separate**
   story (SBOM, signing, immutable distribution, ADR-0115). It only makes
   sense once a chart's `image.repository` is *also* repointed at
   `quay.io/zuno/<component>` — skipping that and pinning only `.tag` is
   the exact mismatch that keeps recurring. Nothing about deploying today
   depends on this path ever having run.

   **Disabled 2026-08-22 (WP-04/ADR-0115 closed):** `build-publish.yml`'s
   automatic push/tag triggers were removed (now `workflow_dispatch` only)
   after the 2026-08-21 operator decision to stay on the in-cluster
   BuildConfig path rather than cut charts over to Quay. The pipeline
   already proved itself once (2026-08-19, run `32273454405`, tag
   `v0.1.0` — real signed, SBOM'd images published) and is left in place
   for a future ADR to reactivate by restoring its triggers; the
   step-by-step process below still documents exactly how.

3. **Named in-cluster release (ADR-0549, `make d3 release TAG=<tag>`,
   current mechanism).** Closes ADR-0111's SecNumCloud gap without
   depending on path 2's GitHub Actions/Quay pipeline at all. Rebuilds
   every locally-buildable component in-cluster from an exact tagged
   commit into `<component>:<tag>` (the same internal ImageStream mirror
   as path 1, never Quay), signs each keyless via RHTAS (the same
   mechanism `make d1/d2 build` already signs `:latest` builds with), and
   records tag+digest+signature evidence in
   `platform/supply-chain/pinned-releases.yaml` — an append-only ledger,
   never a `values.yaml` edit. **Deliberately never touches
   `gitops/charts/*/values.yaml` or `gitops/apps/*/targetRevision`** —
   `main` keeps deploying `:latest`, continuously, exactly as path 1
   describes; this is a signed provenance snapshot, not a deployment
   target (see ADR-0059 for why `:latest` must stay load-bearing for
   `main`, and ADR-0549's Context for why path 2's `pin_release.py`
   approach was not reused). See [WP-134](docs/roadmap/work-packages/wp-134-in-cluster-release-ledger.md)
   for the full mechanism.

   ```
   git tag v0.2.0 && git push origin v0.2.0
   make day3|d3 release TAG=v0.2.0
   ```

This project has never cut a path-2 release: every GitOps `Application`
(`gitops/apps/*/application.yaml`, `gitops/root-app-of-apps.yaml`) still
tracks `targetRevision: main`. ADR-0115 wants that replaced with an
immutable, reviewed Git revision or tag, but rewriting `targetRevision`
before any tag exists would point every Application at a ref that
doesn't exist and break every deployment — a deliberate sequencing gap,
not an oversight. The tooling exists
(`.github/workflows/build-publish.yml`); cutting the first release is a
maintainer decision, not something to fabricate a tag for. Path 3
(ADR-0549) is unaffected by this and deliberately never touches
`targetRevision` at all, ever — see point 3 above.

## Path 2's process, once a maintainer is ready to cut `v0.1.0` via Quay

1. Ensure `main` is at the commit you want to release.
2. `git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0`.
3. `.github/workflows/build-publish.yml` triggers on the tag push:
   builds, scans and SBOMs every component image (no longer signs - see
   step 5), publishing each as both `quay.io/zuno/<component>:sha-<commit>`
   (always) and `quay.io/zuno/<component>:v0.1.0` (only for a tag push).
4. Bump each `gitops/charts/*/values.yaml`'s `image.tag` (and
   `.repository`, if also moving off the in-cluster registry) to
   `v0.1.0` in a follow-up commit/PR. Do this with
   `platform/supply-chain/pin_release.py --manifest <manifest.yaml>`
   (`--dry-run` first) rather than hand-editing every chart — write a
   manifest listing every `chart_values`/`path`/`tag`/`digest` tuple from
   the images `build-publish.yml` just published (schema in the script's
   own docstring; `digest` is recorded in
   `platform/supply-chain/pinned-releases.yaml` for audit). It refuses to
   run unless the manifest covers *exactly* the fields
   `check_no_latest_tags.py` currently reports, and only rewrites `tag`
   fields, preserving every existing comment. Repointing `.repository` to
   `quay.io/...` is still a manual, reviewed edit per chart.
   `check_no_latest_tags.py` (wired into `.github/workflows/lint.yml`)
   starts passing once every chart's `tag: latest` is replaced this way.
5. **Signing note (ADR-0420, 2026-08-22):** `build-publish.yml` no longer
   signs anything — signing moved fully in-cluster (Vault Transit), since
   a GitHub-hosted runner has no route to sign against it. Images
   published to `quay.io/zuno/*` by this release flow are therefore
   *not* signed. `platform/supply-chain/verify_signatures.py` only
   verifies the in-cluster `image-registry...svc:5000/zuno-ai-build/*`
   images every chart actually deploys today (`make d2 check
   supply-chain`, or `python3 platform/supply-chain/verify_signatures.py`
   from inside the cluster — it needs registry network access a release
   PR's CI run doesn't have) — it has no bearing on this Quay path at
   all. Signing the Quay-published path too is a distinct, not-yet-done
   follow-up (see ADR-0420's Future work).
6. Bump `gitops/apps/*/application.yaml`'s `targetRevision: main` to
   `targetRevision: v0.1.0` in the same PR — this is the point
   ADR-0115's "production-like Argo CD applications must deploy a
   reviewed Git revision/tag" actually takes effect. Also bump
   `gitops/root-app-of-apps.yaml`'s own `targetRevision` the same way
   (Ansible no longer applies it, ADR-0311; it stays a working example
   for the documented pure-GitOps bootstrap path,
   `docs/platform/installation.md`).
7. Merge, then `make day0|d0 configure` / `make day1|d1 configure|run`
   (or let ArgoCD's automated sync pick it up) to roll the cluster onto
   the pinned revision.

Subsequent releases repeat steps 1-7 with the next tag.
`gitops/apps/vault/application-d1.yaml` already tracks a pinned upstream
chart version (`targetRevision: "0.28.1"`, a third-party chart release,
not this repository's own) — the same pattern this process brings to
every other Application.
