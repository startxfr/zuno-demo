# Releasing (ADR-0051)

This project has never cut a release - every GitOps `Application`
(`gitops/apps/*/application.yaml`, `gitops/root-app-of-apps.yaml`) still
tracks `targetRevision: main`, a moving reference. ADR-0051 wants that
replaced with an immutable, reviewed Git revision or tag, but rewriting
those `targetRevision` values today, before any tag has ever been pushed,
would point every Application at a Git ref that doesn't exist and break
every deployment - a strictly worse outcome than the moving-`main`
reference it would replace. This is a deliberate, honest sequencing gap,
not an oversight: the tooling to make a real release exists now
(`.github/workflows/build-publish.yml`), but *cutting* the first release
is a decision for a repository maintainer, not something to fabricate a
tag for from here.

## The process, once a maintainer is ready to cut `v0.1.0`

1. Ensure `main` is at the commit you want to release.
2. `git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0`.
3. `.github/workflows/build-publish.yml` triggers on the tag push: builds,
   scans, SBOMs and signs every component image, publishing each as both
   `quay.io/zuno-demo/<component>:sha-<commit>` (always) and
   `quay.io/zuno-demo/<component>:v0.1.0` (only for a tag push).
4. Bump each `gitops/charts/*/values.yaml`'s `image.tag` (or
   `.repository`, if also moving off the in-cluster registry placeholder
   coordinates - see each chart's own comment) to `v0.1.0` in a follow-up
   commit/PR. `platform/supply-chain/check_no_latest_tags.py` (wired into
   `.github/workflows/lint.yml`) will start passing once every chart's
   `tag: latest` is replaced this way.
5. Bump `gitops/apps/*/application.yaml` and
   `gitops/root-app-of-apps.yaml`'s `targetRevision: main` to
   `targetRevision: v0.1.0` in the same PR - this is the point ADR-0051's
   "production-like Argo CD applications must deploy a reviewed Git
   revision/tag" actually takes effect, and not before.
6. Merge, then `make configure` (or let ArgoCD's automated sync pick it
   up) to roll the cluster onto the pinned revision.

Subsequent releases repeat steps 1-6 with the next tag. `gitops/apps/vault/application.yaml`
already tracks a pinned upstream chart version (`targetRevision: "0.28.1"`,
a third-party chart release, not this repository's own) - the same
pattern this process brings to every other Application.
