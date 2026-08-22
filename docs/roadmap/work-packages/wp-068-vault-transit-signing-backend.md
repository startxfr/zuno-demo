# WP-068: Vault Transit signing backend (implements ADR-0420)

- **State:** Done — live-verified on api.demo222.startx.fr 2026-08-22: Vault
  Kubernetes-auth login, sign+verify+tamper-rejection round trip, negative
  auth (default SA correctly refused), non-exportability
  (`transit/export/signing-key/...` correctly refused), offline verify (a
  second pod with `VAULT_ADDR` unset and all egress denied still verifies),
  and the audit trail (each `transit/sign` call attributed to
  `kubernetes-zuno-ai-build-zuno-signer`) all confirmed. Two real bugs found
  and fixed along the way: (1) `zuno-vault`'s NetworkPolicy allowlist didn't
  include `zuno-ai-build`, so the signer couldn't reach Vault at all;
  (2) the `platform-signer` policy only granted the bare
  `transit/sign/zuno-platform-signer` path, but cosign's hashivault client
  calls `transit/sign/<key>/sha2-256` - Vault policy paths are exact-match,
  so every sign-blob call 403'd until a `/*` glob was added. A third,
  cosmetic bug (`enable_if_new`'s "already enabled" guard didn't recognize
  the audit device's differently-worded error) was also fixed.
- **ADRs:** ADR-0420 (Proposed -> Partially implemented)
- **Depends on:** —
- **Blocks:** WP-069 (OKF bundle signing cutover), WP-070 (image signing cutover)
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Stand up a fully in-cluster signing backend - a Vault Transit key, a
Kubernetes-auth role bound to a dedicated ServiceAccount, and a minimal
signer image - with **zero consumers cut over yet**. OKF bundle signing and
image signing keep working exactly as before (still unenforced,
`ZUNO_REQUIRE_SIGNED_BUNDLES=false`) until WP-069/WP-070. Done when a debug
pod can authenticate to Vault as the new signer identity, sign an arbitrary
blob via Transit, and verify it completely offline (no Vault, no network).

## ADR references

ADR-0420's Decision section: the Vault Transit key, the `zuno-signer`
ServiceAccount/`platform-signer` role pattern, and the two load-bearing
cosign flags (`--tlog-upload=false`, `--insecure-ignore-tlog=true`).

Related: ADR-0024 (Vault for app secrets), ADR-0032 (Keycloak not used for
workload identity - precedent this ADR follows), ADR-0106/ADR-0115 (what
this backend eventually replaces, in WP-069/070).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `ansible/roles/vault/kustomize/unseal-configure/configmap.yaml` (the
  existing KV v2/PKI/Kubernetes-auth setup and its `enable_if_new` idiom),
  `ansible/roles/ai_gateway_build/` (the build-only role shape to copy),
  `ansible/tasks/apply_openshift_build.yml`, `components/agent-runtime/Dockerfile`
  (the existing cosign-fetch block to mirror).

## Repo changes (step by step)

1. **Vault configuration**:
   `ansible/roles/vault/kustomize/unseal-configure/configmap.yaml` - append,
   after the existing `istio-issuer` block: enable the Transit secrets
   engine (`enable_if_new`-guarded, matching the file's own idiom), create
   `zuno-platform-signer` (`type=ecdsa-p256`) idempotently, lock it down
   (`exportable=false`, `allow_plaintext_backup=false`), write the
   `platform-signer` policy (`update` on `transit/sign/zuno-platform-signer`,
   `read` on `transit/keys/zuno-platform-signer`), write
   `auth/kubernetes/role/platform-signer` bound to
   `bound_service_account_names=zuno-signer`,
   `bound_service_account_namespaces=zuno-ai-build`, `ttl=1h`. Enable a file
   audit device (`vault audit enable file file_path=stdout`) as the
   in-cluster substitute for the Rekor transparency log this replaces.
2. **ServiceAccount + build role**: new
   `ansible/roles/supply_chain_signer_build/tasks/build.yml` - create the
   `zuno-signer` ServiceAccount in `zuno-ai-build`, then build
   `supply-chain-signer` via `ansible/tasks/apply_openshift_build.yml`
   (same call shape as `ai_gateway_build`).
3. **Signer script**: new `platform/supply-chain/sign_in_cluster.py` -
   Vault Kubernetes-auth login (stdlib `urllib`, no extra dependency),
   `login`/`public-key`/`sign-blob`/`verify-blob`/`dry-run` subcommands. The
   `dry-run` subcommand is this WP's acceptance check: sign+verify a
   scratch blob, then confirm a tampered copy is rejected.
4. **Signer image**: new `components/supply-chain-signer/Dockerfile` -
   `python:3.11-slim` mirror base (matching every other Python component
   here), same cosign-fetch block as `components/agent-runtime/Dockerfile`
   (bump both together if the pinned version ever changes), `COPY`s in
   `sign_in_cluster.py` only. `ENTRYPOINT`/default `CMD` runs `dry-run`.
5. **Wiring**: `Makefile`'s `DAY1_BUILD_COMPONENTS` gains
   `supply-chain-signer`; `ansible/playbooks/day1_build.yml`'s
   `day1_build_components` gains `supply_chain_signer_build`.

## What NOT to touch

- `platform/supply-chain/sign_okf_bundle.py`, `verify_signatures.py`,
  `components/agent-runtime/app/registry.py`,
  `gitops/charts/agent-runtime/*`, `.github/workflows/build-publish.yml` -
  all WP-069/WP-070. This WP adds a backend with no consumers yet.
- `ZUNO_REQUIRE_SIGNED_BUNDLES` - stays `false`, untouched.

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile platform/supply-chain/sign_in_cluster.py`
- `ansible-playbook ansible/playbooks/day1_build.yml --syntax-check`
- `python3 platform/docs/check_docs.py` -> `RESULT: PASS`

## Live verification (in an isolated debug pod, `zuno-ai-build`, using the `zuno-signer` ServiceAccount)

1. `make d0 install vault` (re-run; idempotent) to apply the Transit
   engine/key/policy/role.
2. `make d1 build supply-chain-signer` to build the signer image (push to
   `origin/main` first - the BuildConfig clones from there, not the local
   tree).
3. Run `sign_in_cluster.py dry-run` in a pod using the `zuno-signer`
   ServiceAccount in `zuno-ai-build` -> expect `RESULT: PASS`, including the
   tamper-rejection line.
4. Negative check: the identical login attempt from a pod using the
   *default* ServiceAccount in the same namespace must fail (403) - proves
   the role binding is actually scoped, not merely present.
5. Non-exportability check: `vault read transit/export/signing-key/zuno-platform-signer`
   must fail (the key has no export capability configured).
6. Audit trail: `oc logs -n zuno-vault <vault-pod> | grep transit/sign`
   shows the signing call attributed to `zuno-signer`.
7. Commit `platform/supply-chain/keys/zuno-platform-signer.pub` (exported
   from the live key) as the trust anchor future verifiers will use.

## Status updates (then re-run check_docs.py)

- After repo merge + live verification: ADR-0420 status stays "Partially
  implemented" (the backend is live; nothing consumes it yet - that's
  WP-069/070); this file's State -> `Done`.

## Out of scope / deferred

- OKF bundle signing cutover (WP-069).
- Image signing cutover (WP-070).
- Splitting into per-artifact-kind signing keys (only if a real rotation
  need ever appears - see ADR-0420's Accepted risks).
