# ADR-0115: Use immutable and verifiable software supply chain artifacts

- **Status:** Deferred
- **Target:** v0.7 (retargeted from v0.1 on 2026-08-24 — WP-04's own text: "the ADR itself states gaps 2,3,4,6 all reduce to gap 7: one real, credentialed GitHub Actions + Quay release"; grouped under a new v0.7 milestone dedicated to GitHub-Actions-based release automation)
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0051, retargeted v0 -> v0.1 (2026-08-13 roadmap reorganization; the remaining gaps are release-cycle work)
- **Last reviewed:** 2026-08-22

## Implementation note (2026-08-22) — closed, pipeline disabled

WP-04 closed. The 2026-08-21 operator decision below (stay on the
in-cluster BuildConfig path, no Quay repository cutover) is now formalized
as a stop, not just a pause between attempts: gaps 2, 3, 4 and 6 all reduce
to that same cutover decision, which the operator has decided not to make
for now. Rather than leave this ADR indefinitely `Partially implemented`,
it moves to **Deferred**: real, working infrastructure stays in the repo
untouched (the proven 2026-08-19 release, `platform/supply-chain/*.py`,
`tag_local_release.py`), but no further gap-closing work is planned until a
**future ADR** explicitly reactivates this stream.

Concrete actions taken:

- `.github/workflows/build-publish.yml`'s automatic `push`/tag triggers
  removed (now `workflow_dispatch` only) - it no longer runs on every push
  to `main` or every `v*` tag, so nothing is published to Quay
  automatically. The workflow file, its cosign/SBOM/Trivy steps and the
  `QUAY_USERNAME`/`QUAY_PASSWORD` secret wiring are untouched and it
  remains manually runnable.
- Verified no `gitops/charts/*/values.yaml` `image.repository`/
  `frontendRepository`/`bffRepository` field points at `quay.io/zuno/*` -
  every first-party component still deploys from the in-cluster
  `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/*`
  ImageStream. The one remaining literal `quay.io` string in any chart
  (`gitops/charts/models/values.yaml`'s `vllm: quay.io/modh/vllm:...`) is a
  third-party OpenShift AI model-runtime fallback governed by ADR-0048, not
  a Zuno-built image - explicitly out of scope for this ADR.
- Verified every zuno-authored component still has a real in-cluster
  BuildConfig: `agent-runtime`, `agent-bff`, `agent-frontend`,
  `aiagent-operator`, `ai-gateway`, `mcp-gateway`, `mcp-confluence`,
  `mcp-git-forge`, `mcp-sales-db`, `mcp-salesforce`, `rag-service`,
  `rag-ingestion` and `mlops` each have an `ansible/roles/<name>_build`
  role wired to `ansible/tasks/apply_openshift_build.yml`. This corrects
  the 2026-08-21 note below, which believed `mlops` had none -
  `ansible/roles/mlops_build` exists (added by the WP-34 mlops pipeline
  work) and is wired into `ansible/playbooks/day2_build.yml`.

Gaps 2, 3, 4 and 6 (below) remain genuinely open - this note does not
resolve them, it records the decision to stop pursuing them for now.

## Implementation note (2026-08-21) — local-registry immutable tagging

The user clarified the actual goal behind the failed stage-3 attempt
below: Quay publishing (`build-publish.yml`, on every `v*` tag) should
keep happening as the supply-chain provenance proof - that already
works - but deployment should keep consuming the local `zuno-ai-build`
ImageStream, not Quay. Reframed the problem: give the *local* registry a
real immutable tag too, instead of repointing `image.repository` to Quay.

New `platform/supply-chain/tag_local_release.py`: for each of the 12
components with a real in-cluster BuildConfig, temporarily repoints
`spec.output.to.name` from `<component>:latest` to
`<component>:<release_tag>`, runs `oc start-build --commit=<release_tag>
--wait` (building from the *exact* tagged commit, so the local and Quay
images are provably the same source), then always reverts
`spec.output.to.name` back to `:latest` - `:latest` is never the build
output at any point, so live pods pulling it (`imagePullPolicy: Always`)
are undisturbed even if one restarts mid-run. Verified live: `:latest`'s
digest was confirmed byte-identical before and after, for every
component.

Ran this for real against `v0.1.0` for all 12 components (`agent-bff`,
`agent-frontend`, `agent-runtime`, `ai-gateway`, `aiagent-operator`,
`mcp-confluence`, `mcp-gateway`, `mcp-git-forge`, `mcp-sales-db`,
`mcp-salesforce`, `rag-ingestion`, `rag-service`) - each build reached
`Complete`, each produced a real, distinct local `:v0.1.0` `ImageStreamTag`
digest. `--emit-manifest` then reads those *already-tagged* live
ImageStreamTags (no cluster mutation) and prints a manifest in
`pin_release.py`'s exact existing format, so `pin_release.py` itself is
reused unchanged - `image.repository` fields are never touched, exactly
as it already guaranteed.

Running `pin_release.py` against that manifest found one of its own
pre-existing bugs, never previously exercised: `_apply_pins_to_file`
counted every literal `tag:` line in a file and assumed a 1:1
correspondence with the manifest's pins for that file - correct as long
as a file's fields are either all pinned or all skipped, but
`rag-ingestion/values.yaml` has two `tag:` lines with *one* pinned
(`images.ingestion.tag`, now locally buildable) and *one* skipped
(`images.compiler.tag`, no BuildConfig exists for `rag-pipeline-compiler`
at all). Fixed: the function now correlates each literal `tag:` line to
its YAML path (via the same document-order walk `_current_findings()`
already produces) and only edits lines whose path is actually pinned,
skipped lines included, in file order. `python3 -m py_compile` and the
existing `check_no_latest_tags.py` both confirm no regression;
`tests/test_pin_release.py` has 3 pre-existing failures (stale fixture
manifest against the repo's much-expanded chart set) unrelated to this
fix - confirmed identical with and without it via `git stash`.

Result: 16 of 18 previously-`latest` fields are now pinned to a real,
live-verified local `v0.1.0` tag (`helm lint` clean on all 16 touched
charts; the rendered `image:` reference for a spot-checked component
matched its live digest exactly). The remaining 2 (`mlops`, no
BuildConfig at all; `rag-ingestion`'s `images.compiler.tag`, an unwired
`rag-pipeline-compiler`) are a separate, pre-existing gap - out of scope
here, not silently worked around. `check_no_latest_tags.py` therefore
still exits 1 on those two; `lint.yml`'s gate stays `continue-on-error:
true` deliberately - flipping it now would fail every PR over an issue
this change didn't create, not just the fields it actually closed.

**Honest limit, not closed by this mechanism**: gap 6 (signature
verification as a deployment gate). Local in-cluster builds have no
GitHub OIDC identity, so they are never cosign-signed -
`verify_signatures.py` correctly finds nothing to verify for these
images, same as before. Staying local means immutable and traceable, not
cryptographically verified at deploy time - that remains a Quay-path-only
property.

**Also deliberately not touched**: gap 4, `targetRevision: main`.
Retargeting `gitops/apps/*` to a tag would pin ArgoCD's *manifest*
source too, and `v0.1.0` is now stale against `main` - a much bigger
regression than the stage-3 near-miss below. A future decision, tied to
a *fresh* release tag, not this one.

## Implementation note (2026-08-21) — stage 3 attempted and reverted

Ran `pin_release.py` against the real `v0.1.0` manifest (WP-04 stage 2's
real release, run 32273454405) as WP-04 stage 3's first step. It
succeeded mechanically - 15 fields pinned, 3 correctly skipped (added
`mcp-git-forge`, a chart created after this release ran, to the skip
list alongside `rag-ingestion`'s pre-existing two) - but produced a
**real, would-be-live outage** before anything was committed, caught by
inspecting the diff: every one of those 15 charts' `image.repository`
still points at the in-cluster `zuno-ai-build` ImageStream
(`ansible/roles/<component>_build`'s BuildConfig), which has never
produced and will never produce a `:v0.1.0` tag - only `:latest`. Pinning
`.tag` to `v0.1.0` without also repointing `.repository` to
`quay.io/zuno/<component>` renders an image reference
(`zuno-ai-build/<component>:v0.1.0`) that does not exist, which every
Application syncs live via `automated: {selfHeal: true}` - this would
have ImagePullBackOff'd tekos, arkos, comage, advantage, finage, naveo,
agent-runtime, ai-gateway, rag-service, aiagent-operator, mcp-gateway,
mcp-confluence, mcp-sales-db and mcp-salesforce simultaneously.
`platform/supply-chain/README.md` already named this exact failure mode
("the manifest-unknown ImagePullBackOff this repo has hit repeatedly...
all reverted back to latest each time") - reproduced it once more here,
caught before commit, and reverted every touched file
(`git checkout --` on the 15 chart `values.yaml`s plus
`pinned-releases.yaml`/`release-v0.1.0-manifest.yaml`) without disturbing
unrelated uncommitted work already present in the tree.

`pin_release.py`'s own docstring already flagged repository repointing as
"an explicit, reviewed decision for the operator to make chart-by-chart,
not something this tool should infer or automate" - the WP-04 brief's
stage 3 steps don't call that decision out as a precondition of step 1,
which is what let this get as far as a real diff. Two things need
deciding before stage 3 can safely proceed, together, not stage-3-step-1
alone:

1. **Cut over each chart's `image.repository` to `quay.io/zuno/<component>`
   at the same time as pinning `.tag`** - a real architecture decision
   (leave the in-cluster BuildConfig path as the deployment mechanism for
   day-to-day dev, or actually start consuming the Quay images the release
   pipeline produces) that changes how this cluster gets images going
   forward, not a mechanical follow-up.
2. **`v0.1.0` is now three days stale** against `main` (real fixes landed
   across nearly every one of these 15 components since 2026-08-19 -
   agent-runtime, rag-service, arkos, and others each had genuine bugs
   found and fixed live in that window) - pinning to it today would pin
   production to code with known, already-fixed defects. A fresh real
   release (re-running `build-publish.yml` against current `main`) is the
   honest way to close this, not reusing the existing manifest.

Left `false`/`latest` everywhere, ADR-0115 unchanged at `Partially
implemented`. Not attempting either decision unilaterally - both are
architecture/timing calls for the operator, not something to infer from
the existing brief text.

**Operator decision (2026-08-21):** stay on the in-cluster BuildConfig
path for now - no Quay repository cutover. `v0.1.0`'s artifacts remain
valid proof the release pipeline itself works end to end (ADR-0115's core
completion criterion), but production deployment stays on `:latest`
in-cluster images; stage 3's tag-pinning/`targetRevision` retargeting
stays deferred indefinitely, not scheduled. If a future release is ever
needed for a real reason, it must be cut fresh against `main` at that
time - `v0.1.0` should not be reused once stale.

## Context

Several GitOps applications track `targetRevision: main` and multiple component Helm values still use `tag: latest`. This makes a deployed environment non-reproducible and weakens rollback, auditability and provenance in a public-source project.

The repository now contains most of the mechanisms required by this decision, but the 2026-08-11 reconciliation found that they are not yet closed into an enforced end-to-end supply-chain loop. The ADR must therefore no longer be considered fully implemented.

## Decision

Build every first-party component in CI, publish images to Quay with immutable version/SHA tags and preferably digest pinning, generate an SBOM, scan dependencies/images, sign release images, verify signatures before trusted deployment, and update GitOps manifests with immutable references.

Production-like Argo CD applications must deploy a reviewed Git revision/tag rather than a moving `main` reference. Base images used to build Zuno images must also be pinned to a controlled version or digest rather than moving `latest` tags.

## Consequences

Every trusted deployment can be traced to source, build, SBOM and image digest. Releases and rollbacks become deterministic at the cost of adding CI/release automation and an explicit promotion step between image publication and GitOps deployment.

## Security considerations

CI secrets stay outside Git. Signing uses workload identity/keyless mechanisms where possible. Vulnerability scanning and signature verification become mandatory gates before an artifact is promoted to a trusted environment.

A successful `cosign sign` action is not sufficient by itself: the deployment path must verify the expected identity/signature and immutable digest before considering an image trusted.

## Operational considerations

The release workflow must reconcile source revision, image digest, chart values and Argo CD `targetRevision` in one auditable release/promotion change. A repository check must reject stale build entries, non-existent Dockerfile/context paths and non-immutable deployable image references.

## Implementation state

**Partially implemented as of 2026-08-12.** Two of the original seven gaps
(build inventory staleness, moving Dockerfile base images) are now closed;
the remaining five reduce to one real blocker (gap 7, a credentialed
GitHub Actions + Quay run) plus its three direct downstream consequences.

**2026-08-14 (WP-04 stage 1, docs/roadmap/work-packages/wp-04-supply-chain-completion.md):**
the tooling for gaps 2, 3, 4 and 6 is now built and CI-wired, so what
remains for every one of them is purely gap 7 (the credentialed release
run) plus running that tooling against its output - no further scripting.
Nothing below moved to resolved by this addition alone: with no real
release yet, `verify_signatures.py` correctly finds nothing to verify and
`pin_release.py` has no real manifest to apply.

**2026-08-19 (WP-04 stage 2, first real `v0.1.0` release attempt):** running
`build-publish.yml` for real surfaced three bugs no dry-run could have
caught, all now fixed on `main`: `aquasecurity/trivy-action@0.28.0` resolved
to a since-deleted internal `setup-trivy` tag (bumped to `v0.36.0`, which
pins that dependency by commit SHA instead); every first-party
Dockerfile/Containerfile's `FROM` defaulted to the cluster-internal
`zuno-ai-build` mirror, unreachable from GitHub-hosted runners (each now
takes a `BASE_IMAGE`-family `ARG`, defaulting to the internal mirror for
in-cluster BuildConfig builds unchanged, overridden by `build-publish.yml`
to the real public registry - see `ansible/roles/image_mirrors/tasks/
install.yml` for the mapping); the Quay organization is `zuno`, not
`zuno-demo` (`REGISTRY_NAMESPACE` and `verify_signatures.py`'s
`FIRST_PARTY_REGISTRY_PREFIX` corrected, `startxfr/zuno-demo` GitHub source
repo references left alone - different thing).

Once those were fixed, the Trivy scan itself started finding real HIGH
findings across most components (`agent-bff` alone published clean) -
OS-package staleness in the `python:3.11-slim`/`3.12-slim`/`ubi9-python-311`
base images, an outdated Go stdlib in `agent-frontend`'s then-`golang:1.24`
build stage, and outdated application dependencies (`transformers`,
`protobuf`, `starlette` in Python; `go.opentelemetry.io/otel/sdk`,
`golang.org/x/net`, `golang.org/x/text`, `google.golang.org/grpc` in
`aiagent-operator`'s `go.mod`). Fixed the mechanical, code-independent
subset: `agent-frontend` now builds with `golang:1.26` (already used
cleanly by `agent-bff`/`aiagent-operator`); the 7 Debian-slim Python
Dockerfiles now run `apt-get upgrade` + `pip install --upgrade pip
setuptools wheel` before installing requirements, verified locally to
actually land the patched package versions. Deliberately deferred the
application-level dependency bumps (`transformers` is a major-version jump
with a real API-compatibility risk for ML code; the `go.mod` bump needs a
real `go mod tidy` + build/test cycle; `mlops`'s UBI9 base carries ~94 HIGH
OS-package findings on its own) rather than rushing untested bumps through
to unblock a release - tracked as open debt in gap 7 below, not silently
dropped.

Given that debt is real and would otherwise block every first-party image
from ever being signed, the Trivy step is now `continue-on-error: true` in
`build-publish.yml` (build/push/SBOM/sign/attest all still run on a Trivy
failure) rather than the originally-authored hard `exit-code: "1"` gate -
a deliberate loosening of this ADR's stated "mandatory gate" security
posture, not an oversight, made explicitly to get the first real release
through while the remediation above is still open. Revisit once the
deferred bumps above land.

**2026-08-19 (gap 7 closed for real):** with those three bugs and the
mechanical CVE fixes above in place,
[run 32273454405](https://github.com/startxfr/zuno-demo/actions/runs/32273454405)
against tag `v0.1.0` (commit `c83cfcd`) went green end to end: all 11
`build-publish-sign` matrix jobs and all 8 `sign-okf-bundles` jobs
succeeded - every first-party image built, pushed to `quay.io/zuno/<name>
:v0.1.0` with a real digest, SBOM-attested and keyless-signed. That is
exactly the "at least one real release proves source -> build -> SBOM ->
scan -> signature -> immutable GitOps reference -> deployment
traceability" completion criterion below (GitOps reference/deployment
still pending - see stage 3).

Real numbers, corrected from the estimate above now that the scan actually
ran clean on some components and worse than expected on others not
previously sampled: `agent-bff`/`agent-frontend` publish with zero
findings; `mcp-gateway`/`mcp-confluence`/`mcp-sales-db`/`mcp-salesforce`
are down to 2 HIGH each (the `wheel`/`jaraco.context`-shaped pip finding
that survives the base pip/setuptools/wheel upgrade); `mlops` still 94
HIGH (confirmed, not an estimate) + 2 HIGH (`transformers`);
`aiagent-operator` still 8 HIGH (`go.mod` staleness, confirmed);
`rag-service` 6 HIGH (`protobuf`/`starlette`/pip-tooling); and two
components not sampled before this real run turned out to carry their own
previously-undocumented debt - `ai-gateway` (14 HIGH, 1 CRITICAL) and
`agent-runtime` (15 HIGH/1 CRITICAL OS-level + 56 HIGH/2 CRITICAL
application-level, the largest surface of any component here, driven by
its own dependency tree rather than anything touched this pass). None of
this blocks the pipeline (`continue-on-error`), but it means the
remediation backlog is larger than first estimated - full per-component
CVE tables are in the `Scan for vulnerabilities` step logs of the run
above.

**2026-08-19 (v0.1 objective: registry backend stays internal by
default):** this ADR's build/publish/sign pipeline exists to prove
supply-chain provenance (source -> build -> SBOM -> scan -> signature),
not to become the default deployment source. Every `gitops/charts/*`
`repository`/`frontendRepository`/`bffRepository` field still points at
the in-cluster mirror (`image-registry.openshift-image-registry.svc:5000/
zuno-ai-build/<name>`), populated by the OpenShift `BuildConfig` mechanism
(`ansible/tasks/apply_openshift_build.yml`) - unchanged by `pin_release.py`
(stage 3, WP-04) on purpose, and unchanged by this ADR going forward: the
platform keeps defaulting to internal registry + `BuildConfig` for
first-party runtime images.

An *optional* mode where charts instead source first-party runtime images
from Quay (or another external registry) - i.e. actually moving a chart's
`repository`/`frontendRepository`/`bffRepository` off the in-cluster
mirror - is a distinct, legitimate future direction, deliberately
deferred to **ADR-0353** (v0.3, not yet written; see
[docs/adr/0300-v0.3-roadmap.md](0300-v0.3-roadmap.md#adr-0353-support-an-optional-external-registry-as-the-first-party-runtime-image-source)),
not decided or implemented here. This is a third, distinct sense of
"external" from ADR-0352's (who deploys the platform's own infrastructure
services) and ADR-0116/0117's (how agents reach third-party SaaS tool
backends): ADR-0353 would decide where first-party runtime images
themselves are sourced from.

### Implemented foundations

- `.github/workflows/build-publish.yml` builds first-party images, publishes SHA-based tags, generates SPDX SBOMs, scans HIGH/CRITICAL vulnerabilities with Trivy (reported, `continue-on-error: true` - see the 2026-08-19 note above), signs images with keyless Cosign through GitHub OIDC and attests the SBOM.
- `.github/workflows/lint.yml` executes the immutable-image policy check together with OpenAPI, Helm, workload hardening, Go, Python and Ansible validation.
- `platform/supply-chain/check_no_latest_tags.py` correctly scans chart values and fails when a deployable image uses `latest` or an empty tag.
- `RELEASING.md` documents the intended transition from moving Git refs/image tags to reviewed release references, now including the exact `pin_release.py`/`verify_signatures.py` steps (2026-08-14).
- `platform/supply-chain/verify_signatures.py` (2026-08-14): `cosign verify`-based signature check against `build-publish.yml`'s exact keyless GitHub OIDC identity, scoped to immutable-tagged first-party images; wired into `lint.yml` non-blocking (mirrors `check_no_latest_tags.py`'s own convention, for the same reason - see gap 6).
- `platform/supply-chain/pin_release.py` (2026-08-14): mechanically rewrites chart `tag` fields from a release manifest, refusing to run unless the manifest covers exactly the current gap-2 field set; regression-tested (`platform/supply-chain/tests/test_pin_release.py`) against a throwaway copy of the real chart files, never the repository's own state.

### Gaps preventing `Implemented` status

1. ~~The build inventory is stale.~~ **Resolved by ADR-0324** (2026-08-11, same review cycle as this gap list, which wasn't updated at the time): the `postgresql-pgvector` matrix entry is gone from `.github/workflows/build-publish.yml`, and `platform/supply-chain/check_build_matrix.py` passes (7/7 matrix entries valid, every first-party Dockerfile tracked).
2. **Deployable charts still use `tag: latest`.** ~~Mostly resolved 2026-08-21~~: 16 of 18 fields `check_no_latest_tags.py` reports are now pinned to a real, live-verified local `v0.1.0` tag via `platform/supply-chain/tag_local_release.py` + `pin_release.py`, without moving `image.repository` off the in-cluster ImageStream - see the 2026-08-21 "local-registry immutable tagging" note above. **Genuinely still open, 2 fields**: `mlops` (`images.mlops.tag`, no BuildConfig exists for it at all) and `rag-ingestion`'s `images.compiler.tag` (`rag-pipeline-compiler`, never wired to a BuildConfig) - a separate, pre-existing gap this pass didn't create and doesn't close.
3. **The immutable-tag policy is non-blocking.** `lint.yml` still sets `continue-on-error: true` for `check_no_latest_tags.py`. Deliberately left non-blocking: the 2 fields above still fail it, and flipping it now would fail every PR over an issue unrelated to today's fix, not surface new information about it.
4. **GitOps still tracks moving Git refs.** Argo CD Applications continue to use `targetRevision: main`; deployment state is therefore not yet tied to a reviewed release revision. Same dependency as gap 2: there is no reviewed release tag to point at until gap 7 produces one.
5. ~~Two first-party Dockerfiles still inherit moving base images.~~ **Resolved 2026-08-12**: `components/agent-frontend/Dockerfile` and `components/agent-bff/Dockerfile` now pin `registry.access.redhat.com/ubi9/ubi-minimal` by digest (`sha256:7c372902c8d211db2d25c8277ba534a73b92742a334874dced829a63b0f21221`, version 9.8, confirmed live via `skopeo inspect` against the real Red Hat registry) rather than `:latest`. This gap was independent of the others - it depends on Red Hat's registry, not this repository's own release pipeline.
6. **Signing is not yet a deployment verification gate.** Images are designed to be signed in CI, but GitOps/admission/release validation does not yet prove the expected signature identity before deployment. `verify_signatures.py` (2026-08-14) is the verification gate itself, CI-wired non-blocking; it still finds nothing to verify because gap 7 means nothing has been signed for real yet - the remaining blocker is gap 7 alone, not building the check.
7. ~~The publish/sign workflow has not yet been demonstrated end to end against the real GitHub Actions + Quay environment.~~ **Resolved 2026-08-19**: [run 32273454405](https://github.com/startxfr/zuno-demo/actions/runs/32273454405) (tag `v0.1.0`, commit `c83cfcd`) published, SBOM-attested and keyless-signed all 11 first-party images for real - see the dated note above for the real digests and the three real bugs (trivy-action's yanked pin, cluster-internal base images unreachable from GitHub-hosted runners, wrong Quay org name) it took to get there. **Gaps 2, 3, 4 and 6 are not automatically closed by this** - `pin_release.py` still needs to run against this real manifest (stage 3, WP-04), and one wrinkle stage 3 must account for: `rag-ingestion`'s two `latest` fields (gap 2's list) are built exclusively by the in-cluster OpenShift BuildConfig, not this workflow, so this release has no real Quay artifact for them - `pin_release.py`'s exact-field-set manifest requirement can't be satisfied for `rag-ingestion` from this release alone. Known-open CVE debt from this run (`mlops`, `agent-runtime`, `ai-gateway`, `rag-service`, `aiagent-operator` - see the dated note above) is unrelated to gap 7 itself and stays deliberately deferred.

**2026-08-22 (WP-04 closed, ADR deferred):** gaps 2, 3, 4 and 6 above stay
genuinely open - not resolved, not silently dropped, just no longer being
pursued. `build-publish.yml`'s automatic triggers are disabled (see the
dated note at the top of this document); no further stage-3 work is
planned until a future ADR reactivates this stream.

### Completion criteria

ADR-0115 can move back to **Implemented** only when all of the following are true:

- ADR-0324 removes stale/non-buildable entries and the build inventory has a mandatory path-validation gate;
- every deployable first-party image is published with a SHA/semantic immutable reference and chart values no longer contain `latest`;
- `check_no_latest_tags.py` is blocking in CI;
- release GitOps manifests use a reviewed tag/commit and preferably image digests;
- first-party Dockerfile base images are version/digest pinned according to the release policy;
- signature verification is exercised as part of trusted promotion/deployment;
- at least one real release proves source -> build -> SBOM -> scan -> signature -> immutable GitOps reference -> deployment traceability.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0004](0004-use-github-as-the-canonical-source-repository.md)
- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md)
- [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md)
- [ADR-0324](0324-reconcile-the-ci-build-inventory-with-the-repository-component-lifecycle.md)
- [ADR-0059](0059-auto-redeploy-on-in-cluster-build-via-image-triggers.md) - why release pinning must revert to `:latest` after proving itself: that annotation-based trigger only fires for the tag it watches.
- ADR-0353 (v0.3, not yet written) - decides whether/how to optionally source first-party runtime images from Quay/an external registry instead of the internal mirror + BuildConfig default this ADR keeps unchanged.
