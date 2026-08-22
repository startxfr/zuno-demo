# WP-070: Cut container image signing over to in-cluster Vault Transit

- **State:** Done - live-verified 2026-08-22 on api.demo222.startx.fr.
  **All 14 first-party images** carry a real Vault Transit signature,
  independently confirmed with `cosign verify --key` for every one -
  agent-runtime, agent-bff, agent-frontend, ai-gateway, aiagent-operator,
  mcp-gateway, mcp-confluence, mcp-git-forge, mcp-sales-db,
  mcp-salesforce, mlops, rag-ingestion, rag-service, supply-chain-signer.
  (`ai-gateway`'s first signing attempt had actually failed silently
  mid-pass - due before `supply-chain-signer` picked up the `sign-image`
  subcommand - and was caught only by an all-images sweep; re-signed and
  confirmed. A *second*, independent drift instance was later caught the
  same way, when a concurrent session rebuilt `ai-gateway` without
  triggering the signing step - re-signed and confirmed again, which is
  exactly the automated check gate below now exists to catch on its own.)
  `aiagent-operator` has no Makefile/Day1/Day2 build-component wiring at
  all (a pre-existing, orphaned-role gap, not fixed here) - signed via a
  direct ansible invocation instead.

  **Automated check gate**: `make d2 check supply-chain`
  (`ansible/roles/supply_chain`) resolves every first-party image's live
  digest locally (`verify_signatures.py --list-refs` - cluster API access
  only, no registry network needed) and hands the list to an in-cluster
  Job that runs the real `cosign verify` (`sign_in_cluster.py
  verify-images`, using the public key baked into `supply-chain-signer` at
  build time - no Vault access needed to verify). Live-verified both ways:
  a clean run reports `RESULT: PASS - all 13 image(s) verified` (13, not
  14 - `supply-chain-signer` itself has no gitops chart reference, so it's
  outside this particular scan's scope by design), and a deliberately
  tampered digest correctly fails the gate with a named image. Folded into
  `make d2 check all` with no regressions to the other 8 components.

  **`build-publish.yml` decision: keep it** - already fully stripped of
  every signing step, still valuable for SBOM/scan/optional-Quay,
  `RELEASING.md` already frames it as deliberately dormant, and
  `check_build_matrix.py` still hard-depends on its exact job names.
  Fixed three stale doc references that still described the removed
  keyless-GitHub-OIDC mechanism as live (`.github/README.md`,
  `RELEASING.md` step 5, `docs/security/secnumcloud-controls.md`).

  Two real bugs found building the check gate's digest-resolution logic:
  the first-party filter also matched *mirrored* third-party images
  (`vault`, `bitnami-kubectl` - pulled via `image_mirrors`, never signed
  by this pipeline) sharing the same internal registry namespace, fixed by
  requiring a matching BuildConfig to exist; and `agent-bff`/
  `agent-frontend` were entirely invisible to the scan (every per-agent
  chart declares them via a `registry`+`frontendRepository`/
  `bffRepository`+`tag` shape the scanner never recognized), fixed by
  extending the shape-matching walk and deduplicating the resulting
  6x-repeated refs. A third bug (`cosign verify`, unlike `sign`, always
  initializes a TUF trust-root cache under `$HOME/.sigstore` even in pure
  `--key` mode) was fixed by defaulting `HOME` to a writable dir. See
  ADR-0420's implementation notes for the full account, including a
  recurring ansible Job-log-display bug (an arbitrary, sometimes-stale pod
  shown across `backoffLimit` retries) fixed across all three signing/
  verify Jobs at once.

  Remaining, deliberately out of scope: `aiagent-operator`'s missing
  Makefile/build-component wiring (pre-existing).
- **ADRs:** ADR-0115 (Deferred -> superseded-in-part by ADR-0420 for the
  signing mechanism), ADR-0420
- **Depends on:** WP-068 (Vault Transit signing backend)
- **Blocks:** —
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Sign every first-party image actually deployed - the internal
`image-registry.openshift-image-registry.svc:5000/zuno-ai-build/*` `ImageStreamTag`s,
not `quay.io` - by digest, using WP-068's Vault Transit backend, and make
`platform/supply-chain/verify_signatures.py` a real, non-trivially-passing
gate instead of one that finds nothing to verify.

## Preconditions (verify before starting)

- WP-068 and WP-069 merged and live-verified.
- Read: `platform/supply-chain/verify_signatures.py`,
  `.github/workflows/build-publish.yml`'s image-signing job,
  `platform/supply-chain/check_build_matrix.py` (parses `build-publish.yml`
  as the build-matrix source of truth - must be redirected, not just left
  dangling, before that workflow is cut down),
  `.github/workflows/lint.yml`'s `verify_signatures.py` step.

## Repo changes (step by step)

1. **`verify_signatures.py`**: `FIRST_PARTY_REGISTRY_PREFIX` ->
   `image-registry.openshift-image-registry.svc:5000/zuno-ai-build/`;
   delete `EXPECTED_OIDC_ISSUER`/`EXPECTED_IDENTITY_REGEXP`; `_verify_one()`
   resolves each component's live `ImageStreamTag` digest (`oc get istag`)
   and verifies with `--key <pubkey> --insecure-ignore-tlog=true` instead of
   `--certificate-oidc-issuer`/`--certificate-identity-regexp`. This can no
   longer run from a GitHub-hosted runner (no route to the internal
   registry) - move its invocation out of `.github/workflows/lint.yml` into
   an in-cluster `make d1 check` gate instead.
2. **Signing**: extend the WP-069 signing Job (or add a sibling) to resolve
   each component's `ImageStreamTag` digest after its BuildConfig build
   completes and `cosign sign --key hashivault://zuno-platform-signer
   --tlog-upload=false <image>@sha256:<digest>` it, with
   `COSIGN_REPOSITORY` pointed at a dedicated `zuno-ai-build/signatures`
   ImageStream so signature tags don't clutter each component's own stream.
3. **`build-publish.yml`**: decide and execute one of - (a) keep it as a
   build/SBOM-only workflow with its `cosign sign`/`attest`/`sign-okf-bundles`
   jobs removed, or (b) retire the file entirely. Either way,
   `check_build_matrix.py:43`'s `WORKFLOW_PATH` needs a new source of truth
   first (e.g. the Day 1/Day 2 Makefile `*_BUILD_COMPONENTS` lists this
   ADR's own roles already populate) - this is a decision to make
   deliberately in this WP, not a side effect to discover after deleting the
   file.
4. **Trust anchor reuse**: no new public key - the same
   `platform/supply-chain/keys/zuno-platform-signer.pub` WP-068 committed
   covers images too (see ADR-0420's "one key, not two" note; split later
   only if a real rotation need appears).

## What NOT to touch

- OKF bundle signing internals - WP-069's concern, already landed by the
  time this WP starts.
- `gitops/charts/*/values.yaml` image tags/`targetRevision` pinning (ADR-0115
  gap 2, a separate, still-open concern this WP does not need to solve to
  close gap 6).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile platform/supply-chain/verify_signatures.py`
- `python3 platform/supply-chain/check_build_matrix.py` (or its
  post-redirect equivalent) exits 0
- `python3 platform/docs/check_docs.py` -> `RESULT: PASS`

## Live verification (in-cluster)

1. Sign a real component's current `ImageStreamTag` digest.
2. `python3 platform/supply-chain/verify_signatures.py` in-cluster returns a
   non-trivial `PASS` (i.e. it actually found and verified a signed
   reference - not the "nothing to verify" state that made stage 1
   trivially pass before).
3. From a pod with a NetworkPolicy denying all egress: the same verify
   command still succeeds (proves it needs no Vault access, no internet).

## Status updates (then re-run check_docs.py)

- After merge + live verification: ADR-0115's own status note updates to
  reflect gap 6 (signature verification as a deployment gate) closed via
  ADR-0420, in-cluster, instead of the Quay/GitHub-OIDC path it originally
  named.

## Out of scope / deferred

- `gitops/charts/*/values.yaml` immutable tag/digest pinning (ADR-0115 gap
  2) and any future "source runtime images from Quay" mode (ADR-0115
  explicitly defers that to ADR-0353) - neither is required for this WP.
