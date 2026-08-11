# ADR-0051: Use immutable and verifiable software supply chain artifacts

- **Status:** Partially implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team
- **Last reviewed:** 2026-08-11

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

**Partially implemented as of 2026-08-11.**

### Implemented foundations

- `.github/workflows/build-publish.yml` builds first-party images, publishes SHA-based tags, generates SPDX SBOMs, scans HIGH/CRITICAL vulnerabilities with Trivy, signs images with keyless Cosign through GitHub OIDC and attests the SBOM.
- `.github/workflows/lint.yml` executes the immutable-image policy check together with OpenAPI, Helm, workload hardening, Go, Python and Ansible validation.
- `platform/supply-chain/check_no_latest_tags.py` correctly scans chart values and fails when a deployable image uses `latest` or an empty tag.
- `RELEASING.md` documents the intended transition from moving Git refs/image tags to reviewed release references.

### Gaps preventing `Implemented` status

1. **The build inventory is stale.** `.github/workflows/build-publish.yml` still contains the `postgresql-pgvector` matrix entry referencing `gitops/charts/postgresql/image/Dockerfile`, although that custom image was removed when PostgreSQL moved to the Crunchy PGO operand image. ADR-0324 owns this repository/CI reconciliation.
2. **Six deployable charts still use `tag: latest`.** The current policy check reports `agent-runtime`, `ai-gateway`, `mcp-gateway`, `mcp-sales-db`, `rag-service` and `tekos`.
3. **The immutable-tag policy is non-blocking.** `lint.yml` currently sets `continue-on-error: true` for `check_no_latest_tags.py`; a known failure is reported but cannot block a merge.
4. **GitOps still tracks moving Git refs.** Argo CD Applications continue to use `targetRevision: main`; deployment state is therefore not yet tied to a reviewed release revision.
5. **Two first-party Dockerfiles still inherit moving base images.** `components/agent-frontend/Dockerfile` and `components/agent-bff/Dockerfile` use `registry.access.redhat.com/ubi9/ubi-minimal:latest`.
6. **Signing is not yet a deployment verification gate.** Images are designed to be signed in CI, but GitOps/admission/release validation does not yet prove the expected signature identity before deployment.
7. **The publish/sign workflow has not yet been demonstrated end to end against the real GitHub Actions + Quay environment.** The workflow is authored, but repository evidence does not yet prove a successful publication/promotion cycle with real credentials and registry artifacts.

### Completion criteria

ADR-0051 can move back to **Implemented** only when all of the following are true:

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
