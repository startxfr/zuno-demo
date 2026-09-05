# Logical Architecture

```mermaid
flowchart TB
    U[User] --> FE[Agent Frontend]
    FE --> BFF[Agent BFF]
    BFF --> RT[Shared Agent Runtime]
    RT --> AIGW[AI / Inference Gateway]
    RT --> MCPGW[MCP Gateway]
    RT --> RAG[RAG Service]
    MCPGW --> MCP1[Sales DB MCP]
    MCPGW --> MCP2[Confluence MCP]
    MCPGW --> MCP3[Google Workspace MCP]
    MCPGW --> DR[Diagram Render]
    RAG --> VDB[(PostgreSQL + pgvector)]
    AIGW --> LOCAL[OpenShift AI Local Models]
    AIGW --> SAAS[Approved SaaS Models]
    FE -. authentication .-> KC[Keycloak]
    BFF -. identity .-> KC
    RT -. authorization .-> KC
    AIGW -. secrets .-> VAULT[Vault]
```

Dedicated frontends/BFFs are instantiated per agent; runtime, AI gateway and MCP gateway are shared platform services. The PostgreSQL + pgvector target is an HA cluster (see `docs/architecture/data-architecture.md`), not a single instance.

![Redis Low Level Design](../assets/img/zuno-lld-redis.png)

A single shared Redis instance (in `zuno-auth`) serves two distinct roles: the server-side opaque session/token store behind the BFFs (ADR-0042), and the AI Gateway's controlled semantic response cache (ADR-0104).
