# Platform: supply chain

Software supply chain policy: immutable, verifiable artifacts.

`check_no_latest_tags.py` rejects `latest` image tags in deployable
components: walks every `gitops/charts/*/values.yaml` for an image `tag`
set to the literal `latest` (or left empty). No live cluster or registry
needed - pure static YAML inspection.

```bash
python3 platform/supply-chain/check_no_latest_tags.py
```

**This currently fails, honestly, and is expected to for a while.** See
`RELEASING.md`'s own top note first: every chart whose `image.repository`
points at the in-cluster `zuno-ai-build` ImageStream (i.e. every
first-party chart deployed by `make day0|d0`/`day1|d1` today) can only
ever run its BuildConfig-produced `:latest` image - there is no other tag
to reference until `.github/workflows/build-publish.yml` has actually run
against real Quay credentials/a GitHub Actions environment (it hasn't,
in this sandbox) *and* that chart's `.repository` has separately been
repointed at `quay.io/zuno/<component>`. `pin_release.py` below only
rewrites `.tag`, never `.repository` - running it without also
repointing `.repository` produces exactly the manifest-unknown
ImagePullBackOff this repo has hit repeatedly (mcp-* charts,
agent-runtime/tekos, comage/advantage/finage/naveo - all reverted back to
`latest` each time). Run this check to see the current, honest count of
charts still on `:latest` (13 as of 2026-08-20 - it grows as new
components are added, and that's fine: it's supposed to stay red until a
real release is cut).

Wired into `.github/workflows/lint.yml` alongside other policy-as-code
checks (`platform/security/check_workload_hardening.py`,
`platform/api/lint_openapi.py`) - see that workflow.

## check_build_matrix.py

`check_build_matrix.py` validates
`.github/workflows/build-publish.yml`'s build matrix against the
repository's actual `components/**/Dockerfile` inventory. No live
cluster or registry needed - pure static check, safe to run on every PR
before any build/publish/SBOM/scan/sign step starts.

```bash
python3 platform/supply-chain/check_build_matrix.py
```

Fails if a matrix entry's `dockerfile`/`context` path is missing, its
`name` collides with another entry, or it no longer corresponds to a
tracked first-party Dockerfile (e.g. `postgresql-pgvector`, now a
Crunchy PGO-managed operand). Also fails if a first-party
`components/**/Dockerfile` exists with no matrix entry at all.

Wired into `.github/workflows/lint.yml`'s `policy-as-code` job as a hard
gate (not `continue-on-error`, unlike `check_no_latest_tags.py` above).

## verify_signatures.py (WP-04)

`verify_signatures.py` runs `cosign verify` against every first-party
image reference (`quay.io/zuno/...`) that already carries an
immutable tag, checking it was signed by `build-publish.yml`'s exact
keyless GitHub OIDC identity.

```bash
python3 platform/supply-chain/verify_signatures.py
```

Scoped to immutable-tagged references only: a `tag: latest` entry has no
meaningful digest to verify against, so with every chart still on
`latest` (see above) this finds nothing to check and passes trivially.
Needs `cosign` on `PATH` and registry network access once there is
something to verify. Wired into `.github/workflows/lint.yml` with
`continue-on-error: true`, same convention as `check_no_latest_tags.py`.

## pin_release.py (WP-04)

`pin_release.py` is the mechanical half of cutting a release
(`RELEASING.md` step 4): given a manifest listing the real immutable
tag/digest each `build-publish.yml` run produced, it rewrites exactly the
`tag` fields `check_no_latest_tags.py` currently flags, preserving every
existing comment in `values.yaml`. Refuses to run unless the manifest
covers exactly the current set of non-immutable fields (no more, no
less); supports `--dry-run`. See the script's own docstring for the
manifest schema. Optional digests are recorded in an append-only audit
ledger, `pinned-releases.yaml` in this directory - never embedded in
`values.yaml`.

```bash
python3 platform/supply-chain/pin_release.py --manifest <path> [--dry-run]
```

## sign_okf_bundle.py / validate_okf_bundle.py (WP-05, mechanism replaced by WP-069/ADR-0420)

OKF agent bundle signing and validation (`agents/<agent>/`), applied to a
directory of Markdown/YAML instead of an OCI image.

`sign_okf_bundle.py` computes a canonical sha256 digest over a bundle
tree (sorted `relative_path:content_hash` pairs) and signs/verifies it
with `cosign sign-blob`/`verify-blob`, backed by the in-cluster Vault
Transit key `sign_in_cluster.py` authenticates to (ADR-0420), not keyless
GitHub OIDC/Fulcio/Rekor:

```bash
python3 platform/supply-chain/sign_okf_bundle.py digest agents/tekos
python3 platform/supply-chain/sign_okf_bundle.py sign agents/tekos --output-dir /tmp/sigs
python3 platform/supply-chain/sign_okf_bundle.py verify agents/tekos \
    --signature /tmp/sigs/tekos.sig \
    --public-key agents/zuno-platform-signer.pub
```

`sign` needs `VAULT_ADDR`/`VAULT_TOKEN` in the environment and can only
succeed against a reachable in-cluster Vault, not in a local sandbox or
CI; `verify` needs only the bundle, its signature, and the committed
public key above - no Vault access, no network. The actual multi-bundle
signing run is orchestrated by `sign_in_cluster.py sign-okf-bundles`
(baked into the `supply-chain-signer` image), triggered by
`ansible/tasks/run_okf_signing_job.yml` as an in-cluster Job right after
the agent-runtime image builds (`ansible/roles/agent_build`, explicit
`make d2 build agent` only). It writes every `{agent}.sig` plus the
shared public key straight to Vault KV (`zuno/okf-signatures`), consumed
by `gitops/charts/agent-runtime/templates/externalsecret-okf-signatures.yaml` -
no GitHub Actions artifact, no manual "download and commit" step (the gap
ADR-0106's 2026-08-21 note originally flagged).

`validate_okf_bundle.py` checks two other dimensions - schema validity
(OKF structure) and policy validity (every declared tool resolves
against `policies/tools/tool-policy.yaml`, feature-detecting
`policies/knowledge/knowledge-policy.yaml` once it exists) - entirely
from the checked-out repo, no signature needed:

```bash
python3 platform/supply-chain/validate_okf_bundle.py [agents/<name> ...]
```

Wired into `.github/workflows/lint.yml` as a **hard gate** (unlike the two
signature-related checks above). Also run by `ansible/roles/agents`' Day
2 check (`make d2 check agents`).

The Agent Runtime (`components/agent-runtime/app/registry.py`) enforces
signature verification at startup when `ZUNO_REQUIRE_SIGNED_BUNDLES=true`
(default `false` - no bundle has a real signature yet), importing
`sign_okf_bundle.py`'s digest/verify logic directly (baked into the image
at `app/_sign_okf_bundle.py` by `components/agent-runtime/Dockerfile`,
which also installs the `cosign` binary).

Regression-tested (`tests/test_pin_release.py`, run against a throwaway
copy of the real chart files - never the repository's own state), since
this script mutates chart files unlike its read-only siblings above.
