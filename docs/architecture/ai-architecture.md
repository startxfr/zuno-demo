# AI Architecture

Red Hat OpenShift AI 3.5 is the primary AI platform. The design separates agent orchestration (UnifAI, see [agent-platform-architecture.md](agent-platform-architecture.md)) from inference governance (the ai-gateway, see [gateways-architecture.md](gateways-architecture.md)). This page covers what sits behind the gateway: model roles, serving, MaaS, external models, evaluation and the OpenShift AI tools around them. Training and the registry are in [mlops-architecture.md](mlops-architecture.md).

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
  class KSERVE focus;
```

## Model roles

`platform/ai-gateway/provider-routing.yaml` declares 14 providers, each with a `role`, the data levels it may serve (`eligible_for`), a timeout and, for local models, the `inference_service` whose readiness the gateway watches. Each local model has two entries: through MaaS first, then direct.

| Role | Model | Where | Levels |
|---|---|---|---|
| `default` | qwen3.5-9b, fleet-wide default ([ADR-0531](../adr/0531-promote-qwen3-5-9b-as-the-fleet-wide-default-and-extend-ovhcloud-reasoning-access.md)) | local | C1 to C3 |
| `quality` | qwen3.6-27b-instruct ([ADR-0518](../adr/0518-modernize-local-models-qwen36-chat-qwen3-embeddings-qwen35-training.md)) | local | C1 to C3 |
| `reasoning` | gpt-oss-20b ([ADR-0414](../adr/0414-consolidate-zuno-ai-run-into-three-tiered-mig-predictors.md)) | local | C1 to C3 |
| `specialized` | qwen3.5-9b-wesh, French urban register ([ADR-0526](../adr/0526-fine-tune-and-serve-a-french-urban-register-model-variant.md)) | local | C1 to C3 |
| `code` | Mistral Codestral ([ADR-0417](../adr/0417-consume-codestral-via-mistral-api.md)) | SaaS | C1, C2 |
| `reasoning-external` | gpt-oss-120b on OVHcloud | SaaS | C1, C2 |
| `general-external` | OpenAI, Gemini, Anthropic, Mistral | SaaS | C1 or C1, C2 |

The embedding model `qwen3-embedding-0.6b` (1024 dimensions) serves RAG. Which provider answers is decided per agent and task by the gateway, not by the model list. C3 never leaves the cluster ([ADR-0021](../adr/0021-route-models-according-to-c1-c2-c3-classification.md)). Which models a given persona may reach is set by the OKF release.

## Local serving

Local chat models are `LLMInferenceService` objects (KServe with llm-d) on MIG slices of RTX PRO 6000 96 GB GPUs ([ADR-0351](../adr/0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md), [ADR-0537](../adr/0537-integrate-rhoai-hardware-profiles-and-maas-external-models.md)). Weights are staged in the shared S3 bucket `zuno-demo-sources` ([ADR-0546](../adr/0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md)). Only gpt-oss-20b is autoscaled, through `spec.scaling` with minimum and maximum 1 ([ADR-0542](../adr/0542-autoscale-one-served-model-through-llminferenceservice-spec-scaling.md)). A burst node (full GPU, tainted, scale from zero) is for training only.

```mermaid
flowchart LR
  AIGW["ai-gateway<br/>MaaS entry first"] --> GW
  KEY["MaaS key or OpenShift token<br/>developers, Lightspeed"] --> GW
  AIGW -->|"direct fallback"| SVC
  subgraph ING["openshift-ingress"]
    GW["Gateway maas-default-gateway<br/>Kuadrant AuthPolicy and<br/>TokenRateLimitPolicy"]
  end
  subgraph RUN["zuno-ai-run, GPU ResourceQuota"]
    LLMISVC["LLMInferenceService<br/>model.uri, MIG resources, vLLM args"]
    ROUTE["HTTPRoute<br/>per model"]
    SVC["Service workload :8000"]
    POD["Deployment<br/>storage-initializer: S3 to emptyDir<br/>vLLM with warm-up, istio-proxy"]
    EPP["llm-d scheduler EPP<br/>InferencePool"]
    SO["ScaledObject and HPA<br/>gpt-oss-20b only"]
    EMB["InferenceService embeddings<br/>vllm-embedding-runtime"]
  end
  GW --> ROUTE --> SVC --> POD
  ROUTE -.-> EPP
  LLMISVC -. "KServe controller" .-> ROUTE & POD & EPP
  SO -. replicas .-> POD
  S3[("S3 zuno-demo-sources<br/>models/served-name")] --> POD & EMB
  HWP["HardwareProfiles<br/>mig-1g-24gb, mig-2g-48gb"] -. nodeSelector .-> POD
  subgraph GPU["MachineSet zuno-gpu-a<br/>2 nodes, RTX PRO 6000, MIG all-balanced"]
    NA["node A<br/>1g.24gb and 2g.48gb slices"]
    NB["node B<br/>1g.24gb and 2g.48gb slices"]
  end
  POD --> NA & NB
  EMB --> NA
  BURST["MachineSet zuno-gpu-burst-a<br/>MIG off, tainted, 0 to 1<br/>training only"]
  CAS["ClusterAutoscaler,<br/>MachineAutoscaler"] -. "scale from zero" .-> BURST
