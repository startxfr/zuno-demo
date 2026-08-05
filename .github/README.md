# .github

ADR-0051's CI implementation. Every other ADR in this repository that
mentions ".github/workflows/ doesn't exist yet" was written before this
landed - two workflows now exist:

- **`workflows/lint.yml`** - static checks needing no live cluster,
  registry or credentials: the repository's policy-as-code scripts
  (`platform/security/check_workload_hardening.py`,
  `platform/api/lint_openapi.py`,
  `platform/supply-chain/check_no_latest_tags.py`), `helm lint` on every
  chart, `go build`/`vet`/`gofmt`/`test` on the two Go components, the
  standalone Python test suites (`components/agent-runtime/tests/`,
  `components/rag-service/tests/`), and an `ansible-playbook --syntax-check`
  pass over every playbook. Runs on every pull request and every push to
  `main`.
- **`workflows/build-publish.yml`** (ADR-0051) - builds every component
  image, publishes to Quay with an immutable `sha-<commit>` tag (plus the
  semantic version tag on an actual `v*` release tag push), generates an
  SPDX SBOM, scans for HIGH/CRITICAL vulnerabilities (fails the build),
  and signs the image keylessly via `cosign` (Sigstore/Fulcio, using
  GitHub's own OIDC identity - no pre-provisioned signing key or secret).
  Requires `QUAY_USERNAME`/`QUAY_PASSWORD` as encrypted GitHub repository
  secrets (never committed - ADR-0051 Security considerations: "CI
  secrets stay outside Git").

## What hasn't run

Neither workflow has actually executed in a real GitHub Actions
environment - this repository was built in a sandbox with no live Quay
credentials and no GitHub Actions runner to exercise it against (the same
constraint every other ADR in this build has been honest about for a live
OpenShift cluster). Both files' YAML was parsed and validated
(`python3 -c "import yaml; yaml.safe_load(...)"`) and every script/command
they invoke was run directly and does pass (or, for
`check_no_latest_tags.py`, correctly and currently fails against this
repository's real state - see `platform/supply-chain/README.md`), but the
workflow orchestration itself (action versions, GitHub Actions expression
syntax, matrix behavior) is unverified beyond careful authorship against
well-documented, widely-used actions.

See `RELEASING.md` for how a real release (a `v*` tag, triggering
`build-publish.yml`'s signed/SBOM'd/immutable-tagged publish path) is
meant to work, and why `gitops/apps/*/application.yaml`'s
`targetRevision: main` hasn't been rewritten to point at a tag yet.
