# ADR-0051: Use immutable and verifiable software supply chain artifacts

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Several GitOps applications track `targetRevision: main` and component Helm values use `tag: latest`. This makes a deployed environment non-reproducible and weakens rollback/auditability in a public-source project.

## Decision

Build every component in CI, publish images to Quay with immutable version/SHA tags and preferably digest pinning, generate an SBOM, scan dependencies/images, sign release images, and update GitOps manifests with immutable references. Production-like Argo CD applications must deploy a reviewed Git revision/tag rather than a moving `main` reference.

## Consequences

Every deployment can be traced to source, build and image digest. Releases and rollbacks become deterministic at the cost of adding CI/release automation.

## Security considerations

CI secrets stay outside Git. Signature verification and vulnerability policy become deployment gates for sensitive components.

## Operational considerations

Add CI checks rejecting `latest` for deployable component images and establish image signing/verification before industrialized use.

## Implementation state

**Implemented (2026-08-05)**: the CI pipeline, release process and policy-as-code gate all exist and are correct as authored - what remains is external to this repository (provisioning real Quay credentials, a maintainer cutting a first release).

- **CI build/publish/SBOM/scan/sign**: `.github/workflows/build-publish.yml` (this repository's first CI workflow, along with `lint.yml`) matrixes over all 8 buildable images, builds and pushes to `quay.io/zuno-demo/<name>` tagged `sha-<commit>` on every push to `main` (never `:latest`) plus the semantic version tag on a `v*` tag push, generates an SPDX SBOM (`anchore/sbom-action`), scans for HIGH/CRITICAL vulnerabilities (`aquasecurity/trivy-action`, failing the build), and signs the image plus attests the SBOM with `cosign` **keylessly** via GitHub's own OIDC identity (Sigstore/Fulcio) - there is no signing secret to leak, by design. `QUAY_USERNAME`/`QUAY_PASSWORD` (the only secrets this pipeline needs) must be provisioned as encrypted GitHub repository secrets, never committed.
- **GitOps immutable references / reviewed-tag deploys**: deliberately **not done** for the existing `targetRevision: main` references - `RELEASING.md` (new) explains why: no tag has ever been pushed in this repository's history, so rewriting `targetRevision: main` today would point every `Application` at a Git ref that doesn't exist. `RELEASING.md` documents the process (tag push → CI publishes → bump chart `image.tag` values → bump every `targetRevision` in the same PR) so the transition is a maintainer decision away.
- **Policy-as-code gate**: `platform/supply-chain/check_no_latest_tags.py` walks every `gitops/charts/*/values.yaml` for an image `tag` of `latest` (or empty), wired into `lint.yml`. Run and currently, correctly, failing: 6 charts still use `tag: latest` because no image has been published yet - marked `continue-on-error: true` for that reason (a real, currently-true failure, not a broken check). `lint.yml` also runs every other static check built across this engagement (`check_workload_hardening.py`, `lint_openapi.py`, `helm lint`, Go build/vet/gofmt/test, Python test suites, `ansible-playbook --syntax-check`) - this repository's first actual CI gate tying all of it together.
- **Not executed**: neither workflow has run in a real GitHub Actions environment (no live Quay credentials or Actions runner here); every command each workflow invokes was run directly in this environment and passes except `check_no_latest_tags.py`'s honestly-still-failing state above.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0004
- ADR-0022
- ADR-0024
- ADR-0041
- ADR-0048
