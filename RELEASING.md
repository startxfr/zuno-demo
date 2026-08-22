# Releasing (ADR-0115)

**Two independent, parallel image paths exist — don't conflate them.**

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

This project has never cut a release: every GitOps `Application`
(`gitops/apps/*/application.yaml`, `gitops/root-app-of-apps.yaml`) still
tracks `targetRevision: main`. ADR-0115 wants that replaced with an
immutable, reviewed Git revision or tag, but rewriting `targetRevision`
before any tag exists would point every Application at a ref that
doesn't exist and break every deployment — a deliberate sequencing gap,
not an oversight. The tooling exists
(`.github/workflows/build-publish.yml`); cutting the first release is a
maintainer decision, not something to fabricate a tag for.

## The process, once a maintainer is ready to cut `v0.1.0`

1. Ensure `main` is at the commit you want to release.
2. `git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0`.
3. `.github/workflows/build-publish.yml` triggers on the tag push:
   builds, scans, SBOMs and signs every component image, publishing each
   as both `quay.io/zuno/<component>:sha-<commit>` (always) and
   `quay.io/zuno/<component>:v0.1.0` (only for a tag push).
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
5. Run `platform/supply-chain/verify_signatures.py` to confirm each
   pinned image verifies against the expected `build-publish.yml`
   keyless GitHub OIDC identity before treating the release as trusted —
   a meaningful check only once step 4 has replaced at least one
   `latest` tag (see the script's own docstring).
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
