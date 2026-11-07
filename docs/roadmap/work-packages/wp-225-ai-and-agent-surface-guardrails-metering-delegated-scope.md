# WP-225: AI and agent surface: guardrails, metering, delegated scope (delivers ADR-0602, ADR-0603)

- **State:** Operator pending (lots A and B, 2026-11-07); lot C Not started
- **ADRs:** ADR-0602, ADR-0603
- **Depends on:** WP-222, WP-209 (classification floor; do not duplicate its work)
- **Blocks:** WP-227
- **Estimated files touched:** ~20

> Execute this brief as a standalone task from the repository root.

## Goal

Make the guardrails enforce (C7), meter the Anthropic-format paths (C8), and stop shared service identities acting beyond
the caller's scope (C9, M12 to M15).

## ADR references

ADR-0602 clauses 8 to 11; ADR-0603 clause 3. Classification (C10) belongs to ADR-0565 and WP-209.

## Preconditions

- Re-read `components/ai-gateway/app/guardrails.py` and `main.py` (`_observed_stream`), `guardrails-policy.yaml` in
  zuno-demo-agents, `components/mcp-gateway/app/downstream.py`, `components/mcp-servers/*`.
- Read `docs/roadmap/work-packages/wp-220-*.md` and the quota notes first: `/v1/messages` stays open.

## Repo changes

1. Guardrails: `block` fails closed for C2 and above; tool and RAG text scanned; streams buffered or cut on detection;
   model-based classifier added to the regular expressions.
2. Metering: per-key token ceiling on `/v1/messages` and `/v1/responses`, in the ai-gateway or by a Limitador data-extraction
   rule.
3. Scope: space, repository and recipient allowlists in the Confluence, git-forge and email servers, from signed context;
   Salesforce owner scoping; namespace matcher injected into the Kubernetes metrics query.
4. mcp-gateway: token exchange or a signed per-call assertion instead of forwarding the bearer; the same entitlement check on
   the REST path as on `/mcp`; authenticated callers for Dify and the token proxy; signed delegation chain headers in a2a-gateway.
5. Metrics: drop the per-user label; bound JSON-RPC batch size; rate-limit the AAP audit launch.

## Verification

Negative tests for each: an injected tool result is flagged and blocked; a detector outage blocks a C2 request; a request
past the key ceiling on `/v1/messages` is refused; a space outside the caller's group is refused.

## Lots

The brief is delivered in three lots. Lot A is the ai-gateway (clauses 8 and 9). Lot B is delegated scope in the MCP servers
and the metrics items (repository change 3 and the three items of change 5). Lot C is the mcp-gateway identity path and the
a2a-gateway (repository change 4).

| Lot | Scope | State |
|---|---|---|
| A | guardrails (C7) and metering (C8) in the ai-gateway | Operator pending |
| B | space, repository and recipient allowlists; Salesforce owner scoping; namespace matcher; no per-user label; JSON-RPC batch bound; AAP launch limit (ADR-0603 M12, M13, M15) | Operator pending |
| C | token exchange or a signed assertion; REST entitlement; Dify and token-proxy callers; signed a2a chain (ADR-0603 M14) | Not started |

## Lot A: guardrails and metering (Operator pending, 2026-11-07)

Committed locally on `wp-225-ai-surface`, cut from `wp-209-classification-floor`. Not pushed. Not live. Every switch below takes
effect only in `block` mode or when `meteredPaths.enabled` is true. The shipped values keep every class on `observe` and the
metered paths off, so a merge changes no caller. The pod template gains three always-rendered variables
(`GUARDRAILS_FAIL_CLOSED_FROM`, `GUARDRAILS_SCAN_TOOL_RESULTS`, `GUARDRAILS_STREAM_HOLD_BACK_CHARS`), so the sync rolls the pod once.

Classification is not redone here. The guardrails mode, the fail-closed threshold and the eligibility of a metered path all use
the same effective level as a chat call: the client's model alias selects the task (ADR-0596), `app/classification_floor.py`
applies the agent, task and per-client floors (WP-209), and the ADR-0594 markers of the tool results raise it. On the metered
paths the markers are read from Anthropic `tool_result` blocks and Responses `*_call_output` items, with the chat path's raise and
fail-closed rules; markers in `document` and `search_result` blocks raise the level too, but an unmarked one does not count as an
unmarked tool result (it is supplied by the caller).

