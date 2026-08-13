# ADR-0115: Use immutable and verifiable software supply chain artifacts

- **Status:** Partially implemented
- **Target:** v1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0051, retargeted v0 -> v1 (2026-08-13 roadmap reorganization; the remaining gaps are release-cycle work)
- **Last reviewed:** 2026-08-12

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

### Implemented foundations

- `.github/workflows/build-publish.yml` builds first-party images, publishes SHA-based tags, generates SPDX SBOMs, scans HIGH/CRITICAL vulnerabilities with Trivy, signs images with keyless Cosign through GitHub OIDC and attests the SBOM.
- `.github/workflows/lint.yml` executes the immutable-image policy check together with OpenAPI, Helm, workload hardening, Go, Python and Ansible validation.
- `platform/supply-chain/check_no_latest_tags.py` correctly scans chart values and fails when a deployable image uses `latest` or an empty tag.
- `RELEASING.md` documents the intended transition from moving Git refs/image tags to reviewed release references.

### Gaps preventing `Implemented` status

1. ~~The build inventory is stale.~~ **Resolved by ADR-0324** (2026-08-11, same review cycle as this gap list, which wasn't updated at the time): the `postgresql-pgvector` matrix entry is gone from `.github/workflows/build-publish.yml`, and `platform/supply-chain/check_build_matrix.py` passes (7/7 matrix entries valid, every first-party Dockerfile tracked).
2. **Deployable charts still use `tag: latest`.** `check_no_latest_tags.py` reports 8 fields across 7 charts as of 2026-08-12: `agent-runtime`, `ai-gateway`, `mcp-gateway`, `mcp-sales-db`, `rag-service`, `tekos` (`image.tag`), plus `rag-ingestion` (`images.ingestion.tag`, `images.compiler.tag`, added by ADR-0330 after this gap list was first written). **Genuinely blocked on gap 7**: pinning these to a real immutable reference now, before any real build-publish-sign cycle has run, would mean writing a tag that doesn't exist in the registry - the honest fix is a real release, not a placeholder SHA.
3. **The immutable-tag policy is non-blocking.** `lint.yml` still sets `continue-on-error: true` for `check_no_latest_tags.py`. Deliberately left non-blocking until gap 2 is actually closed - flipping it now would just make every merge fail on the still-open `latest` references above, not surface new information.
4. **GitOps still tracks moving Git refs.** Argo CD Applications continue to use `targetRevision: main`; deployment state is therefore not yet tied to a reviewed release revision. Same dependency as gap 2: there is no reviewed release tag to point at until gap 7 produces one.
5. ~~Two first-party Dockerfiles still inherit moving base images.~~ **Resolved 2026-08-12**: `components/agent-frontend/Dockerfile` and `components/agent-bff/Dockerfile` now pin `registry.access.redhat.com/ubi9/ubi-minimal` by digest (`sha256:7c372902c8d211db2d25c8277ba534a73b92742a334874dced829a63b0f21221`, version 9.8, confirmed live via `skopeo inspect` against the real Red Hat registry) rather than `:latest`. This gap was independent of the others - it depends on Red Hat's registry, not this repository's own release pipeline.
6. **Signing is not yet a deployment verification gate.** Images are designed to be signed in CI, but GitOps/admission/release validation does not yet prove the expected signature identity before deployment. Blocked on gap 7 (nothing has been signed for real yet to verify against).
7. **The publish/sign workflow has not yet been demonstrated end to end against the real GitHub Actions + Quay environment.** The workflow is authored, but repository evidence does not yet prove a successful publication/promotion cycle with real credentials and registry artifacts. **This is the actual blocker for gaps 2, 3, 4 and 6** - they are one connected release-and-promote step, not four independent fixes, and need real Quay/GitHub Actions credentials to close for real rather than being faked with placeholder tags.

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
