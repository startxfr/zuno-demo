# Observability architecture

Every Zuno service sends traces and metrics over OTLP to one OpenTelemetry collector in `zuno-monitoring`. Traces are
stored in Tempo, with a copy in OpenShift AI's own TempoStack. Metrics are scraped by the cluster's platform Prometheus
and read by Grafana through Thanos; a third Prometheus (the mesh `MonitoringStack`) holds Istio and Envoy metrics. The
gateways stamp spans with the caller's persona, the agent and the run id of the turn, so one TraceQL query finds a whole
turn (`zuno.run_id` on the Zuno services, `mas.run.id` on UnifAI spans). Counters carry labels such as provider, model,
outcome, agent and client, never a person or a run. The demonstration is the scenario
[Observability: one turn traced, every call counted](../demo/scenarios/foundation/observability-trace.md).

## HLD: where it sits

The highlighted box is "Prometheus, Grafana, Tempo". Gateways and UnifAI emit; the collector and the three metric
stores sit in the platform group.

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
  class OBS focus;
```

## LLD: how a span and a counter reach a screen

```mermaid
flowchart LR
  subgraph EMIT["Emitters"]
    UNIFAI["UnifAI multiagent, worker,<br/>RAG server, Celery, backend<br/>spans mas.session, mas.node, rag.search"]
    AIGW["ai-gateway<br/>spans model_call, guardrails_observe<br/>counters zuno.model_*"]
    MCPGW["mcp-gateway<br/>span tool_invoke<br/>counter zuno.tool_invocations"]
    A2AGW["a2a-gateway"]
    ENVOY["Envoy sidecars<br/>Telemetry mesh-default, 100 percent"]
    VLLM["vLLM local models<br/>zuno-ai-run"]
  end
  subgraph MON["namespace zuno-monitoring"]
    COL["OpenTelemetryCollector zuno-otel-collector<br/>receiver otlp: 4317 gRPC, 4318 HTTP<br/>processor batch"]
    TEMPO[("TempoMonolithic tempo<br/>Service tempo-tempo :3200<br/>PV 10Gi")]
    JUI["Tempo search UI, Jaeger<br/>route tempo-jaegerui-zuno-monitoring"]
    GRAF["Grafana, 12 dashboards<br/>route grafana-route-zuno-monitoring"]
  end
  subgraph OM["namespace openshift-monitoring"]
    PK8S["prometheus-k8s<br/>ServiceMonitor zuno-otel-collector-metrics<br/>base Service only, every 30 s"]
    THANOS["thanos-querier :9091"]
  end
  UWM["prometheus-user-workload<br/>namespaces without<br/>openshift.io/cluster-monitoring=true"]
  MESHP["MonitoringStack mesh-monitoring<br/>zuno-mesh: Istio and Envoy metrics"]
  subgraph RHM["namespace redhat-ods-monitoring"]
    RTEMPO[("TempoStack<br/>data-science-tempostack")]
    PERSES["Perses data-science-perses<br/>RHOAI and zuno-* dashboards"]
  end
  CONSOLE["OpenShift console<br/>Observe, Dashboards<br/>UIPlugin dashboards"]
  VIEWER(["ai-ops-01<br/>OpenShift sign-in; oauth-proxy:<br/>get pods in zuno-monitoring"])

  UNIFAI -.->|"traceparent, X-Zuno-Run-Id"| AIGW
  UNIFAI -.->|"traceparent, X-Zuno-Run-Id"| MCPGW
  UNIFAI & AIGW & MCPGW & A2AGW -->|"OTLP HTTP 4318"| COL
  ENVOY & VLLM -->|"OTLP gRPC 4317"| COL
  COL -->|"traces, otlp/tempo"| TEMPO
  COL -->|"traces, otlp/rhoai, gateway 8090"| RTEMPO
  PK8S -->|"scrape :8889"| COL
  PK8S & UWM --> THANOS
  GRAF -->|"datasource Prometheus"| THANOS
  GRAF -->|"datasource Mesh Prometheus"| MESHP
  GRAF -->|"datasource Tempo, TraceQL"| TEMPO
  JUI --> TEMPO
  PERSES --> THANOS
  PERSES --> TEMPO
  PERSES --> MESHP
  CONSOLE --> PERSES
  VIEWER --> GRAF
  VIEWER --> JUI
```

## Reading notes

- **Run id.** One id per turn lets Tempo answer "what did this turn cost and where did the time go" (ADR-0543); UnifAI
  emits OpenTelemetry itself and passes `traceparent` to the gateways (ADR-0566). The per-run Grafana dashboard is
  TraceQL only, because Prometheus cannot filter on an unbounded label.
- **Two dashboard surfaces.** Grafana holds twelve dashboards declared in `gitops/charts/grafana`. The same views exist as
  `PersesDashboard` objects in `gitops/charts/perses` (eleven templates), attached to the Perses instance that OpenShift
  AI already runs and placed in `redhat-ods-monitoring`; Zuno runs no Perses server of its own (ADR-0552, ADR-0553).
- **Three Prometheus instances.** `prometheus-k8s` (namespaces labelled `openshift.io/cluster-monitoring=true`),
  user-workload monitoring (the others), and the mesh stack in `zuno-mesh`. RHOAI's monitoring stack is widened to
  `zuno-ai-run` for the model targets (ADR-0554).
- **Not wired.** `zuno-aap` carries no ServiceMonitor, PodMonitor or collector in `gitops/charts/aap`,
  `aap-config` or `mcp-aap`: AAP telemetry does not reach the collector.
- Mesh tracing is sampled at 100 percent (`randomSamplingPercentage: 100` in
  `gitops/charts/service-mesh/templates/telemetry.yaml`).

## ADRs

| ADR | Status | Role here |
|---|---|---|
| [0029](../adr/0029-instrument-model-usage-costs-and-distributed-traces.md) | Implemented | Usage, cost and traces by user, agent, task, model, provider |
| [0413](../adr/0413-consolidate-grafana-dashboards-into-six-platform-views.md) | Implemented | Dashboards as platform views declared in Git |
| [0523](../adr/0523-dual-export-traces-into-the-rhoai-monitoring-stack.md) | Implemented | Copy of every trace to RHOAI's Tempo |
| [0543](../adr/0543-propagate-a-per-run-id-across-every-service-span.md) | Implemented | Run id on every service span |
| [0551](../adr/0551-add-namespace-scoped-perses-dashboards-alongside-grafana.md) | Superseded in part by 0552 and 0553 | Perses next to Grafana |
| [0552](../adr/0552-reuse-rhoais-perses-instance-instead-of-running-an-independent-one.md) | Implemented | Reuse RHOAI's Perses instance |
| [0553](../adr/0553-collocate-perses-dashboards-in-redhat-ods-monitoring-for-visibility.md) | Implemented | Dashboards in `redhat-ods-monitoring` |
| [0554](../adr/0554-widen-rhoais-monitoringstack-to-observe-zuno-ai-run.md) | Implemented | RHOAI monitoring stack observes `zuno-ai-run` |
| [0566](../adr/0566-instrument-unifai-with-opentelemetry.md) | Implemented | UnifAI emits OpenTelemetry |

Related pages: [gateways-architecture.md](gateways-architecture.md), [agent-platform-architecture.md](agent-platform-architecture.md),
[network-architecture.md](network-architecture.md).
