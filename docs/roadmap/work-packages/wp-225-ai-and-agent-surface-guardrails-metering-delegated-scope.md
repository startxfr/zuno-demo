# WP-225: AI and agent surface: guardrails, metering, delegated scope (delivers ADR-0602, ADR-0603)

- **State:** Operator pending (lot A, 2026-11-07); lots B and C Not started
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
(repository change 3). Lot C is the mcp-gateway, the a2a-gateway and the metrics (repository changes 4 and 5).

| Lot | Scope | State |
|---|---|---|
| A | guardrails (C7) and metering (C8) in the ai-gateway | Operator pending |
| B | space, repository and recipient allowlists; Salesforce owner scoping; namespace matcher (ADR-0603 clause 3) | Not started |
| C | token exchange or a signed assertion; REST entitlement; Dify and token-proxy callers; signed a2a chain; metrics hygiene | Not started |

## Lot A: guardrails and metering (Operator pending, 2026-11-07)

Committed locally on `wp-225-ai-surface`, cut from `wp-209-classification-floor`. Not pushed. Not live. Every switch below takes
effect only in `block` mode or when `meteredPaths.enabled` is true. The shipped values keep every class on `observe` and the
metered paths off, so a merge changes no caller. The pod template gains three always-rendered variables
(`GUARDRAILS_FAIL_CLOSED_FROM`, `GUARDRAILS_SCAN_TOOL_RESULTS`, `GUARDRAILS_STREAM_HOLD_BACK_CHARS`), so the sync rolls the pod once.

Classification is not redone here. The guardrails mode, the fail-closed threshold and the eligibility of a metered path all use
the effective level of WP-209: `app/classification_floor.py` raised by the ADR-0594 markers.

### What was built

1. **Fail closed (clause 8).** In `block`, a detector outage refuses the request with a typed `503 guardrails_unavailable`
   from `guardrails.failClosedFrom` up (`GUARDRAILS_FAIL_CLOSED_FROM`, default `C2`; empty means never). This applies to the
   prompt, the reply and a stream. C1 keeps the old fail-open behaviour. `observe` is unchanged. A classifier outage counts
   as a detector outage. A detection found by one engine still blocks when the other one failed. The routing decision
   records `blocked_by: guardrails_unavailable`.
2. **Tool results and RAG text (clause 8).** The scan covers the last user message plus the current turn's tool results and
   retrieved context. On chat that means the `tool` messages after the last user message. On Anthropic it means
   `tool_result`, `document` and `search_result` blocks. On Responses it means `*_call_output` items. A refusal names its
   stage (`prompt`, `tool_result`, `retrieved` or `reply`). System prompts and earlier turns are still not sent. An earlier
   turn's tool results were scanned in the turn that produced them. `guardrails.scanToolResults: false` restores the old
   scan.
3. **Streams (clause 8).** In `block`, `app/stream_guard.py` holds a streamed reply back until
   `guardrails.streamHoldBackChars` characters are pending (400; 0 buffers the whole reply). It checks them with a
   256-character overlap, so a pattern that straddles two segments is seen. A clean segment is released. On a detection it
   ends the stream with the protocol's error event and closes the upstream:
   - OpenAI chat: `data: {"error": ...}`, then `[DONE]`;
   - Anthropic: `event: error` with `{"type":"error","error":{...}}`;
   - Responses: `event: error`.

   `observe` streams still pass through untouched.
4. **Model-based classifier (clause 8).** `app/guardrails_classifier.py` defines one interface:
   `classify(contents) -> detections`, raising on an outage. It ships one implementation, `detectors-api`, the FMS
   Guardrails detector API that TrustyAI's Hugging Face detector runtime serves. Configuration is
   `guardrails.classifier.{type,url,detectorId,threshold}`, with `type: ""` (off) by default. No model is wired. A detection
   is named `classifier:<detection>`, and matched text is never kept. Other implementations register with
   `register(name, factory)`.
5. **Metering (clause 9).** The ai-gateway serves three paths:
   - `POST /v1/messages`, plus `/v1/messages/count_tokens`, which is forwarded unmetered;
   - `POST /v1/responses`.

   They are a metered pass-through to a local model that speaks the protocol (`app/metered_paths.py`):
   - Routing: `meteredPaths.models` maps a client model name to provider-routing entries. An entry is used only when it
     is `kind: local`, has an `endpoint`, is eligible for the effective classification and is available. A SaaS key is
     never handed to the pass-through.
   - Counting: usage goes to `zuno.model_tokens` and the token-budget ledger, as a chat call does. Anthropic usage is
     `input_tokens`, plus the cache tokens, plus `output_tokens`. Responses usage is the reply's `usage`. A stream reads
     both from the SSE events.
   - Ceiling: optional, per key (the persona), per tenant (a Keycloak group, one shared counter) or as a default
     (`meteredPaths.keyCeilings`, `app/key_ceilings.py`). `exempt` names personas or client ids that are never capped.
     Past a ceiling, the caller gets the protocol's 429 with `Retry-After`: Anthropic `rate_limit_error`, or OpenAI
     `type: tokens, code: rate_limit_exceeded`. Default `0` with no entries means no ceiling. A malformed value also means
     no ceiling: the paths are open by decision.
   - Off: with `meteredPaths.enabled: false` the paths answer 404, as today.

   The Claude Code key minted on MaaS is not touched: it calls MaaS directly, and MaaS still does not count it
   (WP-220, accepted).

New chart values, all in `gitops/charts/ai-gateway/values.yaml`:
- `guardrails.failClosedFrom` (`C2`), `guardrails.scanToolResults` (`true`), `guardrails.streamHoldBackChars` (`400`);
- `guardrails.classifier.{type,url,detectorId,threshold}` (`""`, `""`, `""`, `"0.5"`);
- `meteredPaths.enabled` (`false`), `meteredPaths.models` (`{}`), `meteredPaths.keyCeilings.{window,default,keys,tenants,exempt}`
  (`1h`, `0`, `{}`, `{}`, `[]`).

The llm role passes `zuno_ai_gateway_guardrails_fail_closed_from`, `zuno_ai_gateway_metered_paths`,
`zuno_ai_gateway_metered_paths_models` and `zuno_ai_gateway_key_ceilings`.

No change is needed in zuno-demo-agents. `guardrails-policy.yaml` names the modes and their minimum per class; the
fail-closed threshold and the scan scope are platform configuration. The corp minimum stays `observe` for every class.
Raising one to `block` is the ADR-0534 evidence decision, not part of this lot.

Tests: `tests/test_wp225_guardrails_metering.py` (33 tests, in the CI list). It includes the four required negative tests:
- an injected tool result is blocked (chat and `/v1/messages`);
- a detector outage blocks C2 and serves C1 (prompt, reply, stream, classifier);
- a mid-stream detection cuts the stream (OpenAI and Anthropic SSE);
- a key past its ceiling on `/v1/messages` is refused while an exempt key passes.

`test_guardrails.py` now pins fail-open at C1 only.

Limits:
- A gateway path is reachable in-cluster only (the ai-gateway has no Route). Giving an IDE a `/v1/messages` endpoint on the
  gateway would need a Route and a Keycloak token helper; that is not part of this lot.
- RAG text that a client puts into a system message is not scanned, because system prompts are excluded by design.
- A stream cut before its final usage event estimates the completion tokens at four characters per token.

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
6. **Ceiling.** Set `keyCeilings: {default: 1000, exempt: [<the developer persona>]}`. A second `/v1/messages` call from
   another persona returns 429 `rate_limit_error` with `Retry-After`, and the exempt persona is still served. Then reset
   `default: 0`.
