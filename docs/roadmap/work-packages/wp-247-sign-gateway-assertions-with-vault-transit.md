# WP-247: Sign the gateway assertions with Vault Transit

- **State:** Not started (design settled 2026-11-11; lot 1 steps 1 and 2 coded in the repo (signer tested locally), not deployed: nothing runs until the chart, the image and the window exist)
- **ADRs:** [ADR-0602](../../adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md),
  [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md)
- **Depends on:** [WP-223](wp-223-secrets-and-identity-hardening-vault-eso-passwords-keycloak.md) (Vault on KMS auto-unseal, raft,
  TLS, per-namespace secret stores), [WP-225](wp-225-ai-and-agent-surface-guardrails-metering-delegated-scope.md) lot C
  (the assertion and the agent chain this WP re-signs)
- **Related:** [ADR-0420](../../adr/0420-sign-supply-chain-artifacts-in-cluster-with-vault-transit.md) (the Transit
  pattern WP-068 set up for image signing), the [post-demo hardening list](../post-demo-hardening.md) item 1
- **Target:** v0.16
- **Estimated files touched:** ~14: `components/mcp-gateway/app/call_assertion.py`, `components/*/app/signed_chain.py`
  (three copies), a shared Transit client and its tests, the `vault` role (Transit mount, keys, policies, Kubernetes
  auth roles), the `mcp-gateway` and `a2a-gateway` charts, `ansible/clusters/demo333.yml`, the post-demo list, the
  operations runbook

> Execute this brief as a standalone task from the repository root. Every cluster action needs the user's go. Prove
> each lot with the golden path before the next one.

## Why

Two Ed25519 private keys sign what the platform trusts at its inner boundary:

| Key | Vault path | Signed by | Verified by |
|---|---|---|---|
| Per-call assertion | `zuno/mcp/gateway-call-assertion` | mcp-gateway (`call_assertion.py`, `MCP_CALL_ASSERTION_KEY_FILE`) | aap-mcp, git-forge-mcp, confluence-mcp (all `callAssertion.required: true` since 2026-11-09/11) and the optional salesforce-mcp |
| Agent chain | `zuno/a2a/agent-chain` | a2a-gateway (`signed_chain.py`, `AGENT_CHAIN_SIGNING_KEY_FILE`) | mcp-gateway and ai-gateway (`agentChain.verify: true`) |

Both are synced into the `zuno-ai-run` namespace as Kubernetes Secrets by an ExternalSecret that reads the namespace
`SecretStore`. Members of `ocp-ai-dev` and `ocp-ai-ops` may create ExternalSecrets in `zuno-ai-run`, so they can ask the
same store for the same Vault paths and read the private keys. With a key they can mint an assertion (call any MCP
server as the gateway) or an agent chain (claim a delegation that never happened). The `callAssertion.required` switch
made the assertion the only way into the MCP servers, so the key now matters more than before.

With Vault Transit the key never leaves Vault: the gateway asks Vault to sign the bytes and gets a signature back. The
Vault role that may call `transit/sign` is bound to the gateway ServiceAccounts only, so an ExternalSecret can no
longer reach the key.

## Goal

1. The mcp-gateway signs every assertion with a Transit key, and no pod and no Secret holds the private half.
2. The a2a-gateway signs every agent chain with a Transit key, same property.
3. As a member of `ocp-ai-dev`, creating an ExternalSecret that names the old key paths is refused or yields nothing
   useful, and the golden path still passes.

## Decisions taken with the user (2026-11-11)