### What was built

1. **Fail closed (clause 8).** In `block`, a detector outage refuses the request with a typed `503 guardrails_unavailable`
   from `guardrails.failClosedFrom` up (`GUARDRAILS_FAIL_CLOSED_FROM`, default `C2`; empty means never). This applies to the
   prompt, the reply and a stream. C1 keeps the old fail-open behaviour. `observe` is unchanged. A classifier outage counts
   as a detector outage. A detection found by one engine still blocks when the other one failed. The routing decision
   records `blocked_by: guardrails_unavailable`.
2. **Tool results and RAG text (clause 8).** The scan covers the last user message plus the current turn's tool results and
   retrieved context. On chat that means the `tool` messages after the last user message. On Anthropic it means
   `tool_result`, `document` and `search_result` blocks. On Responses it means `*_call_output` items. A refusal names its
   stage (`prompt`, `tool_result`, `retrieved`, `system` or `reply`). Earlier turns are not sent: their tool results were
   scanned in the turn that produced them. **Shipped off** (`guardrails.scanToolResults: false`, in observe and block alike),
   so a merge keeps today's scan of the last user message; a cluster turns it on with
   `zuno_ai_gateway_guardrails_scan_tool_results`. In `block`, the metered paths also scan the system-level text (Anthropic
   `system`; Responses `instructions` and `system`/`developer` input messages), where a client may carry retrieved context;
   chat system prompts, and system text in `observe`, are still not sent.
3. **Streams (clause 8).** In `block`, `app/stream_guard.py` holds a streamed reply back until
   `guardrails.streamHoldBackChars` characters are pending (400; 0 buffers the whole reply). It checks them with a
   256-character overlap, so a pattern that straddles two segments is seen. After a clean check the events are released
   except those whose text reaches into the last 256 checked characters, so the first part of a match the next segment
   completes is never sent; the tail goes out after the end-of-stream check. On a detection it ends the stream with the
   protocol's error event and closes the upstream:
   - OpenAI chat: `data: {"error": ...}`, then `[DONE]`;
   - Anthropic: `event: error` with `{"type":"error","error":{...}}`;
   - Responses: `event: error`.

   Scanned in a stream: text, tool-input and reasoning deltas (Anthropic `thinking_delta`, Responses
   `response.reasoning_text.delta` and summary deltas, refusal deltas), text carried by a `content_block_start`, the full text
   a `.done` event or `response.completed` repeats, and the string content of any event type not known to carry none.
   Non-streamed replies include `thinking` blocks and `reasoning` output items. `observe` streams still pass through untouched.
4. **Model-based classifier (clause 8).** `app/guardrails_classifier.py` defines one interface:
   `classify(contents) -> detections`, raising on an outage. It ships one implementation, `detectors-api`, the FMS
   Guardrails detector API that TrustyAI's Hugging Face detector runtime serves. Configuration is
   `guardrails.classifier.{type,url,detectorId,threshold}`, with `type: ""` (off) by default. No model is wired. A detection
   is named `classifier:<detection>`, and matched text is never kept. Other implementations register with
   `register(name, factory)`. A type set without its URL or detector id fails the chart render, and in the code counts as an
   outage (fail closed where `block` applies).
