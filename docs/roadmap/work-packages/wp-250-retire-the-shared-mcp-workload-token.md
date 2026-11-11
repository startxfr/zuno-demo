# WP-250: Retire the shared MCP workload token

- **State:** Repo work in review (lot 1 code and tests written, not built or applied)
- **ADRs:** [ADR-0602](../../adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md),
  [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md)
- **Depends on:** [WP-247](wp-247-sign-gateway-assertions-with-vault-transit.md) (the assertion is signed by Vault Transit),
  [WP-225](wp-225-ai-and-agent-surface-guardrails-metering-delegated-scope.md) lots B and C (the caller context and the assertion)
- **Related:** the [post-demo hardening list](../post-demo-hardening.md) item 1, ADR-0037 (the gateway token), ADR-0119 (each server image is built from its own directory)
- **Target:** v0.16
- **Estimated files touched:** ~16: `components/mcp-gateway/app/{call_assertion,caller_context,downstream,bindings}.py`,
  the verifying half in `components/mcp-servers/{aap,git-forge,confluence,salesforce}/server.py`, `diagram-render`,
  the five charts that mount `mcp-gateway-workload-token`, `platform/vault/secret-access.yaml`,
  `platform/bindings/tools/tool-bindings.yaml`, the tests, the evaluation security checks, this brief, the tracker

> Execute this brief as a standalone task from the repository root. Every cluster action needs the user's go, outside a
> freeze, with a golden-path run after each lot. Opened 2026-11-11 (user's go), as the follow-up WP-247 left open.

## Why

`MCP_GATEWAY_WORKLOAD_TOKEN` (Vault `zuno/mcp/gateway-workload-token`, random) is a **symmetric secret held by the
mcp-gateway and by every MCP server** (aap, git-forge, confluence, salesforce, and diagram-render). It does two jobs:

1. The servers compare it in constant time as `X-Zuno-Gateway-Token` ("the caller is the gateway", ADR-0037).
2. They derive from it, per backend, the HMAC key of `X-Zuno-Caller-Signature`, which authenticates the caller context
   (`groups`, `email`, `username`, `tool`) the shared-credential servers scope their one technical identity to
   (`components/mcp-gateway/app/caller_context.py`).

`zuno-ai-run` lists it in `platform/vault/secret-access.yaml`, so the same ExternalSecret path that exposed the two
signing keys before WP-247 still exposes this one to the members of `ocp-ai-dev` and `ocp-ai-ops`. Today `callAssertion.required: true` on
aap, git-forge and confluence means the token alone no longer opens a tool call, and forging a caller context needs a
valid assertion too. That is a mitigation, not a fix: salesforce-mcp (optional assertion) and diagram-render still
trust the token alone, and the caller context of the other three is only as strong as the weakest secret holder.

Transit cannot replace a symmetric secret by swapping a signer: four servers verify with the same value. Holding it in
Vault would mean a Vault call per verification on every server.

## Options

| Option | What changes | Cost | Verdict |
|---|---|---|---|
| **A. Fold the caller context into the assertion (recommended)** | The Transit-signed assertion already carries `sub`, `tool`, `args`. Add `groups`, `email`, `email_verified`, `username`. The servers read the caller from the verified claims; retire `X-Zuno-Gateway-Token` and `X-Zuno-Caller-Signature` and the secret | One signature per call (already paid), no new Vault round trip, one trust anchor; the assertion becomes mandatory on salesforce-mcp and diagram-render | Recommended |
| B. Sign the caller context with Transit too | A second Transit key and a second signature per call | Doubles Vault latency per tool call; two things to keep in step | No |
| C. Keep the token, move it out of reach | Sync it only into a namespace the groups cannot create ExternalSecrets in, project it into the pods | Smallest change; the secret stays shared and symmetric, every holder can forge a caller context | Fallback only |

## Goal (option A)

- The assertion carries the caller context, signed by Vault Transit; every MCP server, including salesforce-mcp and
  diagram-render, requires and verifies it and takes the caller from its claims.
- `X-Zuno-Gateway-Token`, `X-Zuno-Caller-Context`, `X-Zuno-Caller-Signature` and `MCP_GATEWAY_WORKLOAD_TOKEN` are gone
  from the gateway, the servers and the charts; `mcp/gateway-workload-token` leaves `secret-access.yaml`.
- The claims are read from the validated identity only, never from a request argument or header (as today).

## Lots (each with the user's go and a golden path)

| Lot | Content | Live effect |
|---|---|---|
| 1 | Gateway and servers accept BOTH: the assertion carries the context; servers prefer it, fall back to the headers. Salesforce and diagram-render verify the assertion when present. Unit tests on the claims, the audience, the tool binding and an assertion without groups | roll of mcp-gateway and the servers |
| 2 | Servers require the claims (no fallback); the gateway stops sending the two headers and the token. Bindings `gateway_token: false` and `caller_context` removed or folded | roll, golden path |
| 3 | Remove `MCP_GATEWAY_WORKLOAD_TOKEN` from the charts, the ExternalSecret and `secret-access.yaml`; delete the Vault value only with a separate go | none for users |

## Decisions (2026-11-11, the user)

- **Q1 settled: yes.** The assertion becomes mandatory on salesforce-mcp and diagram-render (lot 2).
- **Q2 settled: yes.** The evaluation security checks are rewritten to prove the 401 with the assertion, in lot 2.

## Progress log

- **2026-11-11, lot 1 code (repo only, not built, not applied).** The gateway adds a `ctx` claim (`groups`, `email`,
  `email_verified`, `username`, from the validated identity only) to a tool-call assertion when the binding declares
  `caller_context` (`caller_context.assertion_context`, `call_assertion.mint(caller=...)`); a schema-read assertion never
  carries it. The four servers' byte-identical verifier block strips any client-sent `X-Zuno-Assertion-Caller` header,
  rejects a malformed `ctx` (401), and after a verified assertion hands `ctx` to the tool code as that header;
  `_verified_caller` prefers it and keeps the HMAC headers as the fallback, so the old and new mechanisms coexist.
  Tests: `components/mcp-gateway/tests/test_wp250_assertion_context.py` (7) and
  `components/mcp-servers/*/tests/test_wp250_assertion_caller.py` (9, byte-identical in the four servers); the existing
  lot B, lot C, WP-247 and per-server assertion suites still pass. To do: build mcp-gateway and the four server images
  (needs the user's go), roll, golden path, then lot 2.

## Questions asked (answered above)

- **Q1.** diagram-render and salesforce-mcp do not require an assertion today. Is it acceptable to make it mandatory on
  both (salesforce has no org on demo333)? Proposed: yes.
- **Q2.** The evaluation security checks (`evaluations/*/security_checks.py`) use the token to prove the 401. They must
  be rewritten to prove it with the assertion. Proposed: same lot as lot 2.

## Proof

- A call with no assertion, or with an assertion for another audience or tool, gets 401 on every server.
- Holding any namespace `SecretStore` role, the token path is no longer readable (it no longer exists in the store's key list).
- A forged `X-Zuno-Caller-Context` header changes nothing: the caller comes from the verified claims.
- The golden path passes after each lot; the tool-call latency stays within 100 ms of today's.

## Acceptance

- No component reads `MCP_GATEWAY_WORKLOAD_TOKEN`; `grep -r gateway-workload-token gitops platform ansible` finds only history.
- The post-demo list item 1 states the workload token is retired.
