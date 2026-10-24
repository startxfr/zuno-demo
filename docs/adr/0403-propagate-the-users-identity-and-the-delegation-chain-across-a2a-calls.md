# ADR-0403: Propagate the user's identity and the delegation chain across agent-to-agent calls

- **Status:** Accepted (2026-10-24) - the decisions below are settled; it becomes `Implemented` once the proofs of "Before Implemented" are made live (WP-174)
- **Target:** v0.11
- **Date:** 2026-10-24
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md), [ADR-0032](0032-propagate-trusted-identity-end-to-end.md), [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md), [ADR-0401](0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0402](0402-adopt-a2a-as-the-inter-agent-protocol.md), [ADR-0406](0406-limit-agent-delegation-by-depth-cycle-and-budget.md), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0563](0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md)

## Context

The stub (2026-08-13): "Keep authorization grounded in the initiating user during
delegated operations." The 2026-10-24 reassessment called it the real gap.

Today the user's own Keycloak access token is forwarded unchanged from the browser
to every gateway (ADR-0032, ADR-0563, live-proven by WP-146). Each gateway validates
the JWT itself and applies the five factors of ADR-0011. UnifAI's A2A client is not
wired into this: it sends static headers, no user token, no `X-Zuno-*` context, and
nothing identifies the initiating user to the remote agent. UnifAI has no A2A server,
so there is also no inbound identity for a delegated run.

Keycloak offers no token exchange here: the realm is created once and reconciled only
for clients (ADR-0530), no `act` claim or delegation audience exists, and `JWT_AUDIENCE`
is not enforced at the gateways. ADR-0032 explicitly chose to reuse the end-user token
rather than an on-behalf-of exchange.

## Decision

1. **The initiating user's JWT is the identity of the whole chain.** A delegating
   agent forwards the same access token it received, through the existing mechanism
   (UnifAI `IdentityForwarder` and the identity binding of ADR-0563). The target
   never runs under a service identity and never under the delegator's.
2. **The chain is declared in headers.** On a delegated call the A2A client adds
   - `X-Zuno-Delegated-By: <agent>:<task>[,<agent>:<task>...]`, outermost delegator
     first, nearest delegator last;
   - `X-Zuno-Delegation-Depth: <n>`, the number of hops, equal to the number of
     entries.
   `X-Zuno-Agent` and `X-Zuno-Task` keep naming the agent that executes the call,
   the target. The values are rendered by the platform from the run's tags (ADR-0563
   clause 4); an unresolved variable omits the header, which the gateway then reads as
   no delegation (a depth of zero), not as a valid one.
3. **The gateway verifies the chain on every call, in the one evaluation path** (never a
   second one): it refuses when
   - the headers are malformed, or the depth differs from the entry count;
   - a delegator's signed OKF declaration does not list the next hop as a target (ADR-0401);
   - an agent in the chain is not `active` or is revoked (ADR-0584);
   - the user is not entitled to the target agent (ADR-0040);
   - the chain exceeds the depth limit or repeats an agent (ADR-0406).
4. **The tools of the target are authorized by ADR-0011 on the target alone.**
   Agent declaration, task rights, tool policy, classification and groups all apply to
   the target as they do today. The delegator's tool rights are not intersected:
   delegation exists so that B can do what A cannot. "A task can only narrow its agent's
   declaration" (`policy.py`) still holds.
5. **Classification rises along the chain and never falls (ADR-0565).** `preferred_classification` is the
   level a run starts at, and it escalates during the turn; it is not a ceiling. On a delegation the
   delegating run passes its current level with the A2A request (`X-Zuno-Data-Classification`); the
   target's run starts at the higher of that and its own default and only rises; the result returning to
   the delegator raises the delegator's run to at least the target's final level, so the ai-gateway floor
   and the local-only rules (ADR-0035, ADR-0550) apply to what comes back. The mcp-gateway judges each
   call on the header it receives, as for any call: it cannot see the delegator's run, so keeping the level
   monotone is the duty of the A2A client and server (WP-173), proven by their tests.
6. **The chain is audited.** The gateway log line and the tool span add the user's
   `sub`, `delegated_by` (the chain) and `delegation_depth`, so a delegated call can be
   reconstructed. Counters keep their current low-cardinality labels.
