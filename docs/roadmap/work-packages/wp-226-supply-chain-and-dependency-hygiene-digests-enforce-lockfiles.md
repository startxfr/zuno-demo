# WP-226: Supply chain and dependency hygiene: digests, enforce mode, lockfiles (delivers ADR-0603)

- **State:** Not started
- **ADRs:** ADR-0603
- **Depends on:** WP-222
- **Blocks:** WP-227
- **Estimated files touched:** ~40

> Execute this brief as a standalone task from the repository root.

## Goal

Make what runs the same bytes that were built and reviewed (M16 to M18, M20), and triage the certificate-verification
exceptions (M3).

## ADR references

ADR-0603 clause 4.

## Preconditions

- Read `RELEASING.md`, ADR-0535, `platform/supply-chain/pinned-releases.yaml` and the two pin checkers
  (`check_no_latest_tags.py`, `check_unifai_pins.py`) to see why `:latest` charts pass.
- Every release pin needs the user's go (memory: pin every release with the user's go).

## Repo changes

1. Render image digests into chart values at release; pin base images with `@sha256`; stop `pullPolicy: Always` on pinned images.
2. `ClusterImagePolicy`: run warn mode against the live cluster, fix what it reports, then switch to enforce.
3. Sign CI-built images keylessly; attach SBOMs as attestations; verify the cosign download by checksum; drop
   `ignore-unfixed` or record why it stays.
4. Hashed lockfiles (`pip-compile --generate-hashes`) and one version per library across components; pin
   `kubernetes.core`; Dependabot for actions and Python.
5. Triage the `validate_certs`/`insecure` hits: fix, or keep with a one-line reason in the file.
6. `evaluations/.venv-gate`: run the untrack step left by WP-222 and decide whether to purge history.

## Verification

`make` pin checks pass with the new digests; an unsigned image is refused in enforce mode on a test namespace; a clean install
from the lockfiles gives the hashes recorded.