```

## MaaS and external models

MaaS is the access plane: `maas-default-gateway` (Authorino key or TokenReview check, Limitador token limits), the portal for API keys, and the CRs `MaaSSubscription`, `MaaSAuthPolicy` and `MaaSModelRef` ([ADR-0201](../adr/0201-complete-the-openshift-ai-maas-governance-plane-integration.md)). All local traffic of the ai-gateway goes through it ([ADR-0521](../adr/0521-route-local-model-traffic-through-maas.md)); keys, per-subscription limits and exposure belong to MaaS, per-persona budgets stay in the ai-gateway ([ADR-0570](../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md)).

Mistral and OVHcloud gpt-oss-120b are also published as MaaS `ExternalModel` objects ([ADR-0541](../adr/0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md)). The ai-gateway still calls the chat SaaS providers directly, with its own keys, as a named exception of ADR-0570; the MaaS path is proven and not switched on (`MAAS_EXTERNAL_EGRESS_ENABLED=false`).

```mermaid
flowchart LR
  DEV["Browser<br/>/maas-consumer-portal"] --> KAP
  CLI["curl, SDK, IDE<br/>Bearer sk-oai-..."] --> GWY
  subgraph PORTAL["portal: OpenShift AI namespaces"]
    KAP["kube-auth-proxy<br/>OpenShift OAuth"] --> UI["maas-consumer-portal"] --> API["maas-api<br/>mint, list, revoke keys"]
  end
  subgraph GATEWAY["maas-default-gateway, openshift-ingress"]
    GWY["listeners"] --> AUTH["AuthPolicy<br/>sk-oai key or TokenReview"] --> TRLP["TokenRateLimitPolicy<br/>tokens per user, per subscription"]
  end
  API -. "key validation" .-> AUTH
  SUB["MaaSSubscription<br/>group, model, tokens per hour"] -.-> TRLP
  MAP["MaaSAuthPolicy<br/>model-entitlement"] -.-> AUTH
  REF["MaaSModelRef<br/>one per model"] -.-> GWY
  TRLP --> LLM["LLMInferenceService<br/>local models"]
  TRLP --> EXTM["ExternalModel<br/>mistral-large, gpt-oss-120b-ovhcloud"]
  AIGW["ai-gateway service account<br/>subscription 1M tokens per hour"] --> GWY
  AIGW -->|"direct, own keys, in use"| SAAS["SaaS providers"]
  EXTM --> SAAS
```

## OpenShift AI tools

- **GenAI playground.** A ready-made OGX server (`OGXServer`, [ADR-0322](../adr/0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md), Superseded in part by ADR-0561 and ADR-0568) in `zuno-playground`: chat goes to MaaS under the person's subscription, uploaded documents go to a small dedicated pgvector, tools go to the mcp-gateway `/mcp` front door with the person's OpenShift token. It is an operator tool, not an end-user experience ([ADR-0587](../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)). Zuno's own RAG is on Qdrant, see [data-architecture.md](data-architecture.md).
- **Lightspeed.** OpenShift Lightspeed is a consumer: inference through MaaS (provider `rhoai_vllm`, subscription `gpt-oss-20b-lightspeed`), official documentation untouched, Zuno tools through the mcp-gateway, per-user identity ([ADR-0524](../adr/0524-integrate-openshift-lightspeed-with-the-zuno-ai-platform.md)).
- **Evaluation.** TrustyAI runs RAGAS, Garak and LM-Eval, and EvalHub gives a self-service path; guardrails moved out of TrustyAI into the ai-gateway ([ADR-0534](../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md), Superseded in part by [ADR-0567](../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md)). Detail in [mlops-architecture.md](mlops-architecture.md).
- **Platform CRDs.** Kueue, JobSet and LeaderWorkerSet are installed as charts (`kueue`, `jobset`, `lws`); the `DataScienceCluster` carries notebooks, pipelines, KServe, the model registry and OGX.

```mermaid
flowchart LR
  USER["Browser<br/>ai-ops, ai-dev"] --> UI["maas-consumer-portal<br/>Playground: Model, Knowledge, MCP"]
  UI --> BFF["dashboard gen-ai backend"]
  BFF --> OGX["OGXServer<br/>zuno-playground"]
  OGX -->|"passthrough provider,<br/>person's subscription"| GW["maas-default-gateway"] --> LLM["gpt-oss-20b<br/>LLMInferenceService"]
  OGX -->|"upload, embed"| PGV[("genai-pgvector")]
  OGX -->|"user's OpenShift token"| FD["mcp-gateway /mcp<br/>TokenReview, group policy"] --> SRV["MCP servers"]
  LS["Lightspeed app server"] -->|"SA token, rhoai_vllm"| GW
  LS -->|"user's OpenShift token"| FD
  LS --> DOCS["lightspeed-rhokp<br/>OpenShift docs"]
```

Scenarios: [model serving with llm-d and MIG](../demo/scenarios/rhoai/model-serving-llmd-mig.md), [external models](../demo/scenarios/rhoai/external-models.md), [MaaS portal and API keys](../demo/scenarios/rhoai/maas-portal-api-keys.md), [GenAI playground](../demo/scenarios/rhoai/genai-playground.md), [Lightspeed](../demo/scenarios/experiences/lightspeed.md), [evaluation](../demo/scenarios/rhoai/evaluation-trustyai-evalhub.md).
