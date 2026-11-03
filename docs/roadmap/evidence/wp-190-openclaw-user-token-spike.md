# WP-190 spike: OpenClaw with the person's own token

- **Date:** 2026-11-03
- **Type:** desk analysis from the WP-182 spike and the installed WP-183 design; nothing was run on the cluster for it.
- **Question:** could OpenClaw call the ai-gateway and the mcp-gateway with the signed-in person's token, instead of a
  per-persona service account, so that the identity (not only the budget key, [ADR-0593](../../adr/0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md)) is the same in all three experiences?

## What is installed (WP-182, WP-183)

- The assistant's calls leave the Claw pod through the claw-operator's credential proxy, which strips any `Authorization`
  and injects a **client-credentials** token (`golang.org/x/oauth2`, `internal/proxy/injector_oauth2.go`), cached and
  refreshed by the proxy; the pod never holds a usable token ([wp-182-openclaw-spike.md](wp-182-openclaw-spike.md), steps 2 and 3).
- The person signs in to the Control UI through oauth2-proxy (browser flow, PKCE) and then OpenClaw's own password. The
  oauth2-proxy session ends at the front door: the Claw gateway receives no token from it, and OpenClaw's model and tool
  calls do not run inside that browser request.
- The assistant also works in the background (scheduled and long tasks), when no browser session exists.

## Findings

1. **The operator has one injector for this path, client credentials.** There is no per-session or per-user injector.
   Carrying the person's token would need a new injector in an alpha operator (an upstream change or a fork), plus a way
   for the proxy to look the token up per request.
2. **The token is not where the calls are.** oauth2-proxy can pass the access token upstream (`--pass-access-token`,
   `--set-xauthrequest`), but the Control UI backend is not the party that calls the gateways; the calls come from the
   agent runtime in the pod. Forwarding would reach the wrong process and would put a usable token in the pod, which
   ADR-0589 decision 3 forbids.
3. **Background work has no person's token.** A refresh token kept for it is a long-lived credential for the person,
   which ADR-0589 rejected (trivial, a bad practice in a public demo). Keycloak token exchange (impersonation) would need a
   realm change and fine-grained permissions on a realm that is created once and reconciled afterwards
   ([ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md) reached the same
   conclusion for delegation), and it widens who can act as a person.
4. **What the user token would add beyond ADR-0593 is small.** The budget, the `user` label and the audit trail key are
   the persona through the signed claim. The identity difference that remains is the `sub` and the fact that the call is
   made by the assistant; for a personal assistant that is the honest statement, and the service account already carries
   the person's groups for tool and model entitlements.

## Go / no-go

**No-go for now.** The persona claim of ADR-0593 gives one budget, one metric series and one audit key without a
long-lived credential or an operator change. Revisit if one of these changes: the claw-operator gains a per-user token
source, the assistants stop doing background work, or the platform needs per-call attribution to the `sub` of a person
(for example an audit rule that forbids a service-account actor).

## If revisited

Interactive-only first: an operator injector fed by a short-lived, audience-bound token that the front door obtains with
a token exchange for the signed-in person (standard exchange of an existing subject token, no impersonation), refused
whenever there is no browser session; background calls stay on the service account and the persona claim.
