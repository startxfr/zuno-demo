# Gateways Architecture

Every experience reaches models and tools through gateways that own policy. The experiences never choose a provider or call a tool server directly. This page covers the gateways and the model-access plane behind them. The agents and the A2A gateway are in [agent-platform-architecture.md](agent-platform-architecture.md).

The highlighted box is the ai-gateway. Plain arrows carry requests, dotted arrows carry identity, policy or telemetry.

```mermaid
flowchart TB
  subgraph EXP["Experiences: clients of one governed backend"]
    UNIFAI["UnifAI<br/>agents, RAG"]
    OWUI["Open WebUI"]
    CLAW["OpenClaw<br/>one assistant per persona"]
    DIFY["Dify"]
    KAGENT["kagent"]
    LS["OpenShift Lightspeed"]
    BLENDER["Blender add-on"]
    WM["World model"]
  end
  subgraph GOV["Gateways and governance"]
    TP["token proxy,<br/>egress proxy"]
    RHCL["RHCL Kuadrant<br/>auth, rate limits"]
    AIGW["ai-gateway<br/>classification, routing,<br/>guardrails, quotas"]
    MCPGW["mcp-gateway<br/>tools by group"]
    A2A["a2a-gateway<br/>delegation, approval"]
  end
  subgraph AI["Red Hat OpenShift AI"]
    MAAS["MaaS<br/>gateway, portal, API keys"]
    KSERVE["KServe llm-d<br/>local models on MIG GPUs"]
    EXT["SaaS models<br/>Mistral, Codestral, OVHcloud"]
    PG["GenAI playground"]
    BUILD["Pipelines, MLflow,<br/>Kueue, model registry"]
    EVAL["TrustyAI, EvalHub,<br/>LMEval"]
  end
  subgraph TOOLS["Agents and tools"]
    OKF["OKF agents release<br/>zuno-demo-agents"]
    MCPS["MCP servers<br/>Confluence, Git, AAP,<br/>k8s, Google Workspace"]
  end
  subgraph TRUST["Identity, secrets, supply chain"]
    KC["Keycloak<br/>personas, groups"]
    VAULT["Vault, ESO,<br/>cert-manager"]
    SC["RHTAS, Quay,<br/>image policy"]
  end
  subgraph PLAT["Platform and operations"]
    OCP["OpenShift, Service Mesh,<br/>GPU nodes"]
    GITOPS["Argo CD GitOps,<br/>AAP Day 0-3"]
    OBS["Prometheus, Grafana,<br/>Tempo"]
  end
  SAAS[("SaaS<br/>Confluence, Google,<br/>Salesforce")]

  UNIFAI & OWUI & WM --> AIGW
  CLAW & DIFY & KAGENT --> TP --> AIGW
  BLENDER --> RHCL --> AIGW
  UNIFAI --> A2A
  UNIFAI & OWUI & TP & LS --> MCPGW
  LS & PG --> MAAS
  AIGW --> MAAS
  MAAS --> KSERVE
  AIGW --> EXT
  MAAS -. published .-> EXT
  MCPGW --> MCPS --> SAAS
  BUILD --> KSERVE
  EVAL --> MAAS
  RHCL -. limits .-> MAAS
  OKF -. agents, policies .-> UNIFAI & AIGW & MCPGW
  KC -. tokens .-> AIGW & MCPGW & MAAS
  AIGW & MCPGW -. metrics, traces .-> OBS

  classDef focus fill:#ffd54f,stroke:#d84315,stroke-width:4px,color:#000;
  class AIGW focus;
```

## What each gateway owns

- **ai-gateway** (`zuno-ai-run`) is the policy router in front of the models ([ADR-0560](../adr/0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md)). It derives the data level (C1, C2, C3) from the OKF floor and tool markers, and the level can only rise ([ADR-0565](../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)). It orders the candidate providers by the `preferred` and `fallback` lists of each agent and task, and it skips local models that are not Ready and providers that just failed ([ADR-0591](../adr/0591-route-only-to-ready-local-models-and-fail-fast-on-stalled-candidates.md)). It never reads the question: the task decides.
- **Guardrails** run inside the ai-gateway ([ADR-0567](../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md)). The mode (`off`, `observe`, `block`) is set per effective level; every level ships as `observe`. The detector is NeMo Guardrails with pattern rails and no model ([ADR-0540](../adr/0540-express-guardrail-policy-as-nemo-rails-configuration.md)).
- **Quotas** are a per-persona and per-group token ledger in the ai-gateway. It is in-process by default and Redis-backed when `quotaLedger.store` is `redis`, which two replicas need ([ADR-0593](../adr/0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md)). MaaS keeps the per-subscription limits ([ADR-0570](../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md)).
- **MaaS** is the access plane in front of the local models: gateway, portal, API keys ([ADR-0201](../adr/0201-complete-the-openshift-ai-maas-governance-plane-integration.md), [ADR-0521](../adr/0521-route-local-model-traffic-through-maas.md)). Details are in [ai-architecture.md](ai-architecture.md).
- **mcp-gateway** is the one door to MCP tools ([ADR-0010](../adr/0010-introduce-a-central-mcp-gateway.md)). A call passes only if the person's groups, the agent, the task, the tool policy and the data level all allow it ([ADR-0036](../adr/0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)), and the result carries a signed classification marker ([ADR-0594](../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md)).

