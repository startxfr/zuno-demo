# WP-154: tekos pilot on UnifAI, phase A (no GPU)

Measured on `demo333` on 2026-10-22, with the GPU nodes down (`NotReady`). That
removes every local model, the embedding predictor and therefore the RAG corpus.
Phase B (RAG, C3 local-only, restore drill) waits for the GPU nodes.

## What ran

| Element | Value |
|---|---|
| Stack | `zuno-unifai/unifai`, UnifAI images `devel-46b9a60f4` (fork `devel` with WP-146..149 and the team-session fix), operator 0.1.20 |
| Agent | the tekos OKF bundle, published with a throwaway cosign key as `okf-test-tekos@sha256:33d648f4...`, verified by the operator, 16 objects emitted |
| Tools | per-task `UnifaiProvider` (`spec.mcp`) to `mcp-gateway:/mcp`, the user's own JWT forwarded with `X-Zuno-Agent`/`X-Zuno-Task` |
| Models | through the ai-gateway; with the local models down the gateway falls back to the SaaS providers eligible for the classification |
| Workspace | a UnifAI team (`consultant-01..03` + `ai-ops-01`) owns the workflows; the persona selects it with `teamId` |
| Harness | `evaluations/tekos/run_scenarios.py --target unifai` and `security_checks.py --target unifai` (same `scenarios.yaml`) |
| Baseline | the same scenarios against agent-runtime tekos on the same cluster, the same day, the same GPU outage |

## Scenarios (ADR-0027, threshold 75%)

| | agent-runtime baseline | UnifAI |
|---|---|---|
| Passed | 16 / 20 (80%) | 15 / 16 (94%), 4 skipped |
| Failed | 7 timeout, 10 timeout, 11 RAG returns 0 results, 19 needs the in-cluster Kubernetes client | 8 first-token latency |

Skipped on UnifAI, not counted: 6 (no placeholder tiles), 11 (RAG source not
deployed yet), 17 (no bearer-token API: UnifAI uses a server-side session
cookie), 19 (in-cluster-only check, runs in the Day 3 evaluation Job).

Scenario 8 failed on UnifAI because the first token took 7 to 24 s, not the
6 s objective: with the local models down the gateway tries the local
providers (retries, connection errors) before the SaaS fallback. It is a
property of the outage, not of UnifAI, and is re-measured in phase B.

## Security-negative checks

11 of 12 pass.

| Check | Result |
|---|---|
| `unifai_forwards_identity_to_the_gateways` | pass: a Confluence tool call is served through the mcp-gateway, which only accepts the user's JWT |
| `unifai_ignores_a_client_supplied_identity_header` | pass: an outside `X-Authenticated-User` without a session gets 401 |
| `business_role_without_entitlement_denied_by_unifai` | pass: the workflow is not visible and the mcp-gateway answers 403 to the agent declaration |
| `unifai_tekos_never_generates_photorealistic_images` | pass: no SDXL tool call, no PNG (a diagram request takes about 80 s, with three tool calls) |
| shared-service checks (7) | pass |
| `ai_gateway_local_only_forces_local_provider` | **fail, blocked by the GPU outage**: HTTP 502, every local provider unreachable. The gateway failed closed and did not fall back to a SaaS provider, which is the safe outcome; the check needs a local model to answer. |

## Defects found and fixed

| Defect | Fix |
|---|---|
| A team workspace session ran with the team id as the acting user, so identity forwarding failed ("team sessions need a credential user") and the agent ended without output | fork `fix/team-session-credential-user` (`0a173d9c6`), generic, merged in local `devel`, with unit tests |
| `forward_user_token` LLMs were validated with the static key and produced 404s on every validation | fork `fix/openai-compatible-validator-forwarded-token` (`bbabc2144`), in the pushed `devel` |
| A non-streamed execute was dropped by the UI proxy on long answers | the harness consumes the NDJSON stream, as the UI does |
| The agent called `confluence.page.search` in a loop until `max_rounds` (found in WP-152) | not reproduced with the bundle-generated agent: it searches once or twice and answers. The loop came from the throwaway agent's prompt and from the team defect above |

## Observations to follow up

- The ReAct strategy rejects a final answer shorter than 10 characters ("Reasoning too short (5 chars, min 10)"); a one-word answer fails the turn. `min_reasoning_length` is an agent setting to expose through the bundle's `agentConfig`.
- UnifAI visibility is by owner or team workspace. A team cannot yet mean "everyone with the Keycloak group `agent_tekos`": ADR-0583 clause 1 (the `oidc-claims` directory provider, zuno-demo-59) closes that. Until then the pilot uses a hand-made team.
- UnifAI traces reach Tempo (`mas.session` with `chat auto` spans). At the first measurement the gateways did not read `traceparent`, so UnifAI and gateway traces were separate roots. The first fix (`7d44a423`, `0d0a8935`) still produced separate roots: the FastAPI dependency was a plain `def`, which runs in a worker thread on a copy of the context, so the ContextVar it set never reached the handler. Unit tests that call the function directly passed anyway. The fix (`783cb632`) makes it `async`, and the tests now go through a FastAPI app (verified to fail with the synchronous version).

## Continuous trace (WP-147 acceptance)

One Tempo trace (`7d48c3f2...`, root `unifai-multiagent-be mas.session`) now crosses every hop of a tool-using tekos turn, with the images built from `783cb632`:

| Service | Spans |
|---|---|
| `unifai-multiagent-be` | `mas.session`, `StartWorkflow:GraphTraversalWorkflow` |
| `unifai-multiagent-temporal-worker` | `RunWorkflow`, 3 `execute_graph_node`, `mas.node tekos-answer-technical-question`, 2 `mas.agent.iteration`, 2 `chat auto`, `execute_tool confluence.page.search` |
| `ai-gateway` | 2 `model_call` |
| `mcp-gateway` | `tool_invoke`, then the MCP calls `initialize`, `tools/list`, `tools/call search_pages` to the Confluence server |

## Not yet covered

C3 local-only routing, RAG answers with citations and the second-pass
idempotence, the Qdrant and Mongo restore drill, scenario 8 on healthy local
models, the quota 429 in the UI and the routing badge (WP-148 UI), the
guardrails counter (WP-153, hook still disabled), the Playwright screenshot of
the tekos chat.
