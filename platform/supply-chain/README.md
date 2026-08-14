# Platform: supply chain

Software supply chain policy (ADR-0115: "Use immutable and verifiable
software supply chain artifacts").

`check_no_latest_tags.py` is the policy-as-code check that ADR's
Operational considerations ask for ("Add CI checks rejecting `latest` for
deployable component images"): walks every `gitops/charts/*/values.yaml`
looking for an image `tag` set to the literal `latest` (or left empty).
No live cluster or registry needed - pure static YAML inspection, same
style as `platform/security/check_workload_hardening.py`.

```bash
python3 platform/supply-chain/check_no_latest_tags.py
```

**This currently fails, honestly.** 7 charts (`agent-runtime`,
`ai-gateway`, `mcp-gateway`, `mcp-sales-db`, `rag-service`, `tekos`,
`rag-ingestion` - the last with two image fields) still use `tag: latest`,
because the CI pipeline that would publish real immutable tags for them to
reference (`.github/workflows/build-publish.yml`) has never actually
run - this sandbox has no live Quay credentials or a real GitHub Actions
environment to run it in. The check is written to be genuinely CI-usable
the moment that pipeline runs for real and these values get bumped to the
tags it publishes (mechanically, via `pin_release.py` below) - see
`docs/adr/0115-*.md`'s Implementation state for the full reasoning, and
`.github/README.md` for what the workflow itself does.

Wired into `.github/workflows/lint.yml` alongside the other repository
policy-as-code checks (`platform/security/check_workload_hardening.py`,
`platform/api/lint_openapi.py`) - see that workflow.

## check_build_matrix.py

`check_build_matrix.py` is the policy-as-code check ADR-0324 ("Reconcile
the CI build inventory with the repository component lifecycle") asks
for: validates `.github/workflows/build-publish.yml`'s build matrix
against the repository's actual `components/**/Dockerfile` inventory. No
live cluster or registry needed - pure static check, safe to run on every
PR before any build/publish/SBOM/scan/sign step starts.

```bash
python3 platform/supply-chain/check_build_matrix.py
```

Fails if a matrix entry's `dockerfile`/`context` path is missing, its
`name` collides with another entry, or it no longer corresponds to a
tracked first-party Dockerfile (the `postgresql-pgvector` bug this ADR
fixes - Postgres is now a Crunchy PGO-managed operand, not a first-party
built image). Also fails if a first-party `components/**/Dockerfile`
exists with no matrix entry at all.

Wired into `.github/workflows/lint.yml`'s `policy-as-code` job as a hard
gate (not `continue-on-error`, unlike `check_no_latest_tags.py` above -
this check has no known-failing gap to carry).

## verify_signatures.py (ADR-0115 stage 1, WP-04)

`verify_signatures.py` runs `cosign verify` against every first-party
image reference (`quay.io/zuno-demo/...`) that already carries an
immutable tag, checking it was signed by `build-publish.yml`'s exact
keyless GitHub OIDC identity - not merely signed by *someone*.

```bash
python3 platform/supply-chain/verify_signatures.py
```

Scoped to immutable-tagged references only: a `tag: latest` entry has no
meaningful digest to verify against, so with every chart still on
`latest` (see above) this currently finds nothing to check and passes
trivially - the honest state until a real release exists, not a loosened
check. Needs `cosign` on `PATH` and registry network access once there is
something to verify. Wired into `.github/workflows/lint.yml` with
`continue-on-error: true`, same convention and reasoning as
`check_no_latest_tags.py`.

## pin_release.py (ADR-0115 stage 1, WP-04)

`pin_release.py` is the mechanical half of cutting a release
(`RELEASING.md` step 4): given a manifest listing the real immutable
tag/digest each `build-publish.yml` run produced, it rewrites exactly the
`tag` fields `check_no_latest_tags.py` currently flags - text-level edits
that preserve every existing comment in `values.yaml`, never a
`yaml.dump` round-trip. Refuses to run unless the manifest covers exactly
the current set of non-immutable fields (no more, no less); supports
`--dry-run`. See the script's own docstring for the manifest schema.
Optional digests are recorded in an append-only audit ledger,
`pinned-releases.yaml` in this directory - never embedded in
`values.yaml`, since no chart template renders a digest today.

```bash
python3 platform/supply-chain/pin_release.py --manifest <path> [--dry-run]
```

## sign_okf_bundle.py / validate_okf_bundle.py (ADR-0106, WP-05)

OKF agent bundle signing and validation (`agents/<agent>/`), the same
keyless-Cosign convention as `verify_signatures.py` above, applied to a
directory of Markdown/YAML instead of an OCI image.

`sign_okf_bundle.py` computes a canonical sha256 digest over a bundle tree
(sorted `relative_path:content_hash` pairs, independent of filesystem
iteration order) and signs/verifies it with `cosign sign-blob`/
`verify-blob`:

```bash
python3 platform/supply-chain/sign_okf_bundle.py digest agents/tekos
python3 platform/supply-chain/sign_okf_bundle.py sign agents/tekos --output-dir /tmp/sigs
python3 platform/supply-chain/sign_okf_bundle.py verify agents/tekos \
    --signature /tmp/sigs/tekos.sig --certificate /tmp/sigs/tekos.pem
```

`sign` needs a real GitHub Actions OIDC run (Sigstore Fulcio/Rekor) and
cannot succeed locally, same honest limitation as `build-publish.yml`'s
image signing; `verify` needs only the bundle plus its signature/
certificate files, no credentials. Wired into `build-publish.yml` as a
`sign-okf-bundles` job (one signature per agent, uploaded as a build
artifact - bundle signatures are never committed to git, since bundle
content changes on every commit that touches `agents/`).

`validate_okf_bundle.py` checks the other two ADR-0106 dimensions -
schema validity (OKF structure) and policy validity (every declared tool
resolves against `policies/tools/tool-policy.yaml`, feature-detecting
`policies/knowledge/knowledge-policy.yaml` once it exists) - entirely from
the checked-out repo, no signature needed:

```bash
python3 platform/supply-chain/validate_okf_bundle.py [agents/<name> ...]
```

Wired into `.github/workflows/lint.yml` as a **hard gate** (unlike the two
signature-related checks above): schema/policy validity needs nothing a
PR doesn't already have, so there is no honest reason to leave it
non-blocking. Also run by `ansible/roles/agents`' Day 1 check
(`make d1 check agents`).

The Agent Runtime (`components/agent-runtime/app/registry.py`) enforces
signature verification at startup when `ZUNO_REQUIRE_SIGNED_BUNDLES=true`
(default `false` - no bundle has a real signature yet), importing
`sign_okf_bundle.py`'s digest/verify logic directly (baked into the image
at `app/_sign_okf_bundle.py` by `components/agent-runtime/Dockerfile`,
which also installs the `cosign` binary) rather than duplicating it, so
the runtime can never disagree with CI about what a bundle's digest is.

Regression-tested (`tests/test_pin_release.py`, run against a throwaway
copy of the real chart files - never the repository's own state) because,
unlike its read-only siblings above, this script mutates chart files.
