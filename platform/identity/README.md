# Platform: identity propagation contract

Authoritative reference for how identity flows through the Zuno platform
and how a downstream service (a BFF, the Agent Runtime, the MCP Gateway, or
an MCP tool server) validates a caller and retrieves the caller's delegated
Google Workspace token. The Keycloak realm and clients this document
describes are built by `ansible/roles/keycloak` / `gitops/charts/keycloak`
- see that role's README for the deployment/operator side.

## 1. The JWT and its `groups` claim

Every agent frontend authenticates its user against one Keycloak realm,
`zuno`, using its own OIDC client (`tekos-frontend`, `arkos-frontend`,
`comage-frontend`, `advantage-frontend`, `finage-frontend`,
`naveo-frontend` - all confidential, server-side authorization-code
exchange with a Vault-held client secret since each agent's real
frontend shipped; `soursage-frontend`/`cognos-frontend` remain public
SPA placeholders until those ADR-0349 agents are built).
Keycloak issues a standard OIDC access token (JWT) for the authenticated
user. Every client has a per-client protocol mapper
(`oidc-group-membership-mapper`, `full.path: true`) that adds a `groups`
claim to the access token, ID token and userinfo response:

```json
{
  "sub": "3fabc12e-...-b2a1",
  "preferred_username": "consultant-01",
  "email": "dev+zuno-consultant01@startx.fr",
  "groups": ["/consultant", "/agent_tekos"],
  "iss": "https://keycloak.<cluster-apps-domain>/realms/zuno",
  "aud": "tekos-frontend",
  "exp": 1234567890
}
```

- `groups` is always an array of full group paths (leading `/`). There
  are two orthogonal dimensions: one **agent entitlement**
  group (`agent_comage`, `agent_tekos`, `agent_advantage`, `agent_finage`,
  `agent_arkos` - governs frontend/BFF access to that agent) and one
  **business role** group (`sales`, `consultant`, `adv`, `finance`, `board`,
  or `sales_admin` - governs tool/data permissions inside an already
  authorized agent). Downstream services must not assume any particular
  cardinality - treat `groups` as a set and check for the specific
  claim(s) each check cares about.
- Group name to agent-client mapping, and group membership, is defined in
  `gitops/charts/keycloak/files/realm-zuno.json`; the current members are
  documented in `ansible/roles/keycloak/README.md`.
- **This `groups` array is the contract the policy-intersection reads.**
  See `policies/tools/tool-policy.yaml`'s header for the exact
  five-factor intersection formula the MCP Gateway evaluates, of which the
  caller's `groups` claim is one input (`user_group_rights`).

### Validating the token

Any hop that terminates or re-validates the token must fetch the realm's
JWKS and verify the standard claims (`iss`, `aud`, `exp`, signature):

```
GET https://keycloak.<cluster-apps-domain>/realms/zuno/protocol/openid-connect/certs
```

Do not trust an inner `groups` claim forwarded by an upstream hop without
either (a) re-validating the JWT signature yourself, or (b) trusting a hop
that already did so and terminates at a boundary you control end-to-end.
The MCP Gateway must always validate the token itself rather than trust
an assertion from the Agent Runtime.

## 2. Hop-by-hop forwarding

The raw Keycloak-issued access token is forwarded as a bearer token
across every hop, unmodified, for as long as the receiving service
supports it:

```
Frontend (SPA)
  --Authorization: Bearer <access_token>-->
BFF
  --Authorization: Bearer <access_token>-->
Agent Runtime
  --Authorization: Bearer <access_token>-->
MCP Gateway  (policy-intersection enforcement point - ADR-0011)
  --Authorization: Bearer <access_token>-->
MCP tool server (confluence / google-workspace / confluence / web-search / smtp-technical)
```

- The MCP Gateway is the single point that evaluates the full
  intersection (agent declaration ∩ task rights ∩ user/group rights ∩
  classification ∩ platform policy - see
  `policies/tools/tool-policy.yaml`) before allowing a tool call to reach
  an MCP server. It must re-validate the token per section 1 rather than
  trust the Agent Runtime's forwarding.
- If a hop cannot forward the raw token as-is (e.g. it needs a
  narrower-audience token for a specific downstream client), it should use
  OAuth 2.0 Token Exchange (RFC 8693) against Keycloak rather than
  minting its own assertion.
- Service-to-service calls not acting on behalf of a specific end user
  (e.g. the monthly knowledge-ingestion job) use a dedicated service
  account/client credentials grant instead of a forwarded user token - do
  not fabricate a `groups` claim for these.

## 3. Retrieving the user's stored Google Workspace token

The Google IdP broker (`identityProviders[0]`, alias `google`, in
`realm-zuno.json`) is configured with `storeToken: true`, so Keycloak
retains the user's Google access/refresh token after a broker login, and
`addReadTokenRoleOnCreate: true`, so every user who has ever logged in via
Google automatically holds the realm's built-in `broker` client's
`read-token` role - no manual role grant is required.

**Use the user-facing broker token endpoint, not the Admin REST API:**

```
GET https://keycloak.<cluster-apps-domain>/realms/zuno/broker/google/token
Authorization: Bearer <the same user access token forwarded hop-by-hop, see section 2>
```

This is the correct endpoint for an MCP tool server (e.g.
`components/mcp-servers/google-workspace`) acting on behalf of the
currently-authenticated user: it's a per-user, self-service lookup using
the same forwarded end-user bearer token described in section 2, so the
tool server never needs an elevated credential of its own, only the
caller's own token and the `read-token` role that login already granted.

The alternative, `GET /admin/realms/zuno/users/{id}/federated-identity/google`,
is an administrative endpoint requiring a realm-admin or service-account
token with `view-users`/`manage-users` privileges - a standing,
realm-wide credential capable of reading *any* user's stored Google
token. Reserve it for genuine admin tooling (e.g. an operator revoking a
stale federated link), not a request-time tool call.

Response shape (Keycloak's standard OAuth token response - this is
Google's last token response, cached):

```json
{
  "access_token": "ya29.a0Af...",
  "token_type": "Bearer",
  "expires_in": 3599,
  "refresh_token": "1//0g...",
  "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/drive.readonly"
}
```

- If the stored Google `access_token` is expired, Keycloak transparently
  refreshes it using the stored `refresh_token` before returning - the
  caller does not need to handle the Google refresh flow itself.
- If the user never completed a Google broker login, or revoked access
  externally, this call returns `400`/`404` - the calling MCP tool server
  must surface this as "reconnect your Google account" rather than a
  generic failure (never fall back to a shared/service credential, per
  MEMORY.md section 8).
- Google credential/session material retention follows MEMORY.md section 5
  (retained up to five days, must be revocable by the user) - a Keycloak
  broker-session/token-store configuration concern, not enforced per call
  by this endpoint.

## 4. Scopes granted

The Google IdP requests: `openid email profile
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/drive.readonly` - read-only Gmail and
Drive access, matching MEMORY.md section 8 ("Comage reads the user's Gmail
mailbox but never sends mail as the user"; outbound mail uses a technical
SMTP identity instead, see `send_technical_report_email` in
`policies/tools/tool-policy.yaml`). If a future agent needs write access to
Drive/Docs (e.g. Arkos's DAT workflow), extend `defaultScope` on the
`google` identity provider in `realm-zuno.json`.
