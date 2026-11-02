# ADR-0590: Front OpenClaw with oauth2-proxy and an egress firewall, one claw-operator per persona namespace

- **Status:** Implemented (2026-11-02, WP-183: installed on demo333, `make d2 check openclaw` green)
- **Target:** v0.13
- **Date:** 2026-11-02
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0589](0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md) (decision 1's namespace sentence and decision 5 only) - its decisions 2, 3, 4 and 6 stand
- **Related:** [ADR-0589](0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md), [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0586](0586-verify-the-unifai-runtime-images-by-digest-signature-and-attestations-before-deploying-them.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md)

## Context

ADR-0589 chose claw-operator for per-persona OpenClaw assistants. Its WP-182 spike on demo333
([evidence](../roadmap/evidence/wp-182-openclaw-spike.md), claw-operator commit `f5aa592`) confirmed the
token path (decisions 2 to 4: the operator's proxy exchanges a client-credentials token on Keycloak's Route,
refreshes it and adds the `X-Zuno-*` headers, so no first-party sidecar is needed) and disproved three
assumptions:

- the operator **creates no namespace** and its bundle supports `OwnNamespace` and `SingleNamespace` only: one
  operator watches one namespace;
- the operator owns `gateway.auth.*`: OpenClaw's **trusted-proxy mode cannot be set**, only `token` or
  `password`; and it always applies its own Route to the Control UI;
- its proxy **always passes `clawhub.ai`, `github.com`, `codeload.github.com`, `registry.npmjs.org`,
  `openrouter.ai`** and part of `raw.githubusercontent.com` through, and its NetworkPolicy allows TCP 443 to any
  address. ClawHub was reachable from the assistant. OpenClaw has no setting that disables ClawHub.

## Decision

1. **One namespace and one operator per persona.** The `openclaw` chart creates `zuno-claw-<persona>` with
   `zuno.io/experience-client: "true"` (WP-179's ingress grant), an `OwnNamespace` OperatorGroup and a
   Subscription with `installPlanApproval: Manual` on the pinned CSV; the role approves only the InstallPlan
   naming that CSV. Personas: `consultant-02` and `sale-01`.
2. **Egress firewall.** Each persona namespace carries an OVN `EgressFirewall` that allows Keycloak's Route host
   and the control-plane nodes on 6443 (the operator runs in the namespace and the API Service resolves to
   those node IPs), and denies `0.0.0.0/0`. It closes the hard-coded passthrough domains, which NetworkPolicies cannot subtract.
   In-cluster services (ai-gateway, mcp-gateway) are not affected.
3. **Front door.** oauth2-proxy (realm `zuno`, client `openclaw-<persona>`, browser flow with PKCE) admits the
   persona's email only, in front of OpenClaw's `password` mode (secret from Vault). Its Route **claims the
   Control UI host before the `Claw` exists**, so the router rejects the operator's Route
   (`HostAlreadyClaimed`) and the UI is reachable only through the front door.
4. **Lockdown in `config.raw`:** no bundled skills, no uploaded skill archives, plugins limited to
   `memory-core`, browser control and elevated tools off. No messaging channel is configured.
5. **Pins.** The catalog by digest; the bundle's manager and proxy images and the OpenClaw image are checked by
   running image ID, because the bundle names them by tag and nothing is signed.

ADR-0589's other decisions stand: the identity per assistant (2), the token injection by the operator's proxy
(3), MCP through the same proxy with ClawHub and community skills disabled (4), and the fallback (6), which is
not needed.

## Alternatives considered

- **One namespace and one operator for both personas** (`SingleNamespace`): fewer pods, but both personas'
  secrets in one namespace, against ADR-0589's one-namespace-per-persona bound. Rejected (user, 2026-11-02).
- **Fork the operator** to allow trusted-proxy mode and drop the passthrough list: one login, no firewall, but a
  maintained fork of an alpha operator. Rejected. The two gaps are not reported upstream (user, 2026-11-02); the
  egress firewall and the front door of decisions 2 and 3 compensate for them in this deployment.
- **The `openclaw-kube` chart:** no proxy, no NetworkPolicy, no Route, last commit 2026-03-13. Rejected.
- **Re-enable device pairing** (`disableDevicePairing: false`): a third barrier and an approval step per browser
  during the demo. Not taken; see Security considerations.

## Consequences

- Two operator Deployments, one per persona, upgraded together by one pin change (`catalogImage`,
  `startingCSV`, `pinnedImageDigests`).
- The person signs in twice: Keycloak (oauth2-proxy), then OpenClaw's password.
- The operator requeues periodically while its Route is not admitted (`Route exists but status not populated`);
  harmless, visible in its log.
- An EgressFirewall is a namespace object on OVN-Kubernetes; another network plugin would need another egress
  control.

## Security considerations

Residual risks, accepted for a demo with demo accounts: no signature on any claw-operator or OpenClaw image (a
pin by digest, ADR-0586 decision 7 posture for third parties); the operator is alpha and built per commit;
OpenClaw's device check is off and it has no auth rate limit (the operator owns `gateway.auth.*`), both
compensated by oauth2-proxy in front; the proxy's own egress is any address on 443, so the EgressFirewall is the
control that keeps the assistant off the internet and `make d2 check openclaw` tests it from each pod.

## Operational considerations

`make d2 check openclaw` asserts, per persona: the CSV and the `Claw` Ready, the running image IDs equal to the
pins, the front-door Route admitted and no other Route admitted, a 302 to Keycloak without a session, and from
the assistant's pod a 200 from the ai-gateway through the proxy, nothing when the proxy is bypassed, nothing from
`clawhub.ai` or the internet.