## LLD: decisions of the ai-gateway for one call

Adapted from the routing, sovereignty, guardrails and quotas scenarios (Appendix B of each), drawn from `components/ai-gateway/app/*` and `gitops/charts/ai-gateway`. The stage order is the one of the scenario diagrams.

```mermaid
flowchart TB
  REQ["POST /v1/chat/completions<br/>token + X-Zuno-Agent, X-Zuno-Task,<br/>X-Zuno-Data-Classification"]
  subgraph GW["ai-gateway pod, namespace zuno-ai-run"]
    ID["1. Persona and quota class<br/>ledger check: group, then persona<br/>429 quota_exceeded when spent"]
    LEVEL["2. Effective level<br/>max of header, OKF floor, client floor,<br/>signed tool markers"]
    MODE["3. Guardrails mode<br/>strictest of level, corp minimum, agent<br/>block: prompt checked before routing"]
    CAND["4. Candidates<br/>eligible_for holds the level, local only if required,<br/>preferred then fallback order"]
    READY["5. Availability<br/>skip not Ready models,<br/>circuit breaker 60 s"]
    CALL["6. Call, no SDK retry<br/>180 s through MaaS, 60 s direct"]
    REC["7. Record and consume<br/>span, metrics, routing decision,<br/>tokens added to the ledger"]
    OBS["8. Observe check<br/>after the answer, fire and forget"]
    E503["503 at once<br/>no eligible provider"]
  end
  POL[("ConfigMaps from the OKF release<br/>model-routing, classification floors,<br/>guardrails modes, quota budgets")]
  PR[("ConfigMap zuno-provider-routing<br/>14 providers: role, eligible_for,<br/>inference_service, timeout")]
  LIS[("LLMInferenceService status")]
  REDIS[("Redis zuno-redis-master, zuno-auth<br/>ledger, routing decisions 120 s")]
  NEMO["NeMo Guardrails<br/>zuno-guardrails"]
  MAAS["MaaS gateway<br/>local models, C1 to C3"]
  SAAS["SaaS providers, direct<br/>C1, C2 only"]
  REQ --> ID --> LEVEL --> MODE --> CAND --> READY
  READY -- "none left" --> E503
  READY --> CALL --> REC --> OBS
  CALL --> MAAS
  CALL --> SAAS
  POL -.-> ID & LEVEL & MODE & CAND
  PR -.-> CAND
  LIS -.-> READY
  REDIS -.-> ID
  REC -.-> REDIS
  MODE -.-> NEMO
  OBS -.-> NEMO
```

## LLD: alternative gateways

[ADR-0619](../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md) (Accepted) runs other AI gateways in `zuno-ai-gateways` so the same clients can be shown on another road. The Zuno ai-gateway stays the default for every demo. LiteLLM ([ADR-0621](../adr/0621-run-litellm-as-an-alternative-ai-gateway.md)), Agent Router ([ADR-0622](../adr/0622-run-agent-router-as-an-alternative-ai-gateway.md)) and Bifrost ([ADR-0623](../adr/0623-run-bifrost-as-an-alternative-ai-gateway.md)) are Proposed. None of the four carries the signed delegation chain, OKF bundles, classification floors that only rise, or per-(agent, task) policy. Those stay in the Zuno gateways. Praxis has a chart in `gitops/charts/praxis`.

```mermaid
flowchart LR
  subgraph CLIENTS["experience clients"]
    OWUI["Open WebUI<br/>connections: Zuno, Praxis"]
    KAG["kagent, Dify, OpenClaw"]
    OTHER["UnifAI, Blender,<br/>world model"]
  end
  TP["zuno-token-proxy<br/>routes /v1 and /alt/praxis/v1"]
  subgraph RUN["zuno-ai-run: default road"]
    AIGW["ai-gateway<br/>quota ledger, floors, markers,<br/>per-agent policy"]
  end
  subgraph ALT["zuno-ai-gateways: alternative road"]
    PRAX["Praxis<br/>verifies the zuno JWT"]
    FUT["LiteLLM, Agent Router, Bifrost<br/>proposed"]
  end
  KC["Keycloak realm zuno"]
  MODELS["local models through MaaS"]
  TEMPO["Tempo, Prometheus"]
  OWUI -->|"user token"| AIGW
  OWUI -->|"user token"| PRAX
  OTHER -->|"user token"| AIGW
  OTHER -->|"user token"| PRAX
  KAG --> TP
  TP -->|"client token"| AIGW
  TP -->|"client token"| PRAX
  AIGW --> MODELS
  PRAX --> MODELS
  FUT -.-> MODELS
  KC -. "tokens, JWKS" .-> AIGW & PRAX & TP
  AIGW & PRAX -. "traces, metrics" .-> TEMPO
```

Scenarios: [AI gateway routing](../demo/scenarios/governance/ai-gateway-routing.md), [sovereignty](../demo/scenarios/governance/ai-gateway-sovereignty.md), [guardrails](../demo/scenarios/governance/guardrails.md), [quotas](../demo/scenarios/governance/quotas.md), [MCP tools by group](../demo/scenarios/governance/mcp-tools-by-group.md), [multi-gateway](../demo/scenarios/governance/multi-gateway.md), [agents on an alternative gateway](../demo/scenarios/governance/agents-alt-gateway.md).