5. **Metering (clause 9).** The ai-gateway serves three paths:
   - `POST /v1/messages`, plus `/v1/messages/count_tokens`, which is forwarded unmetered;
   - `POST /v1/responses`.

   They are a metered pass-through to a local model that speaks the protocol (`app/metered_paths.py`):
   - Routing: `meteredPaths.models` maps a client model name to provider-routing entries. An entry is used only when it
     is `kind: local`, has an `endpoint`, is eligible for the effective classification and is available. A SaaS key is
     never handed to the pass-through.
   - Counting: usage goes to `zuno.model_tokens` and the token-budget ledger, as a chat call does. Anthropic usage is
     `input_tokens`, plus the cache tokens, plus `output_tokens`. Responses usage is the reply's `usage`. A stream reads
     both from the SSE events. When no usage arrives (a disconnect, a guard cut, no `response.completed`, an unreadable 200
     body) the prompt is estimated from the request body and the completion from the generated text, at four characters
     per token. The upstream is closed and the call metered even when the response body never starts.
   - Ceiling: optional, per key (the persona), per tenant (a Keycloak group, one shared counter) or as a default
     (`meteredPaths.keyCeilings`, `app/key_ceilings.py`). `exemptPersonas` and `exemptClients` are never capped (`exempt`,
     one list for both, is still read). Each call reserves its estimate (prompt plus the requested output cap) until it ends,
     so parallel calls overrun a ceiling by one call at most; `maxConcurrentStreams` caps a key's open streams. Reservations
     and stream counts are per replica.
     Past a ceiling, the caller gets the protocol's 429 with `Retry-After`: Anthropic `rate_limit_error`, or OpenAI
     `type: tokens, code: rate_limit_exceeded`. Default `0` with no entries means no ceiling. A malformed value also means
     no ceiling: the paths are open by decision.
   - Responses state: `background: true`, `previous_response_id` and `conversation` are refused with a protocol-shaped
     400 (state kept upstream would escape the scan and the metering), and `store` is forced to `false`.
   - Off: with `meteredPaths.enabled: false` the paths answer 404, as today.

   The Claude Code key minted on MaaS is not touched: it calls MaaS directly, and MaaS still does not count it
   (WP-220, accepted).

New chart values, all in `gitops/charts/ai-gateway/values.yaml`:
- `guardrails.failClosedFrom` (`C2`), `guardrails.scanToolResults` (`false`), `guardrails.streamHoldBackChars` (`400`);
- `guardrails.classifier.{type,url,detectorId,threshold}` (`""`, `""`, `""`, `"0.5"`);
- `meteredPaths.enabled` (`false`), `meteredPaths.models` (`{}`),
  `meteredPaths.keyCeilings.{window,default,keys,tenants,exemptPersonas,exemptClients,maxConcurrentStreams}`
  (`1h`, `0`, `{}`, `{}`, `[]`, `[]`, `0`).

The llm role passes `zuno_ai_gateway_guardrails_fail_closed_from`, `zuno_ai_gateway_guardrails_scan_tool_results`,
`zuno_ai_gateway_metered_paths`,
`zuno_ai_gateway_metered_paths_models` and `zuno_ai_gateway_key_ceilings`.

No change is needed in zuno-demo-agents. `guardrails-policy.yaml` names the modes and their minimum per class; the
fail-closed threshold and the scan scope are platform configuration. The corp minimum stays `observe` for every class.
Raising one to `block` is the ADR-0534 evidence decision, not part of this lot.

Tests: `tests/test_wp225_guardrails_metering.py` (57 tests, in the CI list, after the review of 2026-11-07). It includes the
four required negative tests:
- an injected tool result is blocked (chat and `/v1/messages`);
- a detector outage blocks C2 and serves C1 (prompt, reply, stream, classifier);
- a mid-stream detection cuts the stream (OpenAI and Anthropic SSE);
- a key past its ceiling on `/v1/messages` is refused while an exempt key passes.

`test_guardrails.py` now pins fail-open at C1 only. The review fixes add tests for the client floor and the model alias on
both paths, a C3 marker in a tool result, the straddle prefix never emitted, reasoning and the other text carriers, the usage
estimate, reservations and the stream cap, a body that never starts, 502s, a misconfigured classifier, the exemption split,
the system-text scan, the Responses state refusals, a Responses stream cut and the chart rendering no metered variable when off.

Limits:
- A gateway path is reachable in-cluster only (the ai-gateway has no Route). Giving an IDE a `/v1/messages` endpoint on the
  gateway would need a Route and a Keycloak token helper; that is not part of this lot.
- On chat, RAG text that a client puts into a system message is not scanned (system prompts are excluded there); the
  metered paths scan it in `block` only.
- Without usage from the upstream, tokens are estimated at four characters per token.
- In `block`, a stream lags the model by up to the hold-back plus 256 characters.

### Live probes (each needs an ai-gateway build and the user's go)

