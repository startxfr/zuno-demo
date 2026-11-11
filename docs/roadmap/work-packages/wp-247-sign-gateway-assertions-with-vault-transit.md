# WP-247: Sign the gateway assertions with Vault Transit

- **State:** Not started (design settled 2026-11-11; lot 1 steps 1-3 in the repo, Vault side applied 2026-11-11, signer not live until the image and the window)
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

Open item resolved 2026-11-11: the "workload token that signs the lot B caller context" is
`MCP_GATEWAY_WORKLOAD_TOKEN`, the Vault secret `zuno/mcp/gateway-workload-token` (random, WP-223). It is a **symmetric
secret held by the gateway and by every MCP server** (aap, git-forge, confluence, salesforce): the servers compare it in
constant time as the `X-Zuno-Gateway-Token` and derive from it, per backend, the HMAC key of `X-Zuno-Caller-Signature`
(`app/caller_context.py`). Transit cannot replace it by swapping a signer: the servers verify with the same secret, so
moving it to Vault means either a Vault call per verification on four servers or folding the caller context into the
assertion claims (the assertion is already signed per call and bound to the tool and the arguments). It is therefore **not
part of this WP**: it needs its own design (candidate: carry `groups`, `email`, `email_verified` and `username` in the
assertion, then retire both the shared token and the HMAC signature). Mitigation already in place: with
`callAssertion.required: true` on the servers, holding the workload token alone no longer opens a tool call; forging a
caller context also needs a valid assertion, that is the Transit key.

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
- **2026-11-11, lot 1 step 3 (chart), repo only, not applied.** `gitops/charts/mcp-gateway` gains
  `outboundIdentity.signer` (`file` default, `transit`) and `outboundIdentity.vault` (`addr`, `authRole`, `transitKey`).
  With `signer: transit` the Deployment sets `MCP_CALL_ASSERTION_SIGNER` and the `VAULT_*` variables (CA = the
  service-ca bundle next to the ServiceAccount token), mounts the ServiceAccount token, and renders neither the
  `mcp-gateway-call-assertion` ExternalSecret nor the key volume. `helm template` checked in the three cases: `file`
  renders as before, `transit` as described, the default (`bearer`) renders no assertion object at all. Network:
  the gateway pod has an Ingress-only policy (no egress limit) and `zuno-ai-run` is already in the `zuno-vault`
  `allowedFromNamespaces`, so no NetworkPolicy change is needed. To prove live: the Istio sidecar passing the
  gateway's own TLS to the non-meshed Vault (the first signature after the switch is the test).
- **2026-11-11 10:35Z, lot 1 step 1 applied on demo333** (`make d0 install vault`, the user's go, zuno-demo and
  unifai-main informed). The configure Job created the Transit key `mcp-call-assertion` (ed25519, version 1, not
  exportable, no plaintext backup, signing only), the policy `mcp-call-assertion-signer` and the Kubernetes auth role
  `mcp-gateway`. No gateway pod was touched and no tool call changed. Still to do: image build (after zuno-demo's
  "R-543 proof done"), then the window.
- **2026-11-11, lot 1 steps 4-6 on demo333 (user's go: build, then "option A" switch).** Build `mcp-gateway-54`
  (devel `955663d`), signed by RHTAS (`sha256:7a548d0b`); the first roll kept `signer: file` and the confluence tool call
  stayed 200. Before the window, a probe pod in `zuno-ai-run` running the gateway image with the `mcp-gateway`
  ServiceAccount (inside the mesh) proved: Vault login OK, public key readable, `transit/keys/zuno-platform-signer`
  refused (403), a signature verified with the fetched public key. Window 12:05:38Z-~12:15Z: one `make d2 install mcp`
  switched the gateway to `signer: transit` and put the Transit public key in aap, git-forge and confluence.
  Proofs: (a) `confluence.page.search` 200 in 791 ms (947 ms before), `git.repository.list` reaches git-forge; (b) a direct
  call without assertion is 401 on all three servers; (c) the Secret `mcp-gateway-call-assertion` is gone and the key path
  does not exist in the pod; 12 `transit/sign/mcp-call-assertion` events in the Vault log, 0 sign errors and 0 x 401 in the
  gateway log. Not done: (d) stopping Vault to see the 502 live (the fail-closed path is covered by the unit tests; a live
  outage of the one secret store was judged not worth the risk) and (e) the full golden path (zuno-demo runs it). The old key
  `zuno/mcp/gateway-call-assertion` stays in Vault until (e) passes.
- **2026-11-11, old key retired from every reader (user's go, option A).** Golden path 14/14 by zuno-demo after the
  switch (and again after UnifAI 0.1.68). `zuno/mcp/gateway-call-assertion` was removed from `zuno-ai-run` in
  `platform/vault/secret-access.yaml`, from the seed and export playbooks (`wp225_*`), and `make d0 install vault` rewrote
  the namespace policy. Proof: logged in to Vault with the `ns-zuno-ai-run` role (the role the store of that namespace
  uses), the read of `mcp/gateway-call-assertion` is **permission denied** while `mcp/gateway-workload-token` and
  `a2a/agent-chain` remain readable; a gateway tool call still returns 200. The Vault data itself is **not deleted yet**
  (only `ansible-seeder` and root can still read it, and nothing reads it): deleting it is a separate step with its own go.
  The chart's `file` signer and its ExternalSecret stay as the documented rollback path.

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
