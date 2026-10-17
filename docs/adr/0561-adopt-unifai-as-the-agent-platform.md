# ADR-0561: Adopt UnifAI as the agent platform

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md), [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md), [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md), [ADR-0215](0215-carry-conversation-history-into-agent-prompts-with-budgeted-compaction.md), [ADR-0544](0544-bound-every-model-call-at-both-ends.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0569](0569-close-unifai-parity-gaps-generically.md), [ADR-0573](0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md)

## Context

Zuno's agent layer is three first-party services and one operator, all
maintained in this repository: `components/agent-runtime` (Python, FastAPI +
LangGraph, ~9.2k lines under `app/`), `components/agent-bff` (Go, standard
library only), `components/agent-frontend` (Go server + PatternFly React) and
`operator/aiagent-operator` (`AIAgent` CRD, ADR-0327/ADR-0308). Agents are OKF
bundles under `agents/<name>/`; eight exist (tekos, comage, arkos active;
advantage, finage, naveo, soursage, cognos placeholders, per each
`agent.okf.md`'s `zuno.status`). Two graph shapes serve them,
`retrieve_reason_respond` and `plan_draft_write`
(`components/agent-runtime/app/graph/shapes/`, ADR-0342).

Everything this layer does generically - sessions, streaming, history,
checkpoints, conversation lists, sharing, a chat UI - is code we own and
re-derive for every feature. ADR-0212, ADR-0215, ADR-0515 and ADR-0527 each
added a database table, runtime endpoints, BFF proxies and React components
for capabilities that agent platforms ship natively.

UnifAI (`redhat-community-ai-tools/UnifAI`, maintained as the
`startxfr/UnifAI` fork on branch `devel`, `/home/cl/ClaudeCode/startx-unifai`)
is such a platform: a multi-agent service (Flask, LangGraph or Temporal
engines, MongoDB, Redis Streams, HITL, MCP client, A2A client), a RAG service,
an admin backend, a Keycloak-backed identity service and a React UI. The fork
adds `unifai-operator` (`fork/unifai-operator/`, group
`unifai.startx.fr/v1alpha1`), which deploys a `UnifaiStack` and pushes
`UnifaiLLM`/`UnifaiProvider`/`UnifaiTool`/`UnifaiRetriever`/`UnifaiAgent`/
`UnifaiWorkflow`/`UnifaiTemplate` objects through the multi-agent REST API
(`fork/unifai-operator/README.md`). It is installed through OLM on `demo333`
(fork `MEMORY.md`, "UnifAI operator" section).

UnifAI is not an LLM gateway: its LLM elements
(`multi-agent/lib/mas/elements/llms/{openai,openai_compatible,google_genai,mock}`)
call providers directly and have no classification routing, fallback, quota
or guardrail. ADR-0560 therefore keeps `components/ai-gateway` as the policy
router in front of it. This record decides the agent layer only.

## Decision

**UnifAI, from the fork's `devel` branch, replaces `agent-runtime`,
`agent-bff` and `agent-frontend` as Zuno's agent platform.** The replacement is
staged: pilot on `demo333` with Tekos, then the remaining agents, then
`demo222`, under ADR-0573. Zuno code is removed only after the `demo222`
cutover (WP-156).

**What stays Zuno's.** The OKF bundle remains the source of truth for agent
behavior and authorization (ADR-0564 delivers it to `unifai-operator`); the
ai-gateway remains the only path to a model (ADR-0560); the MCP Gateway
remains the tool authorization point (ADR-0036, ADR-0571); Keycloak realm
`zuno` remains the identity source (ADR-0562).

**Parity is a closed list.** Every agent-runtime capability below has a named
landing place. A capability not in this list is not carried over.

| Capability today | Source | Lands in |
|---|---|---|
| Graph shapes `retrieve_reason_respond`, `plan_draft_write`; selection by `zuno.graph_shape` | `app/graph/shapes/`, ADR-0342 | Blueprint templates embedded in `unifai-operator`, instantiated per agent (ADR-0564) |
| OKF registry: prompts, `allowed_tools`, `rag.top_k`, `preferred_classification`, fail-fast load | `app/registry.py`, ADR-0039 | Operator parses and validates the bundle, emits owned objects (ADR-0564) |
| Bundle signature verification at load | `app/registry.py`, ADR-0106 | Operator verifies before emitting (ADR-0564) |
| Session persistence, resume by id, ownership re-check on resume | LangGraph Postgres checkpointer, `_resolve_run_id`, ADR-0103 | UnifAI native: `SessionRecord` in MongoDB (`multi-agent/lib/mas/session/`). Cross-user resume refusal is **unverified**; tested in the pilot |
| Conversation list, title, rename, delete | `app/conversations.py`, ADR-0212 | UnifAI native sessions. Star, drag-reorder and hard-delete are **dropped** |
| History in prompts with token budget and summary compaction, classification-aware | `app/graph/history.py`, ADR-0215 | ADR-0569 addition. UnifAI's `custom_agent` injects the last 20 workspace messages (`multi-agent/lib/mas/elements/nodes/custom_agent/custom_agent.py:208`) with no token budget and no summary |
| Prompt clamp against the narrowest local context window | `app/graph/prompt_budget.py`, ADR-0544 clauses 2-4 | Split: history budget in ADR-0569; ai-gateway's pre-flight skip (ADR-0544 clause 5) stays the backstop |
| Per-task `max_tokens` | `X-Zuno-Max-Tokens`, ADR-0544 clause 6 | Forwarded header (ADR-0563), value set by the operator from OKF (ADR-0564) |
| Project memory: extraction at checkpoint, `knowledge.project` retrieval, membership fail-closed | `app/memory.py`, `project_memory_client.py`, ADR-0209 | ADR-0569 addition (generic memory element on UnifAI storage) |
| Projects as sharing and context boundary, clone | `app/projects.py`, ADR-0527 | ADR-0569 (team workspaces and UnifAI's `multi-agent/lib/mas/sharing/cloner.py`); grant equivalence **unverified** |
| Routing headers: agent, task, request id, run id, project id, local-only, classification | `app/clients/model_router.py`, `mcp_client.py` | Templated `default_headers` on the `openai_compatible` element and MCP client (ADR-0563) |
| Caller JWT forwarded to MCP Gateway and ai-gateway | `app/auth.py`, ADR-0032 | `auth_mode: forward_user_token` (ADR-0563) |
| Classification floor per agent/task | `zuno.model.preferred_classification` | Derived from OKF, raise-only per session (ADR-0565) |
| Per-turn escalation from retrieved docs and tool results; `local_only_required` from MCP Gateway's `allow_context` verdict | `retrieve_node`, `tool_call_node`, ADR-0034 | Session-level, raise-only classification (ADR-0565 clause 3), raised by a RAG source's declared classification. Raising from tool results needs metadata that does not reach MAS yet. Until then, the bundle declares the worst case statically (ADR-0565 clause 6) |
| Model routing, fallback, per-agent preferences, LoRA | ai-gateway | ai-gateway, unchanged (ADR-0560) |
| Routing metadata in the UI | ADR-0550 clause 9, `web/src/chat/types.ts` | ADR-0569 addition (UI reads `/v1/routing-decisions/{id}`) |
| Quota exhaustion shown to the user | ai-gateway 429 (`app/main.py:292`) | ADR-0569 addition (clean 429 UX) |
| Streaming: token deltas, tool status, done/error, correlation, cancellation | SSE chain, ADR-0045 | UnifAI native NDJSON stream from a Redis channel (`multi-agent/adapters/inbound/flask/endpoints/sessions.py`, `multi-agent/lib/mas/session/execution/foreground_runner.py`). Correlation via ADR-0563's run id header. Citation rendering **unverified** |
| Tool trigger heuristic (`should_call_tools` regex) | `nodes.py` | **Dropped**: the agent node's LLM tool-calling decides |
| Product-version and language pre-ranking filters | `_extract_product_version`, `_detect_language` | **Dropped** from the agent layer; RAG ranking is ADR-0568's |
| Observe-only TrustyAI guardrails | `app/clients/guardrails_client.py`, ADR-0534/0540 | ai-gateway (ADR-0567) |
| Traces | `app/telemetry.py` | UnifAI OpenTelemetry (ADR-0566) |
| Agent entitlement `agent_<name>` | agent-bff, ADR-0040 | Operator maps OKF `access.groups` to UnifAI visibility (ADR-0564). If UnifAI cannot gate a workflow by Keycloak group, ADR-0569 adds it. MCP Gateway and ai-gateway still enforce server-side with the forwarded JWT |
| Agent tiles and cross-agent navigation | `internal/portal`, ADR-0515 | UnifAI agent repository (ADR-0569) |
| HITL approvals | none generic today | UnifAI native HITL (`foreground_runner.py:_build_hitl`) |

## Planned supersession

At cutover (WP-156), per `docs/adr/README.md` "How a decision changes":

- **In full by this ADR:** ADR-0008 (one frontend and BFF per agent), ADR-0039
  (its clauses migrate into ADR-0564), ADR-0044 (PatternFly frontend),
  ADR-0045 (SSE chain), ADR-0054 (BFF OpenAPI contract), ADR-0103 (LangGraph
  Postgres checkpoints), ADR-0212 (conversations database), ADR-0342 (shapes
  migrate into ADR-0564's blueprint templates), ADR-0515 (tabs and tiles).
- **In part by this ADR:** ADR-0322, only the "Zuno Agent Runtime ->
  LangGraph" branch of its integration boundary (the RAG-provider branch is
  ADR-0568's); ADR-0544, clauses 2-4 (the agent-runtime clamp). Clauses 1 and
  5-8 remain the gateway's.
- **By sibling ADRs:** ADR-0209 and ADR-0215 (full) and ADR-0527 (in part) by ADR-0569; ADR-0308,
  ADR-0327, ADR-0350 and others by ADR-0564; ADR-0534/0540 by ADR-0567.
- **Not superseded:** ADR-0007 (still satisfied; its namespace list gets a
  dated correction note), ADR-0009 (amended by ADR-0560), ADR-0329 (dated
  correction note), ADR-0550 clause 9 (ADR-0569 is its new implementation).
  ADR-0018, ADR-0213 and ADR-0505 are already superseded; nothing changes.

## Consequences

Zuno stops owning a chat UI, a BFF, a session store and a graph runtime. Every
generic feature listed above comes from upstream or from a generic fork change
proposed upstream (ADR-0575). Zuno keeps only what is specific: OKF, the
gateway policy and the tool authorization.

Three properties get weaker, and this record accepts each one:

- Escalation from tool results becomes a static over-classification until
  ADR-0565 clause 6's metadata path exists. Escalation also becomes per
  session instead of per turn.
- Star, reorder and hard-delete of conversations disappear.
- The per-agent frontend Route (ADR-0008) becomes one shared UI.

The fork becomes a dependency with its own rebase cost on upstream `main`
(ADR-0575).

## Security considerations

Today the BFF re-validates the JWT and enforces `agent_<name>` before any call.
In UnifAI, internal services trust an `X-Authenticated-User` header set behind
the identity service (`fork/unifai-operator/README.md`, NetworkPolicy
section). Server-side authorization therefore rests on the downstream
gateways, which see the caller's own JWT only once ADR-0563 is in place. No
agent is cut over before ADR-0563 is in place.

The interim loss of tool-result escalation must never widen SaaS
eligibility. ADR-0565 clause 6 makes the bundle declare the worst case of any
tool source the task can reach, and the gateway enforces that floor
independently (ADR-0565 clause 5). Credentials stored
by UnifAI are Fernet-encrypted in MongoDB with a key the operator generates
once (`unifai-generated`, `CREDENTIAL_ENCRYPTION_KEY`). Losing it makes stored
credentials unreadable, so it is backed up with ADR-0568's Day-3 tier.

## Operational considerations

The pilot (ADR-0573) must test each **unverified** row of the parity table
explicitly: cross-user session resume refused, citation rendering, group-gated
agent visibility, team-workspace grants. A row that fails moves to ADR-0569 or
blocks cutover. It is never dropped silently.

The two stacks run side by side until WP-156. `evaluations/<agent>/`
scenarios, including `chat_first_token_latency` (`max_seconds: 6`), are
re-pointed at UnifAI's session API, and a regression there blocks cutover.