1. **Defaults change nothing.** After the build and sync, check three things. `/v1/messages` on the gateway answers 404. A
   chat at C2 behaves as before (every class is still `observe`). The MaaS Claude Code key still works against MaaS.
2. **Fail closed.** In a window, set `guardrails.modeByClassification.C2: block` on the live Application. Make NeMo
   unreachable (scale `zuno-guardrails` to 0 in `zuno-ai-run`). A C2 chat returns 503 `guardrails_unavailable`, a C1 chat
   (`block` or `observe`) returns 200, and `zuno_guardrails_evaluations_total{outcome="unavailable"}` moves. Then restore
   both.
3. **Injected tool result.** With C2 on `block`, send a chat whose `tool` message contains "ignore all previous instructions".
   It returns 400 with `stage: tool_result`, and `zuno_guardrails_detections_total` moves.
4. **Stream cut.** With C2 on `block`, stream a chat that asks the model to repeat the test card number 4111 1111 1111 1111.
   The stream ends with a `data: {"error": ...}` chunk and `[DONE]`, and the digits are not in the output.
5. **Metering.** Set `meteredPaths.enabled: true` with `models: {gpt-oss-20b: [local-gpt-oss-maas, local-gpt-oss]}`. Send
   `/v1/messages`, plain and streamed, then `/v1/responses`, with a user token. Each moves `zuno_model_tokens_total` for
   `local-gpt-oss-maas` by input plus output tokens. `/v1/responses` on vLLM gpt-oss-20b is not proven yet; WP-220 proved
   `/v1/messages` only.
6. **Ceiling.** Set `keyCeilings: {default: 1000, exemptPersonas: [<the developer persona>]}`. A second `/v1/messages` call from
   another persona returns 429 `rate_limit_error` with `Retry-After`, and the exempt persona is still served. Then reset
   `default: 0`.

## Lot B: delegated scope and metrics hygiene (Operator pending, 2026-11-07)

Committed locally on `wp-225-lot-b`, cut from `wp-225-ai-surface` (lot A). Not pushed. Not live. Every scope check is off
until its chart value is set, so a merge changes no caller, with two exceptions that apply at once: the per-user metric
label is gone, and two bounds have defaults (20 messages per JSON-RPC batch, 2 `cluster_audit` launches per caller per
15 minutes). The pod templates of the five charts gain always-rendered variables, so the sync rolls each pod once.

### The signed caller context

A shared-credential server cannot scope its technical identity without knowing the caller, and a tool argument or a
plain header is written by the caller. After the ADR-0011 decision, the mcp-gateway sends two headers
(`app/caller_context.py`), and only to bindings that declare `caller_context: true` in
`platform/bindings/tools/tool-bindings.yaml`: confluence, git-forge, salesforce and aap. A third-party backend
(kubernetes-mcp-server) never receives a caller's identity.

