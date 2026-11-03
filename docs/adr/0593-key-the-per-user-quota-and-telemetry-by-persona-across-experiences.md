# ADR-0593: Key the per-user quota and telemetry by persona across experiences

- **Status:** Implemented (2026-11-03, WP-190 phase 1: persona claim live, build 36, one budget proved across the three experiences)
- **Target:** v0.13
- **Date:** 2026-11-03
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0589](0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md), [ADR-0590](0590-front-openclaw-with-oauth2-proxy-and-an-egress-firewall-one-claw-operator-per-persona-namespace.md), [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md), [ADR-0570](0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md)

## Context

ADR-0587 puts three user experiences (UnifAI, Open WebUI, OpenClaw) on one governed backend and asks that a person's
budget be the same whichever one they use. The WP-184 shared-quota run of 2026-11-03 showed what holds today. The ai-gateway
ledger (`app/quota.py`) keys the per-user token counter by the token `sub`. Open WebUI and UnifAI call with the
signed-in person's own token, so they spend one counter: a budget spent in Open WebUI refused the next UnifAI call
(429 `quota_exceeded`). OpenClaw calls as a Keycloak service account (`service-account-openclaw-<persona>`, ADR-0589),
another `sub`, so it has its own counter and shares only the group budget. The metric label `user` has the same split.
ADR-0589 recorded this as a consequence; it makes "one user, one budget" false for the third experience.

The assistant works in the background without a browser session, which is why ADR-0589 rejected forwarding the
person's own token to OpenClaw. That rejection stands here.

## Decision

**The per-user quota counter and the `user` telemetry label are keyed by persona, a value derived only from validated
token claims, for every experience.**

1. **Persona.** The persona of a call is, in this order: the `persona` claim when the token carries it; otherwise the
   token's `preferred_username` when it is a person's token; otherwise the token `sub`. A `preferred_username` that
   starts with `service-account-` is never used as a persona. The value never comes from a request header (ADR-0033).
2. **Claim.** Keycloak sets `persona=<id>` on every token of the clients `openclaw-<persona>` with a hardcoded-claim
   mapper (one per client, in the `protocolMappers` of the client in `realm-zuno.json`: the client-reconcile Job re-applies each
   client on every Keycloak sync, so the mapper is durable and needs no live step). The service account keeps its
   groups; only the identity of the budget changes. The gateway honours a `persona` claim only for a token whose
   `azp` is an `openclaw-*` experience client.
3. **Quota.** `check` and `consume` of the ai-gateway ledger use the persona for the `user` dimension, in the memory
   and Redis stores alike (`zuno:quota:<class>:user:<persona>:<bucket>`), and `quota_windows` uses the same key for
   `Retry-After`. Group and project dimensions are unchanged. The per-user ceiling stays enforced by the ledger, not
   by MaaS (ADR-0570, WP-177).
4. **MaaS attestation.** The attested header `X-Zuno-User-Sub` carries the persona, so no Kuadrant policy changes.
5. **Telemetry.** The `user` label of `zuno_model_*` (the guardrail metrics have no `user` label) and the dashboards'
   `$user` variable are the persona, which changes the value for every person from the Keycloak id to the username; series
   recorded before keep the id. The raw token `sub` stays in the span attribute `zuno.user_sub` and in logs, for audit.
   The semantic cache stays keyed by the raw `sub`, so an assistant turn never reads the person's cached answers.
6. **Unchanged.** OpenClaw keeps its service account, its token-injecting proxy and its client credentials. Using the
   person's own token for the interactive OpenClaw session is a spike of WP-190 with a go/no-go, not a decision.
7. **Alignment of the three experiences on the platform** (observability, network and mesh, automation, common chart and
   role base) is tracked by WP-190 phases 2 to 4; each decision it takes is recorded as an amendment of this ADR.

## Alternatives considered

- **Derive the persona from the client name (`azp`) in the gateway:** no Keycloak change, but a naming convention
  becomes a security rule; a renamed or new client would silently change whose budget a call spends.
- **Forward the person's own token to OpenClaw (token exchange or a refreshed session token):** the real unification of
  identity, but no token exists for background work, and it needs a realm change and a change of the alpha claw-operator
  proxy. Kept as a spike.
- **Leave OpenClaw on its own counter:** what ADR-0589 chose; the demonstration then has to explain why one persona has
  two budgets.

## Consequences

- One budget per person across Open WebUI, UnifAI and OpenClaw; the `user` series of a persona join across the `client`
  label. Series keyed by token `sub` in history stay as they are.
- Two accounts of one persona now share a ceiling: an OpenClaw runaway can exhaust the person's budget in the other UIs.
  That is the point, and the reason the group and project ceilings stay.
- ADR-0589's consequence about the assistant's identity is superseded for quota and telemetry; its other content stands.
- The check-before-consume race (concurrent calls all pass) is unchanged and documented, not solved here.

## Security considerations

The persona is a signed claim or a Keycloak-owned username. A client that can obtain a token with a chosen `persona`
claim could spend or exhaust another person's budget, so the mapper is hardcoded on a confidential client whose secret
is in Vault, and no user-editable attribute feeds it. The gateway must not accept `persona` from an unsigned source and
must not treat a token from a client outside the declared experience clients as carrying one.

## Operational considerations

`/metrics` shows one `user` series per persona across clients. A token of an `openclaw-<persona>` client without the
`persona` claim falls back to its own `sub` and gets its own counter: check the mapper first when OpenClaw's budget does
not move with the person's.
