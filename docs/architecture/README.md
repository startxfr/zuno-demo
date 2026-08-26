# Architecture Documentation

The architecture documentation is intentionally split into complementary views.

- `functional-architecture.md` - users, agents, tasks, and business capabilities.
- `logical-architecture.md` - reusable platform services and responsibilities.
- `physical-architecture.md` - OpenShift deployment boundaries and namespaces.
- `security-architecture.md` - identity, policy, secrets, network, and data classification.
- `data-architecture.md` - business data, vector data, memory, and document context.
- `ai-architecture.md` - OpenShift AI, model serving, RAG, evaluation, and inference governance.
- `identity-architecture.md` - Keycloak, Google federation, delegated OAuth, and identity propagation.
- `network-architecture.md` - routes, service paths, NetworkPolicies, and controlled egress.
- `sequence-flows.md` - representative runtime sequences.

## Baseline logical flow

```mermaid
flowchart LR
    U[User] --> FE[Agent Frontend]
    FE --> BFF[Agent BFF]
    BFF --> RT[Agent Runtime]
    RT --> MCPG[MCP Gateway]
    MCPG --> MCP[MCP Servers]
    RT --> AIGW[AI / Inference Gateway]
    AIGW --> LOCAL[Local models on OpenShift AI]
    AIGW --> SAAS[SaaS model providers]
    RT --> RAG[RAG / pgvector]
    KC[Keycloak] -. identity and policy .-> FE
    KC -. identity and policy .-> BFF
    KC -. authorization .-> RT
    V[Vault] -. secrets .-> RT
    V -. secrets .-> AIGW
```