- `X-Zuno-Caller-Context`: base64url JSON with `aud` (the binding's backend name), `sub`, `groups`, `email`,
  `email_verified`, `username`, `tool` (the backend's tool name) and `iat`, all read from the validated token;
- `X-Zuno-Caller-Signature`: HMAC-SHA256 of that value, with a key derived per backend from the workload token every
  server already holds (ADR-0037): `HMAC(token, "zuno-caller-context-v1:" + backend)`.

Each server verifies it (`_verified_caller`, four identical copies, because an image is built from its own directory,
ADR-0119). The following verify as nothing: a missing, forged or tampered context, one older than 300 s or dated more
than 30 s in the future, one signed or addressed for another backend, and one minted for another tool. A server that
needs a caller then refuses. The headers are built from binding data and the validated identity only: an inbound
`X-Zuno-Caller-*` header is never forwarded (tested).

`gateway_token: false` on the five `k8s` bindings also stops X-Zuno-Gateway-Token going to kubernetes-mcp-server, which
does not check it (calls and schema reads). The workday bindings are `provider-delegated` and refused before any call,
so they send nothing. The forwarded bearer is unchanged: replacing it is lot C (ADR-0602
clause 10, token exchange or a per-call assertion). The context is narrower. It tells a server which groups and which
person to scope a call to, and nothing else.

### What was built

1. **Confluence space allowlist (M12).** `spaceAllowlist.groups` maps a Keycloak group to space-key patterns (fnmatch,
   case-insensitive, `*` for every space). Once set:
   - `create_page` and a `search_pages` that names a space are checked before Confluence is called;
   - `update_page` and `read_page` are checked on the page's own space, before the write or the return;
   - a search without a space is limited to the caller's spaces: in the CQL when they are literal keys, and always by a
     post-filter.

   - `create_page` under a `parent_id` checks that the parent is a page of the same, allowed space;
   - a refusal on a page named by id (`read_page`, `update_page`, a parent) answers "no Confluence page with id N" and
     never names the page's space;
   - the space is re-read in the PUT response of `update_page`, and a mismatch is logged as a warning. This is an
     accepted race: the PUT names the checked space and the next version, so a page moved between the GET and the PUT
     mostly fails as a version conflict, and a write that still lands elsewhere is visible in the log.

   `spaceAllowlist.scope: write` checks only the two writes.
2. **git-forge repository allowlist (M12).** `repositoryAllowlist.groups` maps a group to patterns over
   `<provider>:<owner>/<repo>`. A repository created or forked without an owner is `<provider>:@self/<name>`. Once set:
   - `write_file` and `create_repository` are checked;
   - `fork_repository` is checked on its destination (write) and its source (read);
   - reads are checked, and listings are filtered;
   - a target that is not a plain name (`..`, URL syntax) is refused, so `zuno-*` does not admit `zuno-x/../../prod`;
   - the name the provider resolved (`full_name`, `path_with_namespace`) is re-checked before a read, a write or a fork,
     because PyGithub follows the 301 of a renamed or transferred repository (and GitLab serves a moved project under
     its old path); a fork whose result lands outside the allowlist is reported as an error, naming the fork to remove.

   Patterns are fnmatch, decided deliberately: `*` matches across `/`, so `gitlab:team/*` also admits the subgroups of
   `team`. To stop at one level, list the repositories.

   `scope: write` checks only the three writes.
3. **Email recipient allowlist (M12).** `emailReport.recipientAllowlist` in the mcp-gateway chart maps a group to
   recipient patterns, on top of `internalEmailDomains`. The handler is in-process, so the groups are the validated
   token's. One recipient outside the caller's patterns refuses the whole send.
4. **Salesforce owner scoping (M12).** With `ownerScoping.enabled`, the caller is the single active Salesforce User whose
   `Email` is the token's `email` claim (from the signed context):
   - `read_opportunity` adds `OwnerId = <that user>`;
   - `create_opportunity` sets `OwnerId` to that user;
   - `update_opportunity` checks the owner by a query before the PATCH, and answers another owner's record as a missing
     one.

   The email counts only when the token's `email_verified` is `true`. The zuno realm does not set `verifyEmail` and a
   user may edit their own email, so an unverified address names nobody: such a caller is refused before any lookup.
   A caller with no email, or no single matching User, is refused. `ownerScoping.allRecordsGroups` lists the groups
   entitled to every record. `opportunity_id` is checked against the Salesforce record-id format (15 or 18
   alphanumerics) on every `update_opportunity`, scoping on or off.

   Follow-up (before owner scoping is enabled on a customer install, WP-227): map the caller by an identifier the user
   cannot edit. Either a Keycloak attribute that only an administrator can write, carried as a claim, or the Salesforce
   User's `FederationIdentifier` set to the Keycloak `sub`. In both cases, also make `email` admin-edit-only in the
   realm's user profile.
5. **Namespace matcher on `metrics.query` (M13).** `metricsQuery.namespacesByGroup` maps a group to namespaces (`*` is
   every namespace). Once set, the mcp-gateway rewrites the PromQL before it reaches mcp-k8s (`app/promql_scope.py`):
   - The query is tokenised with PromQL's lexical rules: the three string styles, comments, numbers, durations, label
     lists and the subquery colon.
   - `namespace=~"<allowed>"` is added to every vector selector: a bare name, a selector with matchers, a nameless
     `{__name__=...}`, and each alternative of a Prometheus 3 `or` inside braces.
   - Matchers are ANDed, so a caller's own `namespace` matcher can only narrow the result.
   - `info()` is refused, and so is any token PromQL would not accept.
   - A caller whose groups list no namespace is refused.

   A metric without a `namespace` label then selects nothing, which is intended. The server's ServiceAccount keeps
   `cluster-monitoring-view` (Thanos 9091 needs it); the matcher is the boundary.
6. **No per-user metric label (M15).** The ai-gateway counters (`zuno_model_calls`, `zuno_model_tokens`,
   `zuno_model_cost_usd`, the duration histogram and the two `_by_group` counters) lose `user`; `client`, `agent` and
   `group` stay. The persona moves to the span (`zuno.persona`, next to `zuno.user_sub`). The mcp-gateway counter never
   carried a user. Dashboards:
   - Usage & cost (Grafana and Perses): the `$user` variable becomes `$client`, and the "by user" panels are by client.
   - Five experiences: the `$user` variable is gone, and the "one budget" table is by group and client
     (`zuno_model_tokens_by_group_total`).

   No alert used the label. A per-person view reads Tempo or the token-budget ledger.
7. **JSON-RPC batch bound (M15).** `jsonRpc.maxBatchSize` (20; 0 is unbounded). A larger batch, or an empty one, gets one
   JSON-RPC Invalid Request object (`-32600`, `id: null`), and no message of the batch is processed.
8. **AAP launch limit (M15).** `clusterAudit.rateLimit.{launches,windowSeconds}` (2 per 900 s; 0 is no limit), per
   caller `sub` from the signed context. Calls without a verified context share one bucket (`<unverified>`), on
   purpose: changing a header never buys a fresh allowance. **The mcp-gateway must therefore roll before mcp-aap:**
   with an older gateway every caller shares that one bucket (2 launches per 15 minutes for the whole platform). A
   launch whose POST AAP refused, or that never reached AAP, does not count. Once the POST has succeeded the launch
   counts, even if the status read or the log tail after it fails. The count is in the pod (replicas 1), a restart
   resets it, and the buckets whose stamps have all expired are dropped.

New chart values (defaults in brackets):
- `mcp-gateway`: `emailReport.recipientAllowlist` (`{}`), `metricsQuery.namespacesByGroup` (`{}`),
  `jsonRpc.maxBatchSize` (`20`);
- `mcp-confluence`: `spaceAllowlist.groups` (`{}`), `spaceAllowlist.scope` (`all`);
- `mcp-git-forge`: `repositoryAllowlist.groups` (`{}`), `repositoryAllowlist.scope` (`all`);
- `mcp-salesforce`: `ownerScoping.enabled` (`false`), `ownerScoping.allRecordsGroups` (`[]`);
- `mcp-aap`: `clusterAudit.rateLimit.launches` (`2`), `clusterAudit.rateLimit.windowSeconds` (`900`).

A malformed allowlist or mapping fails closed (every caller refused). An empty one (`{}`) is off. The hardened profile
(WP-227) is where these get values; no group-to-space, repository or namespace mapping is decided here.

No change is needed in zuno-demo-agents. Optionally, the `metrics.query` description in `policies/tools/tool-policy.yaml`
can say that the gateway adds a namespace matcher to every selector, so a model does not try to widen a query that will
be narrowed anyway.

Tests (all in the CI list):
- `components/mcp-gateway/tests/test_wp225_lot_b.py` (34);
- `components/mcp-servers/confluence/tests/test_wp225_space_allowlist.py` (17);
- `components/mcp-servers/git-forge/tests/test_wp225_repository_allowlist.py` (12);
- `components/mcp-servers/salesforce/tests/test_wp225_owner_scoping.py` (12);
- `components/mcp-servers/aap/tests/test_wp225_launch_rate_limit.py` (8).

The server tests sign with the gateway's own module, so the signer and the verifiers are tested together. Every
PromQL query the matcher rewrites in the tests is re-parsed by a real parser, promql-parser 0.11.0. It is a test-only
hashed lock in `components/mcp-gateway/tests/requirements.txt`, compiled by `platform/python/compile_locks.py` and
never in the image. The test asserts that each rewritten query parses and that every vector selector (each `or`
branch included) carries the matcher. The negative
tests include:
- a space outside the caller's group is refused, with no Confluence call;
- an unsigned, forged, stale, tampered or other-tool context is refused;
- a repository outside the group, and a traversal inside an allowed prefix, are refused;
- another owner's Salesforce record is refused before the PATCH;
- PromQL escapes are neutralised or refused: a caller `namespace` matcher, `or` inside braces, a comment hiding a
  selector, a string that looks like a selector, `info()`, and malformed queries;
- a batch past the bound is refused with nothing dispatched;
- a third `cluster_audit` inside the window never reaches AAP, and a launch that failed after its POST still counts;
- an unverified email is refused for owner scoping, before any Salesforce call;
- a renamed-repository redirect (`startxfr/zuno-old` resolving to `elsewhere/prod`) is refused before any read, write
  or fork;
- an inbound `X-Zuno-Caller-*` header is not forwarded, and kubernetes-mcp-server gets neither the context nor the
  workload token;
- a Unicode digit (`²`) in a PromQL query is a scope error, not an internal error.

`test_wp190_persona.py` now pins the absence of the label. `test_mcp_protocol.py` of mcp-aap sets the limit to 0, because
it launches many times.

Limits:
- The context is as strong as the workload token: whoever holds it can sign a context. That was already true of the
  calls themselves (ADR-0037). Lot C's per-call assertion is the stronger answer.
- The other `k8s.*` reads (resources, events, logs) are still bounded by the namespaces of the mcp-k8s RoleBindings,
  not by the caller's groups.
- The launch limit and the batch bound are per pod.
- The rollout order matters: build and roll the mcp-gateway first, then the four servers. A server ahead of the gateway
  sees no context. That is harmless while every scope value is empty, but the AAP limit then uses the shared bucket.

### Live probes (each needs the five images built, a sync, and the user's go)

Roll the mcp-gateway first, then confluence, git-forge, salesforce and aap (see item 8 above for why).

1. **Defaults change nothing visible.** After the builds and the syncs: a Tekos Confluence search and a git-forge read
   still answer, `aap.platform.audit` still answers, and a `metrics.query` returns the same series as before.
   `zuno_model_calls_total` has no `user` label, while `client`, `agent` and `group` are still there. The Usage & cost
   and Five experiences dashboards render.
   kubernetes-mcp-server still answers without X-Zuno-Gateway-Token (it never checked it).
2. **Context reaches the servers.** Set `spaceAllowlist.groups: {<group>: [<a real space>]}` on the live Application,
   for a group that the tool policy allows `confluence.page.create`. A user of that group creates a page in that space,
   and the same call in another space is refused with "outside the space allowlist". Then remove the value.
3. **Repository allowlist.** With `repositoryAllowlist.groups: {<an Arkos group>: ["github:<the demo org>/<a test repo>"]}`,
   a `write_file` to that repository commits, and one to another repository of the same org is refused before GitHub is
   called (the GitHub audit log shows no request). Then remove the value.
4. **Namespace matcher.** With `metricsQuery.namespacesByGroup: {ocp-ai-ops: [zuno-ai-run]}`, `ai-ops-01` runs
   `kube_pod_info{namespace="openshift-etcd"}` and gets no series, and `kube_pod_info` returns only `zuno-ai-run` pods.
   `info(up)` is refused. Then remove the value.
5. **Batch bound.** Send a batch of 21 `ping` messages to `/mcp` with a user token. The answer is one object with
   `error.code: -32600`.
6. **AAP launch limit.** Launch `aap.cluster.audit` three times as `ai-ops-01` within 15 minutes. The third is refused
   with "rate limited", and the AAP job list shows two jobs.
7. **Salesforce owner scoping.** Waits on WP-101 (no Salesforce org is wired). With `ownerScoping.enabled` and a sandbox
   user whose email matches `sale-01`, `read_opportunity` returns only that user's records.
8. **Email allowlist.** With `emailReport.recipientAllowlist: {sales: ["sales-*@<internal domain>"]}`, a send by `sale-01`
   to `ceo@<internal domain>` answers `sent: false`. The handler is demo-mode, so nothing is sent either way.
