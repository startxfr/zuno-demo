# WP-146: UnifAI identity and context-header forwarding

- **State:** Repo work in review
- **ADRs:** [ADR-0563](../../adr/0563-forward-caller-identity-and-zuno-context-headers-from-unifai.md), [ADR-0562](../../adr/0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0575](../../adr/0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)
- **Depends on:** none
- **Related:** [ADR-0560](../../adr/0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0036](../../adr/0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md), [ADR-0021](../../adr/0021-route-models-according-to-c1-c2-c3-classification.md), [WP-148](wp-148-unifai-parity-memory-routing-quota-ux.md), [WP-150](wp-150-unifai-operator-okf-agent-bundles.md)
- **Target:** v0.11
- **Estimated files touched:** ~12 in `startx-unifai` — the `openai_compatible` LLM element, the MCP client element and its transports, the identity/session token lookup, the Temporal execution path, their unit tests, and a NetworkPolicy hardening note in the operator's stack assets. None in `zuno-demo`.

> The first fork-side work package of the UnifAI adoption. Without it the
> ai-gateway cannot tell who is calling, which agent is calling, or at what
> classification, so every policy ADR-0560 keeps in the gateway goes blind.

## Goal

An UnifAI agent node calling an OpenAI-compatible endpoint or an MCP server
can forward the end user's access token and a configurable set of templated
headers (agent, workflow, session, run id, classification, project id), the
token stays valid for long runs, and the change is generic enough to be
proposed upstream.

## Steps

All work happens in `/home/cl/ClaudeCode/startx-unifai`. Generic changes start
from `main` (`make feature-start BRANCH=feat/forward-user-token`) and are merged
into `devel` for testing (`make feature-to-devel`), per `fork/README.md`.
Never put fork-only paths (`fork/fork-only-paths`) on the feature branch.

1. **Read before writing.** Read
   `multi-agent/lib/mas/elements/llms/openai_compatible/{config.py,openai_compatible.py,openai_compatible_factory.py,spec/spec.py,validator.py}`
   and `multi-agent/lib/mas/elements/providers/mcp_server_client/{config.py,mcp_server_client.py,transport/streamable_http_transport.py,transport/sse_transport.py}`.
   Note where the HTTP client is built and where headers can be injected.
   Read `multi-agent/lib/mas/core/identity/ports.py` and
   `multi-agent/adapters/inbound/flask/decorators.py` to see how the caller
   identity (`X-Authenticated-User`) enters MAS today.

2. **Done (fork `4467138fe` on `feat/forward-user-token`, merged into `devel`
   as `45b2f85a1`).** What landed, as ADR-0563 now records it:
   - `OpenAICompatibleConfig.forward_user_token: bool` and
     `default_headers: Dict[str, str]`; `McpAuthMethod.FORWARD_USER_TOKEN`,
     whose `additional_headers` become templates. Rendering is
     `render_header_templates()` in
     `multi-agent/lib/mas/core/identity_forwarding.py`; a header with an
     unresolved variable is omitted. Variables: `{session_id}`, `{user}`,
     `{identity}`, `{identity_type}`, `{scope}`, `{node_uid}`, `{node_name}`,
     `{node_type}`, `{tag.<key>}`.
   - Token source port `IdentityTokenSource` (same module) and its Redis
     adapter `multi-agent/adapters/outbound/redis/identity_token_source.py`:
     binding `mas:identity_binding:{session}` -> identity session, written by
     `/user.session.execute` and `/user.session.submit`; refresh with a
     `refresh_token` grant 60 s before expiry, written back to the identity
     hash. Nothing reaches MongoDB or Temporal history, so Temporal mode is
     covered by the same path.
   - Session metadata tags mirrored into `ExecutionContext.tags` at staging;
     `BaseNode` binds the current node in a ContextVar.
   - Enabled by `IDENTITY_FORWARDING_ENABLED=true` plus `KEYCLOAK_BASE_URL`,
     `KEYCLOAK_REALM`, `CLIENT_ID`, `CLIENT_SECRET` on the multiagent pods.
   - 18 unit tests in `multi-agent/tests/unit/core/test_identity_forwarding.py`;
     the rest of the multiagent unit suite is unchanged (127 failed / 33
     errors before and after, all pre-existing environment failures; 18 more
     passes). Upstream `contrib-check` reports no error.

