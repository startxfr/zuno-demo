# a2a-gateway

Serves each active agent of the admitted `zuno-demo-agents` release as an **Agent2Agent (A2A 0.3)** endpoint over JSON-RPC
(ADR-0585, WP-175). It answers with the **caller's own identity**: the model call goes through the ai-gateway and the tool calls
through the mcp-gateway, both with the caller's Keycloak token, so routing, guardrails, quota and tool policy apply to the real user.

```
GET  /agents/<agent>/.well-known/agent-card.json   public card (title, description, task names; no group names)
POST /agents/<agent>/                              message/send, message/stream, tasks/get, tasks/cancel
GET  /healthz  /readyz
```

## Rules

- A task call needs a valid token of realm `zuno` with the audience `zuno-admin-api` (every token of the `unifai` client has it).
- The caller must hold one of the agent's `zuno.access.groups` (ADR-0040); otherwise the answer is the one given for an unknown agent.
- `X-Zuno-Delegated-By` / `X-Zuno-Delegation-Depth` are verified like the mcp-gateway does (`app/agent_chain.py` is a copy of its
  module): declared targets, depth within `min(agent max_depth, corp ceiling)`, no cycle. They are passed on unchanged.
  `X-Zuno-Data-Classification` is raised to at least the agent's floor, never lowered.
- The task to run is `message.metadata.task`, else the agent's primary task.
- No onward delegation, no approval across hops (`input-required` is never raised), no credential of its own.

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `AGENTS_DIR`, `LIMITS_POLICY_PATH` | `/okf/agents`, `/okf/policies/limits/limits-policy.yaml` | the admitted release (okf-fetch init container) |
| `KEYCLOAK_ISSUER`, `KEYCLOAK_JWKS_URL`, `JWT_AUDIENCE` | see `app/auth.py` | token validation |
| `AI_GATEWAY_URL`, `MCP_GATEWAY_URL` | in-cluster services | downstream gateways |
| `PUBLIC_BASE_URL` | `http://a2a-gateway.zuno-ai-run.svc:8080` | URL written in the agent cards |
| `A2A_TOOLS_ENABLED`, `A2A_MAX_TOOL_ROUNDS` | `true`, `3` | tool loop through the mcp-gateway |

## Tests

```
cd components/a2a-gateway && python3 -m pytest tests -q
```

They drive the app with the A2A SDK client that UnifAI uses, with a fake token validator and mock transports for both gateways.

## Deployment

Chart `gitops/charts/a2a-gateway`, Applications `gitops/apps/a2a-gateway`, installed and built with the `mcp` run component
(`make d1 build mcp`, `make d1 install mcp`). ai-gateway and mcp-gateway accept this pod in their network policies.
