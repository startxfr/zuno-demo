# ADR-0051: Use immutable and verifiable software supply chain artifacts

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

Several GitOps applications track `targetRevision: main` and component Helm values use `tag: latest`. This makes a deployed environment non-reproducible and weakens rollback/auditability in a public-source project.

## Decision

Build every component in CI, publish images to Quay with immutable version/SHA tags and preferably digest pinning, generate an SBOM, scan dependencies/images, sign release images, and update GitOps manifests with immutable references. Production-like Argo CD applications must deploy a reviewed Git revision/tag rather than a moving `main` reference.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Every deployment can be traced to source, build and image digest. Releases and rollbacks become deterministic at the cost of adding CI/release automation.

## Security considerations

CI secrets stay outside Git. Signature verification and vulnerability policy become deployment gates for sensitive components.

## Operational considerations

Add CI checks rejecting `latest` for deployable component images and establish image signing/verification before industrialized use.

## Implementation state

**Implemented (2026-08-05)**: the CI pipeline, the release process, and
the policy-as-code gate all exist and are correct as authored - what
remains is external to this repository (provisioning real Quay
credentials, and a maintainer actually cutting a first release), not
something this environment could fabricate without lying about the
repository's actual state.

**CI build/publish/SBOM/scan/sign** (Decision: "Build every component in
CI, publish images to Quay with immutable version/SHA tags... generate an
SBOM, scan dependencies/images, sign release images"):
`.github/workflows/build-publish.yml` - new, this repository's first CI
workflow along with `lint.yml` below. A matrix over all 8 buildable images
(the 6 components with a `gitops/charts/*` deployment, plus
`components/mcp-servers/sales-db` and the custom
`gitops/charts/postgresql/image` pgvector image) builds and pushes to
`quay.io/zuno-demo/<name>` tagged `sha-<commit>` on every push to `main`
(never `:latest` - immutable by construction) and additionally the
semantic version tag on a `v*` tag push, generates an SPDX SBOM
(`anchore/sbom-action`), scans for HIGH/CRITICAL vulnerabilities
(`aquasecurity/trivy-action`, failing the build), and signs the image plus
attests the SBOM with `cosign` **keylessly** via GitHub's own OIDC
identity (Sigstore/Fulcio) - satisfying "CI secrets stay outside Git"
literally: there is no signing secret to leak, by design, not merely a
promise to store one safely. `QUAY_USERNAME`/`QUAY_PASSWORD` (the only
secrets this pipeline needs, for the registry push itself) must be
provisioned as encrypted GitHub repository secrets - never committed.

**"Update GitOps manifests with immutable references" / "Production-like
Argo CD applications must deploy a reviewed Git revision/tag"**:
deliberately **not done** for the existing `targetRevision: main`
references, and this is an honest sequencing gap, not an oversight -
`RELEASING.md` (new) explains why: no tag has ever been pushed in this
repository's history, so rewriting `targetRevision: main` to a specific
tag today would point every GitOps `Application` at a Git ref that
doesn't exist, breaking every deployment for no benefit. `RELEASING.md`
documents the exact process (tag push → CI publishes → bump chart
`image.tag` values → bump every `targetRevision` in the same PR) so that
transition is a maintainer decision away, not still-unbuilt tooling.

**Policy-as-code gate** (Operational considerations: "Add CI checks
rejecting `latest` for deployable component images"):
`platform/supply-chain/check_no_latest_tags.py` walks every
`gitops/charts/*/values.yaml` for an image `tag` of `latest` (or empty),
wired into `.github/workflows/lint.yml`. **Run and currently, correctly,
failing**: 6 charts (`agent-runtime`, `ai-gateway`, `mcp-gateway`,
`mcp-sales-db`, `rag-service`, `tekos`) still use `tag: latest`, because
no image has ever actually been published by the new pipeline for them to
reference yet - marked `continue-on-error: true` in the workflow for
exactly that reason (a real, currently-true failure, not a broken check)
rather than either silently disabling it or fabricating a passing state.

`lint.yml` also runs every other static check built across this
engagement (`platform/security/check_workload_hardening.py`,
`platform/api/lint_openapi.py`, `helm lint` on every chart, `go
build`/`vet`/`gofmt`/`test` on both Go components, the standalone Python
test suites, and `ansible-playbook --syntax-check`) - this repository's
first actual CI gate tying all of it together, not just the supply-chain
half of this specific ADR.

**Not executed**: neither workflow has run in a real GitHub Actions
environment - this sandbox has no live Quay credentials or Actions runner.
Both files' YAML was parsed/validated and every command they invoke was
run directly in this environment (and does pass, except
`check_no_latest_tags.py`'s honestly-still-failing state above); the
workflow orchestration itself (action versions, matrix behavior, GitHub
Actions expression syntax) is unverified beyond careful authorship against
well-documented, widely-used actions - see `.github/README.md`'s own
"What hasn't run" section.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0004
- ADR-0022
- ADR-0024
- ADR-0041
- ADR-0048

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