3. **Done: operator wiring.** unifai-operator 0.1.13 (fork `fb8b94b26`,
   released by the startx-unifai session) adds
   `UnifaiStack.spec.identity.forwardUserToken` (default `false`, no
   rollout when unset). When `true` it sets `IDENTITY_FORWARDING_ENABLED`,
   `KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM` and `CLIENT_ID` on the multiagent
   backend and Temporal worker, and puts `CLIENT_SECRET` in
   `multiagent-be-secret`. Until `:devel` carries the feature,
   `spec.images.multiagent` selects a `devel-<sha>` image.

4. **Done: upstream defect found live and fixed.** Foreground runs
   (`/user.session.execute`) on the Temporal engine never shipped the
   `ExecutionContext` to the worker: `TemporalGraphExecutor` built
   `GraphExecutionParams` without it, so every node ran with an empty
   session id and an anonymous `unknown` identity. Forwarding failed
   closed; per-user OAuth MCP credentials (`credential_user_id`) were
   silently resolved for the wrong user. Fixed on
   `fix/temporal-foreground-execution-context` (`5ba7aed85`, regression
   tests in `multi-agent/tests/unit/sessions/test_foreground_execution_context.py`),
   merged into `devel`; an upstream candidate per ADR-0575.

5. **Done: live proof on demo333, 2026-10-17** (namespace `unifai-devel`
   only, image `quay.io/zuno/unifai-multiagent:devel-cbfb91d42`, a
   throwaway header-echo OpenAI-compatible server, real Keycloak browser
   login as realm `unifai` user `admin` through the UI's own nginx path):
   - the echo server received the user's own JWT (`iss` realm `unifai`,
     `azp=unifai`, `preferred_username=admin`) instead of the static key,
     plus `X-Zuno-Agent: wp146-agent`, `X-Zuno-Run-Id: <session id>` and
     `X-Zuno-Data-Classification: C2` from the session tag;
   - without the tag, `X-Zuno-Data-Classification` was omitted, not sent
     empty;
   - a run started by the operator (`UnifaiChat`, internal header, no
     signed-in user) failed closed with "no identity binding" and never
     reached the model;
   - a second call in the same session after 262 s carried a new token
     (`iat` advanced by 262 s) refreshed by MAS itself, logged as
     "Refreshed forwarded access token".
   All test objects were deleted and the stack spec restored afterwards.

6. **Header authorship (remaining).** Any UnifAI user can create an LLM or
   MCP resource with arbitrary `X-Zuno-*` header templates. Decide whether
   forwarding resources are admin-only, or whether the gateways ignore
   self-asserted headers they cannot verify (ADR-0565 floor, ADR-0563
   clause 5). Record the choice in ADR-0563. The proof against the real
   ai-gateway (realm `zuno` JWT) is part of WP-151.

7. **Hardening.** `X-Authenticated-User` is trusted by internal services
   (`global_utils/src/global_utils/flask/decorators.py`,
   `rag/infrastructure/http/auth.py`). Check that the operator's stack
   NetworkPolicy (`UnifaiStack.spec.exposure.networkPolicy`, rendered from
   `fork/unifai-operator/internal/stack/`) only admits in-namespace callers
   to multi-agent and rag. If it does not, open it as an operator change
   following the release flow below.

8. **Build and release.** Run `make contrib-check` on the feature branch.
   Merge into `devel`, build images with `make images-devel` (tags
   `:devel` and `:devel-<sha>`). If the operator changed in step 7: run
   `make test` (envtest) in `fork/unifai-operator` first, bump `VERSION` in
   `fork/unifai-operator/Makefile`, and coordinate with the startx-unifai
   session before releasing — OLM on demo333 rolls a new operator image to
   both stacks it manages (`unifai-devel`, `unifai-olm`).

9. **Upstream.** Per ADR-0575 and `MEMORY.md` in the fork, contact the
   upstream maintainers (CODEOWNERS) before opening any PR. Do not run
   `make contrib-pr` until the user says so.

## Acceptance

Unit tests pass; with the new fields unset the existing multi-agent unit
suite is unchanged; upstream `contrib-check` reports no error; the feature
branches contain no fork-only path; the live proof of step 5 holds. The
work package closes when step 6 is decided and step 7 is checked.

## Open questions

- A run that outlives the user's SSO session (a HITL pause longer than the
  realm's SSO session) fails closed with "sign in again"; whether that is
  acceptable for scheduled or very long workflows is unsettled. Schedules
  have no signed-in user and cannot forward a token at all.
- **Confirmed open (2026-10-17, startx-unifai session):** the upstream
  `nginx.conf.template` leaves the external `X-Authenticated-User` block
  commented out, and the header is honoured from outside through the UI
  routes `/api1` and `/api2` without any session: anonymous admin access.
  A fix is under review in the fork; step 7 must verify it.
