# Shared Components

Reusable software components are separated from agent definitions so a new agent can be onboarded without duplicating platform code.

Since WP-156 the agents are served by UnifAI (ADR-0561), deployed from the
admitted zuno-demo-agents release (ADR-0580); the zuno agent stack that used
to live here (`agent-runtime`, `agent-bff`, `agent-frontend`, and
`operator/aiagent-operator`) was retired. What remains:

| Component | Role |
|---|---|
| `ai-gateway` | AI Inference Gateway: policy router in front of MaaS and the external providers (ADR-0009, ADR-0560), guardrails hook (ADR-0567). |
| `mcp-gateway` | MCP Gateway: tool authorization and invocation (ADR-0036), with the `mcp-servers/*` it fronts. |
| `diagram-render` | Self-hosted Mermaid rendering behind mcp-gateway's diagram tool (ADR-0516). |
| `mlops` | Training/evaluation pipeline (ADR-0302). |
| `trustyai-eval` | RAGAS evaluation image (ADR-0534). |
| `world-model-web` | The world-model browser API (identity, GPU lease, prompt screening and enhancement, stream relay) and its React + PatternFly UI (ADR-0604). |
| `world-model-runtime` | The world-model GPU runtime (ADR-0604): FLUX.2 klein for the first image and world edits, Waypoint-1.5 for the interactive frames, H.264 (NVENC or x264) for the browser; CPU mock adapters for tests. |
| `zuno-token-proxy` | Gives an experience client that cannot forward a user token (Dify, kagent) a refreshed client-credentials token towards the two gateways (ADR-0601). |
| `zuno-dify-knowledge` | Dify External Knowledge API (`POST /retrieval`) over the mcp-gateway `knowledge.tech.search` tool, through the token proxy; no store (ADR-0599, WP-205). |
| `supply-chain-signer` | In-cluster image signing identity (ADR-0420, ADR-0535). |
| `aap-execution-environment` | Custom AAP execution environment (ADR-0418). |