7. **Failure is closed.** No user token, an expired or unrefreshable binding, or a call
   that carries chain headers and fails any check above: the call is refused. No fallback
   to a static credential (ADR-0563 clause 1). A call with no chain headers is a direct
   call (depth 0) and is evaluated exactly as today.

## Residual risk

The chain headers, like `X-Zuno-Agent` (ADR-0563 clause 4, WP-146 step 6), are not
cryptographically bound to the token, and a call without them is a direct call. That is
acceptable for privilege: whoever holds the user's token can already call, directly, every
tool of every agent that user is entitled to, so omitting or forging the chain gives
nothing new. What it defeats is governance and attribution for that call: the target list,
the depth and cycle limits, the write flag and a truthful `delegated_by` in the audit.

The chain controls therefore bind what the platform's own agents do on a user's behalf,
whose headers the platform renders (ADR-0563 clause 4), and not a hostile holder of the
token. This is the same boundary as `X-Zuno-Agent`. Token exchange (below) and WP-146
step 6 would close it; until then the audit says what the headers claimed, not what was
proven.

## Decisions of 2026-10-24

Taken with the user while closing this record:

- **The residual risk is accepted**, because it concerns attribution and governance, not privilege (see above).
  The record is not held back for a signed chain. Rejected: waiting for a chain signed with a workload secret or
  for a Keycloak token exchange, which would add a signing component or a realm change (the realm is created once,
  ADR-0530) for a risk that grants nothing new.
- **Conditions before the first live delegation.** Two older weaknesses are closed before Tekos declares any target
  (WP-174's prerequisites, not this record's): WP-146 step 6 (who may author the `X-Zuno-*` templates in UnifAI)
  and the enforcement of `JWT_AUDIENCE` on the gateways (today a token from any client of realm `zuno` is accepted).
- **The format is frozen:** `X-Zuno-Delegated-By: <agent>:<task>[,...]` and `X-Zuno-Delegation-Depth: <n>`. The
  gateway applies it and the WP-173 brief gives it to the fork, so a later change costs two repositories.
  Rejected: waiting for the A2A server to choose a structured or signed header.
- **No headers means a direct call (depth 0),** evaluated exactly as before. Rejected: refusing a direct call to an
  agent that is somebody's declared target; Arkos stays usable directly by a user who holds its group.

## Before Implemented

On demo333: a delegated call carries the user's own token and the chain, shows in the gateway audit line and the
trace with the user's `sub`, `delegated_by` and `delegation_depth`, and the refusals of ADR-0401's list hold. The two
conditions above are met before that run.

## Alternatives considered

- **Keycloak token exchange per hop** (RFC 8693 or RHBK standard exchange): the
  strongest option, with an audience-narrowed short-lived token and an actor record.
  Deferred: not verified on the live realm (an `act` claim may not be produced), needs
  the Admin API because the realm is create-only, and reopens ADR-0032's choice.
  It is the hardening path for the residual risk, together with enforcing
  `JWT_AUDIENCE`.
- **Chain attested by the gateway with a workload secret** (as ADR-0570's attested MaaS
  headers): sound, but adds a signing component for a risk that is attribution only.
  Reconsidered if the audit needs non-repudiation.
- **A service identity for the target:** rejected; it breaks the per-user quota and
  authorization model (ADR-0032: no fabricated groups for service identities).

## Consequences

- `components/mcp-gateway/app/` gains a chain parser and validator (`agent_chain.py`,
  distinct from `delegation.py`, which is OAuth credential delegation), a delegation
  context in `policy.evaluate`, and the new log and span fields.
- UnifAI's A2A node needs `forward_user_token` and templated headers, and an A2A server
  must validate the JWT and run the workflow as the caller (WP-173).
- ADR-0011 gets a dated note stating the rule for a delegated call (clause 4 above).

## Security considerations

The decision does not widen any user's access: every tool a delegated call reaches is one
the target agent declares, in a task of that agent, for a user who holds that agent's
group. It narrows what an agent can do on its own behalf by requiring a signed
declaration for every hop.

## Review evidence

`components/mcp-gateway/app/{auth,policy,main,agent_declarations}.py`, `gitops/charts/keycloak/`,
ADR-0032, ADR-0563, ADR-0571 and the UnifAI fork's `identity_forwarding.py` and
`a2a_agent` node, read on 2026-10-24.
