# ADR-0563: Forward caller identity and Zuno context headers from UnifAI

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0032](0032-propagate-trusted-identity-end-to-end.md) (propagate trusted identity end to end)
- **Related:** [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md), [ADR-0033](0033-derive-user-identity-only-from-validated-tokens.md), [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md), [ADR-0528](0528-rekey-project-binding-quota-and-telemetry-onto-the-zuno-project-id.md), [ADR-0543](0543-propagate-a-per-run-id-across-every-service-span.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0566](0566-instrument-unifai-with-opentelemetry.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

ADR-0032 made the end user's validated bearer token travel
`Frontend -> BFF -> Agent Runtime -> AI Gateway / MCP Gateway`, and forbade
placeholder credentials such as `Bearer not-required`. Today that chain is
implemented by `components/agent-runtime/app/clients/model_router.py`, which
builds the gateway client with the caller's token and sets, per call,
`X-Zuno-Data-Classification`, `X-Zuno-Local-Only`, `X-Zuno-Agent`,
`X-Zuno-Task`, `X-Zuno-Request-Id`, `X-Zuno-Project-Id`, `X-Zuno-Run-Id` and
`X-Zuno-Max-Tokens`. `components/ai-gateway/app/main.py` consumes all of them
plus `X-Zuno-Quota-Class`, and forwards the caller token onwards to MaaS
(`app/maas_adapter.py` `_maas_bearer_token` prefers it over the pod's
ServiceAccount token, so MaaS sees the real user's `sub` and `groups`).

UnifAI (ADR-0561) does none of this today. In the fork:

- `multi-agent/lib/mas/elements/llms/openai_compatible/openai_compatible.py`
  creates one `openai.OpenAI(api_key=api_key, base_url=base_url, **extra)`
  client per LLM resource, with `api_key` taken from the resource config
  (`BaseLLMConfig.api_key`, default `"EMPTY"`). `extra` is passed through, so
  a *static* `default_headers` map is already expressible; nothing per-user or
  per-call is.
- `elements/providers/mcp_server_client/mcp_provider_factory.py`
  `_build_headers` combines a static `additional_headers` map with a stored
  `bearer_token`/credential set when the resource is configured
  (`McpAuthMethod.ACCESS_TOKEN` or `SIGN_IN`). The token is the resource
  owner's, not the current caller's.
- `shared-resources/identity/utils/auth_manager.py` already holds what is
  needed: after the Keycloak OIDC callback it stores `access_token` and
  `refresh_token` in the Redis identity session, refreshes the access token
  when `_should_refresh_token()` says so, and returns it from
  `GET /api/auth/user`. MAS resolves the same Redis-backed session per request
  (`global_utils/flask/decorators.py` `validate_session` ->
  `get_identity_session`); internal services otherwise trust the
  `X-Authenticated-User` header (`global_utils/constants.py`).
- MAS can execute a workflow outside the HTTP request, in distributed mode
  (`mas/engine/factory.py` selects a `TemporalGraphBuilder`;
  `mas/engine/distributed/node_executor.py` rebuilds the session in a worker).
  There is no Flask request, and therefore no session cookie, in that worker.

Without forwarding, every UnifAI model call would reach the ai-gateway either
unauthenticated (rejected by `app/auth.py`) or under a shared resource-level
credential - the exact pattern ADR-0032 forbids, and one that would collapse
MaaS's per-user subscriptions into one identity.

## Decision

**The fork gains two generic capabilities, proposed upstream (ADR-0575):
caller-token forwarding and templated per-call headers, on both the
`openai_compatible` LLM element and the MCP server client.**

1. **Opt-in caller-token forwarding.** `OpenAICompatibleConfig` gains
   `forward_user_token: bool` (default `false`, today's behaviour) and
   `McpProviderConfig.auth_method` gains the value `forward_user_token`. When
   set, the element sends `Authorization: Bearer <access token of the user on
   whose behalf this execution runs>` instead of its stored
   `api_key`/`bearer_token`. The token is resolved at call time, never written
   into the resource, the workflow definition, the session record or the
   conversation history. Forwarding fails closed: when no valid user token can
   be resolved the call raises; it never falls back to the static credential.
2. **Binding, not carriage, settles distributed (Temporal) execution.** When a
   signed-in user executes or submits a session, the HTTP layer records a
   binding `mas:identity_binding:{mas_session_id}` -> identity server-session
   id in Redis, next to the identity sessions themselves and expiring with
   them. The MAS process or Temporal worker that runs a node resolves the
   binding, reads the user's token from `identity:session:{sid}`, and refuses
   a binding recorded for another user than the execution context's
   credential user. No access or refresh token ever reaches MongoDB or
   Temporal's event history, so `forward_user_token` is safe in both engine
   modes. A session started without a signed-in user (the internal
   `X-Authenticated-User` header, a schedule) has no binding and its
   forwarding calls fail closed.
3. **Refresh before use.** A token within 60 s of expiry is refreshed by MAS
   with a `refresh_token` grant against the realm's token endpoint, using the
   same Keycloak client settings as the identity service
   (`KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM`, `CLIENT_ID`, `CLIENT_SECRET`), and
   written back to the identity session hash exactly as the identity service
   does, so the UI and running workflows keep sharing one token. If refresh
   fails, the call fails with an authentication error. MAS enables the whole
   mechanism only with `IDENTITY_FORWARDING_ENABLED=true`.
4. **Templated per-call headers.** `default_headers` on the LLM element, and
   `additional_headers` on an MCP provider in forwarding mode, are templates
   rendered per call and sent with the OpenAI client's per-request
   `extra_headers` (not baked into the client), so one element instance serves
   many sessions. Variables: `{session_id}`, `{user}` (acting human),
   `{identity}`/`{identity_type}` (workspace owner), `{scope}`, `{node_uid}`,
   `{node_name}`, `{node_type}`, and `{tag.<key>}` for every session metadata
   tag, mirrored into the execution context at submission. A header whose
   template references an unknown or empty variable is **omitted**, never
   sent half-rendered, so a missing classification can never reach a gateway
   as an empty value it might misread. Zuno-specific values travel as session
   tags set by unifai-operator (ADR-0564, ADR-0565), keeping the fork free of
   Zuno names: `X-Zuno-Agent: {tag.zuno-agent}`,
   `X-Zuno-Task: {tag.zuno-task}`,
   `X-Zuno-Data-Classification: {tag.zuno-classification}`,
   `X-Zuno-Run-Id: {session_id}`.
5. **Zuno headers that confer entitlement are not trusted from a template
   alone.** `X-Zuno-Project-Id` and `X-Zuno-Quota-Class` draw down quota
   (ADR-0511, ADR-0528). ADR-0528 requires the project id to be
   server-resolved from a verified grant, not client-asserted. UnifAI has no
   Zuno project model, so before either header is emitted from UnifAI, WP-146
   must choose between the ai-gateway verifying the caller's grant on the
   project itself, or the header being signed by a component that verified it.
   Until then UnifAI does not send them and calls draw on the user's own
   budget.

## Implementation note (2026-10-17)

Live-proven on demo333 (WP-146 step 5). The live run also exposed an
upstream defect clause 2 depends on: foreground runs on the Temporal engine
did not ship the `ExecutionContext` to workers, so nodes ran with no session
id and an `unknown` identity. Fixed in the fork (`5ba7aed85`) and proposed
upstream; until a stack runs an image carrying that fix, forwarding fails
closed for foreground Temporal runs.

## Planned supersession

None. ADR-0032's decision stands and is implemented by a new hop; its
implementation-state paragraph naming `agent-bff` and `agent-runtime` becomes
historical at cutover (WP-156) and receives a dated note, retiring no clause.

## Consequences

The ai-gateway and MaaS see the same caller identity as today, so per-user
quotas, MaaS subscriptions keyed on `groups` and every `zuno.user_sub` span
attribute keep their meaning. The MCP side gains the same property, which the
MCP gateway's group-based authorization (ADR-0036) depends on.

Both capabilities are generic - any OIDC-fronted model gateway or MCP server
benefits - which is what makes them candidates for upstream rather than a
permanent fork delta. The Zuno-specific part is only the header mapping, which
lives in the operator's emitted resources.

## Security considerations

The forwarded token is the user's Keycloak access token for the `unifai`
client (ADR-0562). The ai-gateway's `validate_token` checks issuer and
signature, and checks audience only when `JWT_AUDIENCE` is set; the audience
the gateway expects from UnifAI-issued tokens must be configured explicitly in
WP-146, otherwise any token of the `zuno` realm is accepted.

Tokens are never logged, never stored in MongoDB, never placed in Langfuse or
OTel attributes, and never rendered into a header other than `Authorization`.
The template engine must reject a placeholder that would expose the token.

Templated headers are only as trustworthy as the resource that declares them.
A UnifAI user able to create a custom LLM resource pointing at the gateway can
set any `X-Zuno-*` value. ADR-0565 makes classification safe against lowering;
clause 5 keeps quota-bearing headers out until they can be verified.

## Operational considerations

Acceptance (WP-146, then on demo333 in WP-151 - powered off at the time of
writing; the user must be asked to power it on): a UnifAI turn produces an
ai-gateway `model_call` span whose `zuno.user_sub` equals the logged-in
persona's `sub`; an MCP tool call reaches `mcp-gateway` with the same `sub`;
expiring the access token mid-session triggers a refresh, not a 401; revoking
the Keycloak session makes the next call fail closed. Any `oc` command passes
`--context` explicitly (ADR-0559).
