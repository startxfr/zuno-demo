# Releasing (ADR-0115, ADR-0549, ADR-0580)

**Three independent, parallel image paths exist — don't conflate them.**
Agent definitions are released separately again, outside this repository —
see [Agents release](#agents-release-adr-0576-adr-0580) at the end.

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

   **Rendering the digests (ADR-0603 M16, WP-226), opt-in.** The ledger is
   what was built and signed; `RENDER_DIGESTS=1` (or
   `platform/supply-chain/render_release_digests.py --release <tag>` after
   the release) writes those digests into the charts' `digest` keys, so the
   Deployments run `repository@sha256:...` with `IfNotPresent` and no
   `:latest` trigger. Merged to `main`, that pins what ArgoCD deploys and
   stops ADR-0059's auto-redeploy for those components until `--clear`. It
   is a deployment decision: it needs the user's go for that release, like
   every pin. A chart whose `digest` is empty renders exactly as before.

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

## Platform tags follow the roadmap bands

A platform tag `v0.X.0` is named after the roadmap band `v0.X`, in the same way the first tags were: `v0.1.0` for band
v0.1, `v0.2.0` for v0.2, `v0.3.0` for v0.3, `v0.13.0` for v0.13. The bands, their goals and their ADRs are in
[docs/roadmap/versions.md](docs/roadmap/versions.md); the work packages are in the
[implementation roadmap](docs/roadmap/implementation-roadmap.md).

| Tag | Band | Date | Commit | In-cluster ledger |
|---|---|---|---|---|
| `v0.1.0` | v0.1 | 2026-08-20 | `5111d324` | yes |
| `v0.1.1` | v0.1 (patch) | 2026-08-20 | `db0181ac` | no |
| `v0.2.0` | v0.2 | 2026-09-05 | `7d6d91c1` | yes |
| `v0.3.0` | v0.3 | 2026-10-22 | `8dcea46d` | yes |
| `v0.13.0` | v0.13 | 2026-11-05 | `388555d6` | yes (2026-11-06) |
| `v0.14.0` | v0.14 | 2026-11-06 | `6b79cb7f` | yes (2026-11-06) |
| `v0.14.1` | v0.14 (patch) | 2026-11-06 | `5a352b9c` | yes (2026-11-07) |
| `v0.14.2` | v0.14 (patch) | 2026-11-07 | `2b396a58` | yes (2026-11-07) |

**The rule.**
- **When.** A band is tagged when its ADRs are all closed and its work packages are Done or deferred by name, as of
  [implementation-roadmap.md](docs/roadmap/implementation-roadmap.md). The earlier tags were milestones of their band and
  were cut with a gap or two still named (v0.1 still lists ADR-0110, v0.2 WP-098), so a tagged band may carry a named
  exception, written in the tag message and in versions.md.
- **Where.** On `main`, on the commit where the band closed. Never on `devel`. The Applications are applied with
  `zuno_gitops_target_revision` (`ansible/tasks/apply_gitops_app.yml`), which is `devel` on demo333 although the manifests
  default to `main`: a push to `devel` is a deployment to demo333, and `main` is promoted from a `devel` commit that already
  ran there, so a tag names something that ran. Before a live demonstration, promote the commit the golden-path check
  passed on (ADR-0605).
- **How.** An annotated tag: `git tag -a v0.X.0 <commit> -m "v0.X.0: <what the band delivered>"`, then
  `git push origin v0.X.0`. A tag push starts no workflow: `build-publish.yml` is manual-only (path 2 above).
- **Patch tags.** `v0.X.1` for a fix on the band after its tag, as `v0.1.1` was.
- **The ledger is a separate step.** `make d3 release TAG=v0.X.0` (path 3) rebuilds and signs every component in the cluster
  and appends to `platform/supply-chain/pinned-releases.yaml`. It is a cluster action with its own go and window. A tag
  without a ledger entry is valid: it names the commit, not signed images.
- **Agents releases use the same band numbers.** `zuno-demo-agents` tags `v0.X.y` per band (v0.12.0, v0.13.0) and this
  platform pins one of them in `platform/okf/agents.lock` (see [Agents release](#agents-release-adr-0576-adr-0580)). The two
  repositories do not share patch numbers.

**Bands not tagged.** v0.4 to v0.12 were never tagged: work moved from `v0.3.0` straight to the demo333 pilot and the
UnifAI adoption, and the bands were closed in the roadmap without a tag. They are not tagged retroactively, so `v0.13.0`
contains all of their content. The next tag is `v0.14.3` (2026-11-08, a patch cut before the demonstration of 2026-11-09, by user decision);
`v0.15.0` follows once the v0.15 band closes and more content has joined it.

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
   signs anything — signing moved fully in-cluster (Vault Transit then,
   keyless through RHTAS since ADR-0535, Transit kept as its rollback),
   since a GitHub-hosted runner has no route to sign against it. Images
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

## Agents release (ADR-0576, ADR-0580)

Agent bundles and the corp policies that bound them (tools, knowledge,
quotas, model routing, guardrails, limits, the model catalog) are not in
this repository. They are released by
[startxfr/zuno-demo-agents](https://github.com/startxfr/zuno-demo-agents)
(its own `RELEASING.md`): a `v*` tag publishes one OCI artifact per agent
plus a corp index artifact to `quay.io/zuno`, signed keyless by that
repository's release workflow (ADR-0577, ADR-0578).

This platform runs exactly one release, pinned by digest in
`platform/okf/agents.lock` — the only file here that names an agents
version. A release reaches a cluster in four steps:

1. **Promotion PR.** `.github/workflows/okf-promote.yml` (scheduled, or run
   by hand with a tag) finds a release newer than the lock, verifies it
   offline (`platform/supply-chain/admit_okf_bundle.py`: keyless
   signatures of the release workflow, contract-tests attestations, the
   committed Sigstore trust root), checks this platform can serve it, moves
   the lock, regenerates `platform/okf/stack-config.generated.yaml` and the
   quota files, and opens a PR with a semantic diff. By hand:
   `make d3 admit agents RELEASE=vX.Y.Z UPDATE_LOCK=1`, then
   `python3 platform/okf/generate_stack_config.py` and
   `python3 platform/okf/generate_quota_enforcement.py`.
2. **Review and merge.** CI re-verifies the locked release
   (`lint.yml`, `okf-release` job) and checks every generated file.
3. **Roll.** Re-run the consumers: `make d2 install mcp` (the okf-fetch
   init container of mcp-gateway pulls the new digest at pod start),
   `make d2 install unifai` (UnifaiAgentBundles), `make d0 install
   keycloak` (the group reconcile Job). ai-gateway (model-routing policy) and mlops
   (agents, corp policies) read the release at build time: rebuild them
   (`make d1 build ai-gateway`, `make d2 build mlops`).
4. **Check.** `make d2 check agents` admits the lock again and runs the
   acceptance gate against the release's bundles. It also compares the digest the running mcp-gateway and a2a-gateway
   fetch (their `okf-fetch` init container) with `platform/okf/stack-config.generated.yaml` and fails on a gap: the
   gateways read the release only when a pod starts, so a promotion not rolled in step 3 shows up here (WP-208 D9).

Nothing under `agents/` is ever edited here: there is no such directory.
Locally, `python3 platform/okf/release_cache.py` extracts the locked release
once into `.cache/okf-release/<digest>/` (gitignored) for any reader that
needs it; it needs `cosign` and `oras`.