| Point | Decision | Not adopted (why) |
|---|---|---|
| Approach | Vault Transit (ADR-0602 option A) | Moving the Secrets plus an admission rule (option B): cheaper, but the key stays a Secret |
| Vault unreachable at signing time | **Fail closed**: no signature, the call is refused with the existing 502 ("the gateway cannot sign the call assertion", the same path as an unreadable key), never a silent fallback | Fallback to the local key (defeats the purpose); a signature cache (weakens the binding to the call's `args_hash`) |
| Public-key switch | **All at once in a short window**: gateway and verifiers change together, tool calls fail for a few minutes during the roll, golden path mandatory | A dual-key transition (zero downtime, but a verification code change in four components) |
| Scope | **Two lots**: lot 1 the MCP call assertion, lot 2 the agent chain | Both keys in one lot (longer window, wider risk) |
| Final proof | An existing test persona of `ocp-ai-dev`, with the user's go, used only to try the ExternalSecret and observe the refusal, then cleaned up | `oc --as` impersonation (less realistic); the user running it |

Open item to confirm before lot 2: the post-demo list also names "the workload token that signs the lot B caller
context". Find which mechanism that is (a shared secret, not an Ed25519 key) and decide whether it belongs here or in
its own WP. Nothing in this brief covers it yet.

## What is already done (2026-11-11)

Not part of this WP's code, but the same hardening wave and the facts this design relies on:

- `callAssertion.required: true` is live on aap-mcp (2026-11-09), git-forge-mcp and confluence-mcp (2026-11-11), each
  proven with a direct call without assertion (401, "a gateway call assertion is required") and a call through the
  gateway (200). A signing outage will therefore stop every tool call: the fail-closed decision is deliberate.
- `jwtAllowedClients` is live on ai-gateway (`39fac032a`) and mcp-gateway (`2225a1031`) with the 10 Keycloak clients
  that carry the `zuno-admin-api` audience; the golden path passed 14/14 after the ai-gateway step.
- Vault runs on KMS auto-unseal (WP-223), so the "Vault re-seals on every restart" trap recorded in older notes does
  not apply to the fail-closed risk any more. A Vault outage is still possible (pod restart, raft leader change, node
  loss) and fails the signing.
- The signing code paths are small and isolated: `call_assertion.mint()` takes an optional `key`, and
  `signed_chain.sign()` takes a `private_key` argument, so a Transit signer plugs in at those two seams.

## Progress log

- **2026-11-11, lot 1 step 2 (signer), code and tests.** `call_assertion.py` gains `MCP_CALL_ASSERTION_SIGNER`
  (`file` default, `transit`): in `transit` mode `mint()` builds the compact JWS with the same header PyJWT writes and
  asks Vault for the ed25519 signature (`auth/kubernetes/login` with the pod's ServiceAccount token, then
  `transit/sign/<key>`; standard library only, 2 s timeout, token cached until 30 s before its lease ends and replaced
  once on a 403). Environment: `VAULT_ADDR`, `VAULT_AUTH_ROLE`, `VAULT_TRANSIT_KEY`, optional `VAULT_TRANSIT_MOUNT`,
  `VAULT_AUTH_MOUNT`, `VAULT_CACERT`, `VAULT_SA_TOKEN_FILE`. Any Vault failure, a refused login, a missing setting, or an
  answer that is not a 64-byte ed25519 signature raises `AssertionUnavailable` (no fallback to a local key or to the
  bearer). `downstream.py` now runs the two signing calls in a thread so a slow Vault cannot stall the event loop.
  Tests: `components/mcp-gateway/tests/test_wp247_transit_signer.py` (15, against a fake Vault holding a real Ed25519
  key) pass; `test_wp225_lot_c`, `test_downstream_streamable_http`, `test_mcp_frontdoor`, `test_auth` and
  `test_agent_chain` still pass. The default is unchanged, so the code is dormant until the chart switch.
- **2026-11-11, lot 1 step 1 (Vault side), repo only, not applied.** `ansible/roles/vault/kustomize/configure/configure.sh`
  now creates, create-if-missing, the non-exportable `ed25519` Transit key `mcp-call-assertion`, the policy
  `mcp-call-assertion-signer` (`update` on `transit/sign/mcp-call-assertion`, `read` on `transit/keys/mcp-call-assertion`,
  nothing else) and the Kubernetes auth role `mcp-gateway` (ServiceAccount `mcp-gateway`, namespace `zuno-ai-run`, 15 min
  token). The configurator policy already allows `transit/keys/*`, so it needs no change. Nothing runs until the configure
  Job is re-run (`make d0 install vault`, needs the user's go). Finding for step 3: the gateway Deployment sets
  `automountServiceAccountToken` from `lightspeed.enabled`, so the chart must mount the token when `signer: transit`.

## Steps

### Lot 1: the MCP call assertion

1. **Vault side (the `vault` role).** Enable the `transit` mount if absent; create `mcp-call-assertion` as a
   non-exportable `ed25519` key; write a policy that allows only `update` on `transit/sign/mcp-call-assertion` (and
   read of the public key); create a Kubernetes auth role bound to the `mcp-gateway` ServiceAccount in `zuno-ai-run`
   only. Idempotent, create-if-missing like the other seeded paths (ADR-0345).
2. **Signer.** A small client (shared helper, or one function in `call_assertion.py`) that signs the JWS signing
   input through `POST /v1/transit/sign/mcp-call-assertion` (`marshaling_algorithm=jws` is not available for
   ed25519: sign the raw `header.payload` bytes and base64url the result), authenticating with the pod's
   ServiceAccount token over Vault's TLS (use the CA the other roles already mount). Tests against a fake Vault: valid
   signature verifies with the exported public key, Vault down gives `AssertionUnavailable` (502 on the call, no fallback),
   response with a bad status or a malformed signature is refused, the token is renewed before expiry. Behind a
   switch (`outboundIdentity.signer: file|transit`, default `file`) so the image can ship before the cluster flips.
3. **Chart.** `mcp-gateway`: env for the Vault address, role and key; no `mcp-gateway-call-assertion` ExternalSecret
   and no volume mount when `signer: transit`. NetworkPolicy and mesh: allow the gateway to reach Vault on its TLS
   port (the WP-224 mesh and egress rules must admit it).
4. **Build and image.** `make d2 build mcp-gateway` (signed first-party image), `make d3 sign` where the release flow
   needs it. Ask the other sessions before any build that rolls the gateways.
5. **Window (user's go, announced to zuno-demo and unifai-main).** Read the new public key from Vault, put it in the
   three servers' `callAssertion.publicKey` (`gitops/apps/mcp-aap`, `mcp-git-forge`, `mcp-confluence`) and switch the
   gateway to `signer: transit` in the same window: `make d2 install mcp`. Expect a few minutes of failing tool
   calls while the pods roll.
6. **Proof.** (a) A tool call through the gateway returns 200 (`git.repository.list`, `confluence.page.search`;
   scripts used on 2026-11-11 live in `evaluations/golden_path_probe.py`). (b) A direct call without assertion is 401.
   (c) The gateway pod no longer mounts the key: `oc -n zuno-ai-run exec deploy/mcp-gateway -- ls` of the old path
   fails and the Secret `mcp-gateway-call-assertion` is gone. (d) Stop Vault's active pod (or deny the role) and
   confirm the gateway answers 502 "cannot sign the call assertion", not a stale success; restore and confirm recovery.
   (e) The golden path passes (`tools` moment included).
7. **Retire the old key.** Delete `zuno/mcp/gateway-call-assertion` private half from Vault (keep a note of the date),
   remove the ExternalSecret template and the value from `ansible/clusters/demo333.yml`.

### Lot 2: the agent chain

Same shape for `zuno/a2a/agent-chain`: Transit key `agent-chain`, role bound to the `a2a-gateway` ServiceAccount, the
signer behind the same switch in `signed_chain.sign()` (the three copies of `signed_chain.py` stay identical; only the
a2a-gateway signs), and the new public key in `agentChain.publicKey` of the mcp-gateway and the ai-gateway
(`gitops/apps/mcp`, ai-gateway values in `ansible/roles/llm/tasks/install.yml`). Same proofs, with a delegating agent
turn (the golden path `delegation` moment) as the functional check.

### Final proof (both lots)

With the user's go, as a test persona of `ocp-ai-dev`: try to create an ExternalSecret in `zuno-ai-run` naming
`mcp/gateway-call-assertion` and `a2a/agent-chain` (the paths no longer hold a private key) and, in a second attempt,
a `transit/sign` read through the store (the store's role does not allow it). Record that nothing readable comes back.
Delete anything the attempt created.

## Rollback

Per lot: set `outboundIdentity.signer: file` (or the a2a equivalent) and restore the previous public keys in the
servers, then `make d2 install mcp`. That is why the old key is retired only at the end of each lot, after the proofs.

## Risks

- A Vault outage stops all tool calls (and, after lot 2, all delegations). Mitigation: Vault on raft with KMS
  auto-unseal, the 502 names the cause in the log, and the runbook names the recovery.
- One Vault call per tool call (a few milliseconds on the in-cluster TLS path). Measure `duration_ms` before and
  after on the same tool; refuse the lot if the median grows by more than a small, stated margin.
- The window is a real outage of tool calls for a few minutes: announce it, run it with the golden path ready.
- A new image is needed (the gateways' code changes): coordinate builds with the sessions that own the roll windows.

## Acceptance

- Lot 1: proofs 6(a) to 6(e) pass; the old Secret and Vault private half are gone; `check_docs.py` passes.
- Lot 2: the same for the agent chain.
- Final proof recorded; the post-demo list item 1 is marked done with the date.
