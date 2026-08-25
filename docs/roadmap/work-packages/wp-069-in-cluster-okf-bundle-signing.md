# WP-069: Cut OKF bundle signing over to in-cluster Vault Transit

- **State:** Done. Live-verified 2026-08-22 on api.demo222.startx.fr: all 8
  agent bundles signed by the in-cluster Job, written to Vault KV, synced
  by the ExternalSecret into a real Secret, and independently re-verified
  using the actual deployed `app/_sign_okf_bundle.py`/`app/registry.py`
  code path with `ZUNO_REQUIRE_SIGNED_BUNDLES=true` in a debug pod -
  `AgentRegistry` loaded all 8 agents with zero load errors, and a
  tampered copy was correctly rejected. `requireSignedBundles: true` was
  then flipped on the real chart the same day and has been live since.
  Re-verified again 2026-08-25 (both live and offline, all 8 agents) -
  found and fixed a stale committed trust-anchor file
  (`platform/supply-chain/keys/zuno-platform-signer.pub`) that had
  drifted from the live Vault Transit key after an apparent key
  regeneration on 2026-08-24; this had been silently breaking the
  offline `make d2 check agents` path while live production stayed
  healthy throughout (see ADR-0106's 2026-08-25 note for the full
  diagnosis).
- **ADRs:** ADR-0106 (Implemented), ADR-0420
- **Depends on:** WP-068 (Vault Transit signing backend)
- **Blocks:** —
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.

## Goal

Replace ADR-0106's GitHub-OIDC/Fulcio/Rekor keyless signing of OKF agent
bundles (`agents/<agent>/`) with WP-068's Vault Transit backend, and
automate signature distribution so the manual "download a GitHub Actions
artifact, commit it into gitops" hop goes away entirely. Keep
`ZUNO_REQUIRE_SIGNED_BUNDLES=false` until all 8 agent bundles have a live,
verifying signature - flipping it early fail-closed crash-loops every
agent-runtime pod, exactly as ADR-0106's 2026-08-21 note already warned.

## Preconditions (verify before starting)

- WP-068 merged and live-verified: `platform/supply-chain/keys/zuno-platform-signer.pub`
  exists and is committed; a debug pod can run
  `sign_in_cluster.py dry-run` successfully.
- Read: `platform/supply-chain/sign_okf_bundle.py`,
  `components/agent-runtime/app/registry.py`'s `_verify_signature()`,
  `gitops/charts/agent-runtime/templates/configmap-signatures.yaml`,
  `gitops/charts/agent-runtime/files/okf-signatures/README.md`,
  `gitops/charts/external-secrets/templates/clustersecretstore.yaml` (the
  `vault-backend` ClusterSecretStore this reuses).

## Repo changes (step by step)

1. **`sign_okf_bundle.py`**: keep `compute_digest()`/`_bundle_files()`
   untouched (registry/backend-agnostic, correctly reused already). Delete
   `EXPECTED_OIDC_ISSUER`/`EXPECTED_IDENTITY_REGEXP`. `sign_bundle()` takes
   a `--kms-key` (default `hashivault://zuno-platform-signer`), emits only
   `{name}.sig` (no more `.pem` - Transit produces no certificate).
   `verify_bundle()` swaps `--certificate-oidc-issuer`/`--certificate-identity-regexp`
   for `--key <pubkey>` + `--insecure-ignore-tlog=true`.
2. **Signing Job**: a new Ansible-triggered `Job` (copy the
   `vault-unseal-configure` delete-then-recreate shape), using the
   `supply-chain-signer` image and the `zuno-signer` ServiceAccount, runs
   after the agent-runtime build. Use an initContainer to copy `agents/`
   out of the just-built `agent-runtime:latest` image before signing, so
   the signed bytes are, by construction, exactly what the runtime loads
   (a separate BuildConfig checkout of a moving `main` ref could otherwise
   drift by one commit).
3. **Distribution**: the Job writes `zuno/okf-signatures` in Vault KV
   (one field per agent, unconditional `kv put` on every run - not the
   idempotent seed-if-missing pattern, since a signature must update when
   bundle content changes). New
   `gitops/charts/agent-runtime/templates/externalsecret-okf-signatures.yaml`
   materializes one Secret (`<agent>.sig` per agent, plus `cosign.pub`)
   mounted read-only at `/app/okf-signatures`, replacing
   `configmap-signatures.yaml` and the committed `files/okf-signatures/*.{sig,pem}`
   files.
4. **Runtime**: `components/agent-runtime/app/registry.py`'s
   `_verify_signature()` - `{name}.pem` lookup becomes a single shared
   `cosign.pub`; error text updated to match.
5. **Chart**: `gitops/charts/agent-runtime/values.yaml`/`templates/deployment.yaml` -
   signature volume moves from `configMap:` to `secret:`; delete
   `okfSignedAgents`'s `.Files.Get` machinery, `templates/configmap-signatures.yaml`,
   `files/okf-signatures/`.
6. **Day 1 check**: `ansible/roles/agents/tasks/check.yml` - replace the
   "signature verification not run here" comment with a real in-cluster
   verify invocation.
7. **Tests**: `platform/supply-chain/tests/test_sign_okf_bundle.py` (digest
   tests should survive unchanged), `components/agent-runtime/tests/test_bundle_signing.py`
   (fixtures move from `.pem` to `cosign.pub`).

## What NOT to touch

- Image signing / `verify_signatures.py` / `build-publish.yml`'s image job -
  WP-070.
- `ZUNO_REQUIRE_SIGNED_BUNDLES` itself - flip only as the last live step,
  once all 8 agents verify (see Operator follow-up).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest platform/supply-chain/tests/ components/agent-runtime/tests/ -q`
- `ansible-playbook ansible/roles/agents/tasks/check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` -> `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

Done 2026-08-22 (flip), re-verified 2026-08-25 (all 8 agents live and
offline, trust-anchor drift found and fixed - see ADR-0106).

1. ~~Run the signing Job for real; confirm all 8 agents
   (tekos, comage, advantage, finage, arkos, naveo, soursage, cognos) have a
   live, verifying `.sig` in the mounted Secret.~~
2. ~~Flip `ZUNO_REQUIRE_SIGNED_BUNDLES` on a scaled-to-1 debug Deployment
   first, confirm every agent still loads, only then flip the real chart
   value.~~

## Out of scope / deferred

- Image signing cutover (WP-070).
