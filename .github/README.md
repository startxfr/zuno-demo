# .github

This repository's CI implementation - two workflows now exist (earlier
ADRs referencing ".github/workflows/ doesn't exist yet" predate this):

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
- **`workflows/build-publish.yml`** - builds every component
  image, publishes to Quay with an immutable `sha-<commit>` tag (plus the
  semantic version tag on an actual `v*` release tag push), generates an
  SPDX SBOM, scans for HIGH/CRITICAL vulnerabilities (fails the build),
  and signs the image keylessly via `cosign` (Sigstore/Fulcio, using
  GitHub's own OIDC identity). Requires `QUAY_USERNAME`/`QUAY_PASSWORD` as
  encrypted GitHub repository secrets, never committed.

## What hasn't run

Neither workflow has executed in a real GitHub Actions environment: this
repository was built in a sandbox, with no live Quay credentials or
Actions runner to test against. Both files' YAML was parsed and validated
(`python3 -c "import yaml; yaml.safe_load(...)"`) and every script/command
they invoke was run directly and does pass (or, for
`check_no_latest_tags.py`, correctly and currently fails against this
repository's real state - see `platform/supply-chain/README.md`), but the
workflow orchestration itself remains unverified.

See `RELEASING.md` for how a real release (a `v*` tag, triggering
`build-publish.yml`'s signed/SBOM'd/immutable-tagged publish path) is
meant to work, and why `gitops/apps/*/application.yaml`'s
`targetRevision: main` hasn't been rewritten to point at a tag yet.
