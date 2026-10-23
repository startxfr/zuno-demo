# .github

This repository's CI implementation - three workflows now exist (earlier
ADRs referencing ".github/workflows/ doesn't exist yet" predate this):

- **`workflows/lint.yml`** - static checks needing no live cluster,
  registry or credentials: the repository's policy-as-code scripts
  (`platform/security/check_workload_hardening.py`,
  `platform/supply-chain/check_build_matrix.py`, ...), `helm lint` on every
  chart, the standalone Python test suites (`components/mcp-gateway/`,
  `components/ai-gateway/`, `components/rag-service/tests/`, ...), and an `ansible-playbook --syntax-check`
  pass over every playbook. Runs on every pull request and every push to
  `main`. Agent definitions and the corp policies are not in this
  repository (ADR-0576, WP-165): the jobs that read them (policy-as-code,
  python, quality-gate) install `cosign` and `oras` and extract the release
  pinned in `platform/okf/agents.lock` with
  `platform/okf/release_cache.py`, and the `okf-release` job re-verifies
  that release offline and checks the files generated from it.
- **`workflows/okf-promote.yml`** - promotes a zuno-demo-agents release
  (ADR-0580): verifies it, moves `platform/okf/agents.lock`, regenerates
  the stack configuration and quota files, and opens a pull request with
  a semantic diff. Scheduled, and runnable by hand with a release tag. See
  `RELEASING.md`'s "Agents release".
- **`workflows/build-publish.yml`** - builds every component
  image, publishes to Quay with an immutable `sha-<commit>` tag (plus the
  semantic version tag on an actual `v*` release tag push), generates an
  SPDX SBOM, scans for HIGH/CRITICAL vulnerabilities (fails the build),
  and signs the image keylessly via `cosign` (Sigstore/Fulcio, using
  GitHub's own OIDC identity). Requires `QUAY_USERNAME`/`QUAY_PASSWORD` as
  encrypted GitHub repository secrets, never committed. **Disabled
  (2026-08-22, WP-04/ADR-0115 closed)** - the push/tag triggers were
  removed, so it no longer fires automatically; it stays manually runnable
  via `workflow_dispatch` and ready to have its triggers restored under a
  future ADR if this supply-chain stream is reactivated.

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
`build-publish.yml`'s SBOM'd/immutable-tagged publish path) is meant to
work, and why `gitops/apps/*/application.yaml`'s `targetRevision: main`
hasn't been rewritten to point at a tag yet. Signing itself no longer
happens in this workflow at all - ADR-0420 moved it in-cluster (Vault
Transit), since a GitHub-hosted runner has no route to sign against it;
see `platform/supply-chain/README.md`.
