# Releasing (ADR-0115)

**Two independent, parallel image paths exist - don't conflate them.**
Deploying this platform onto a live OpenShift cluster (`make day0|d0`,
`make day1|d1`) never needs anything below this note: every first-party
image is built in-cluster by an OpenShift `BuildConfig`
(`ansible/roles/*_build/`, `ansible/tasks/apply_openshift_build.yml`),
pushed to the internal `zuno-ai-build` `ImageStream` mirror
(`image-registry.openshift-image-registry.svc:5000/zuno-ai-build/*`),
and **always tagged `:latest`** - there is no other tag a BuildConfig
ever produces. Every `gitops/charts/*/values.yaml` whose
`image.repository` points at that internal registry must therefore use
`image.tag: latest` - not a version pin - or its Deployment goes
`ImagePullBackOff` with `manifest unknown` the moment ArgoCD/the image
trigger tries to resolve a tag that was never pushed there (this has now
bitten every `mcp-*` chart and several agent charts, fixed each time by
reverting to `latest` - see e.g. commits `09d2cee`, `be35efa`, and
2026-08-20's `comage`/`advantage`/`finage`/`naveo` fix).

Everything *below* this note - tagging `v0.1.0`, `build-publish.yml`
publishing to `quay.io/zuno/*`, `pin_release.py` rewriting chart
`image.tag` - is a **separate, currently optional** supply-chain/release
story (SBOM, signing, immutable external distribution, ADR-0115). It only
makes sense once a chart's `image.repository` is *also* repointed at
`quay.io/zuno/<component>` (step 4 below already says this is "a manual,
reviewed edit per chart" - easy to skip by accident). Pinning `.tag` to
`v0.1.0` while `.repository` still points at the internal ImageStream -
i.e. running `pin_release.py` without also repointing `.repository` - is
exactly the mismatch that keeps recurring. Nothing about deploying to a
cluster today depends on this path ever having run.

This project has never cut a release - every GitOps `Application`
(`gitops/apps/*/application.yaml`, `gitops/root-app-of-apps.yaml`) still
tracks `targetRevision: main`, a moving reference. ADR-0115 wants that
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
   `quay.io/zuno/<component>:sha-<commit>` (always) and
   `quay.io/zuno/<component>:v0.1.0` (only for a tag push).
4. Bump each `gitops/charts/*/values.yaml`'s `image.tag` (or
   `.repository`, if also moving off the in-cluster registry placeholder
   coordinates - see each chart's own comment) to `v0.1.0` in a follow-up
   commit/PR. Do this mechanically with
   `platform/supply-chain/pin_release.py --manifest <manifest.yaml>`
   (`--dry-run` first to preview) rather than hand-editing every chart:
   write a manifest listing every `chart_values`/`path`/`tag` (and,
   optionally, `digest` - recorded for audit in
   `platform/supply-chain/pinned-releases.yaml`, not embedded in
   `values.yaml`, since no chart template renders a digest today) pair
   from the images `build-publish.yml` just published; see the script's
   own docstring for the exact manifest schema. It refuses to run unless
   the manifest covers *exactly* the fields
   `platform/supply-chain/check_no_latest_tags.py` currently reports - a
   stale or incomplete manifest fails loudly rather than partially
   applying. It only ever rewrites `tag` fields, preserving every existing
   comment; repointing `.repository` to `quay.io/...` (if you choose to)
   is still a manual, reviewed edit per chart.
   `platform/supply-chain/check_no_latest_tags.py` (wired into
   `.github/workflows/lint.yml`) will start passing once every chart's
   `tag: latest` is replaced this way.
5. Once the pinned images exist, run
   `platform/supply-chain/verify_signatures.py` to confirm each
   immutable-tagged first-party image verifies against the expected
   `build-publish.yml` keyless GitHub OIDC identity before treating the
   release as trusted. This becomes a meaningful, non-trivial check only
   once step 4 has replaced at least one `latest` tag - see the script's
   own docstring for why it correctly passes trivially before that.
6. Bump `gitops/apps/*/application.yaml`'s `targetRevision: main` to
   `targetRevision: v0.1.0` in the same PR - this is the point ADR-0115's
   "production-like Argo CD applications must deploy a reviewed Git
   revision/tag" actually takes effect, and not before. Also bump
   `gitops/root-app-of-apps.yaml`'s own `targetRevision` the same way even
   though Ansible no longer applies it (ADR-0311): it stays a working,
   up-to-date example for the documented pure-GitOps bootstrap path
   (`docs/platform/installation.md`).
7. Merge, then `make day0|d0 configure` / `make day1|d1 configure|run`
   (or let ArgoCD's automated sync pick it up) to roll the cluster onto
   the pinned revision.

Subsequent releases repeat steps 1-7 with the next tag. `gitops/apps/vault/application-d1.yaml`
already tracks a pinned upstream chart version (`targetRevision: "0.28.1"`,
a third-party chart release, not this repository's own) - the same
pattern this process brings to every other Application.
