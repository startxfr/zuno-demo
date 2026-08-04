# Security Architecture

Security is based on explicit identity propagation, least privilege and policy intersection.

```mermaid
flowchart LR
  USER[User] --> KC[Keycloak]
  USER --> FE[Frontend]
  FE --> BFF[BFF]
  BFF --> RT[Agent Runtime]
  RT --> MCP[MCP Gateway]
  RT --> AI[AI Gateway]
  RT -. revalidate .-> KC
  MCP -. user and service identity .-> TOOLS[Authorized Tools]
  AI --> VAULT[Vault]
```

Effective authorization combines:

`agent definition ∩ user/group rights ∩ task rights ∩ data classification ∩ platform policy`.

C3 content never leaves local inference. C2 content may use external models only after the relevant context restrictions are satisfied.
