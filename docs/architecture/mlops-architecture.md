# MLOps Architecture

Last reviewed: 2026-11-19

The MLOps path turns a dataset into a served, evaluated model. KFP orchestrates, a Kubeflow TrainJob does the GPU work, MLflow tracks the run, an evaluation gate decides, and a human-reviewed Git change promotes the result to serving. The serving side is in [ai-architecture.md](ai-architecture.md).

The highlighted box groups the build tools: pipelines, MLflow, Kueue and the model registry.

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
  class BUILD focus;
```

## Building blocks

- **Pipeline.** A KFP pipeline in `zuno-mlops` (DSPA `mlops-dspa`, metadata in MariaDB) runs prepare-dataset, train-lora, evaluate and push-registry; comage adds a merge-export step ([ADR-0302](../adr/0302-build-dataset-to-model-mlops-pipelines.md), Superseded in part by ADR-0526).
- **Training.** The train step only submits a TrainJob to a namespaced TrainingRuntime and polls it ([ADR-0539](../adr/0539-delegate-lora-training-compute-to-a-kfp-submitted-trainjob.md)). The job lands on a tainted burst GPU MachineSet that scales from zero ([ADR-0351](../adr/0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)).
- **Tracking.** MLflow in `redhat-ods-applications` records parameters, loss and the gate result; tracking never fails a run ([ADR-0538](../adr/0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)).
- **Queues.** Kueue (Red Hat build, [ADR-0321](../adr/0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md)) admits the evaluation Jobs; TrainJobs are not admitted by it today.
- **Serving a fine-tune.** An adapter reaches the base model through a reviewed change to `loraAdapters` ([ADR-0301](../adr/0301-introduce-lora-and-peft-model-customization.md)). The French fine-tune is served as merged weights, as its own model ([ADR-0526](../adr/0526-fine-tune-and-serve-a-french-urban-register-model-variant.md)).
- **Registry.** push-registry writes to the Model Registry only after the gate passes. The catalog and registry pages run in the RHOAI dashboard; the scenario records that demo333 had no registry instance on 2026-11-16.
- **Evaluation.** Acceptance gates (20 scenarios, 75 percent, [ADR-0027](../adr/0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md), [ADR-0028](../adr/0028-require-a-seventy-five-percent-evaluation-threshold.md)), Garak, RAGAS, LM-Eval and EvalHub ([ADR-0534](../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md)).

## LLD: one LoRA pipeline run

Adapted from the LoRA scenario (Appendix B), drawn from `gitops/charts/mlops`, `components/mlops`, `gitops/charts/mlflow` and `gitops/charts/kueue`.

```mermaid
flowchart LR
  OP["make d3 run mlops<br/>or the dashboard"] -->|"KFP API"| API
  subgraph NS["namespace zuno-mlops"]
    API["DSPA mlops-dspa"]
    subgraph DAG["Argo Workflow per run"]
      PREP["prepare-dataset"]
      TRAIN["train-lora<br/>submitter only"]
      MERGE["merge-export<br/>comage only"]
      GATE["evaluate<br/>agent acceptance gate"]
      PUSH["push-registry<br/>re-checks the gate"]
    end
    TJ["TrainJob<br/>TrainingRuntime mlops-lora<br/>JobSet"]
  end
  DB[("MariaDB zuno-data<br/>database mlops")]
  API --> DB
  API --> PREP --> TRAIN
  TRAIN -->|"comage"| MERGE --> GATE
  TRAIN -->|"tekos"| GATE
  GATE --> PUSH
  TRAIN -->|"create, poll"| TJ
  TJ --> BURST["GPU burst MachineSet<br/>0 to 1, back to 0"]
  SRC[("S3 zuno-demo-sources<br/>base model, style corpus")]
  OUT[("S3 per-cluster mlops bucket<br/>datasets, models, evaluations")]
  SRC --> PREP & TJ
  PREP & TJ & GATE & PUSH --> OUT
  MLF["MLflow<br/>workspace zuno-mlops"]
  TJ -. "params, loss" .-> MLF
  GATE -. "gate_passed" .-> MLF
  PUSH --> MR["Model Registry REST"]
  MR -. "artifact URI" .-> PR["Reviewed change<br/>models values: loraAdapters"]
  PR -->|"Argo CD sync"| LIS["LLMInferenceService qwen35-9b<br/>download-adapter init container,<br/>vLLM lora-modules"]
  OUT --> LIS
  KQ["Kueue ClusterQueue default<br/>evaluation Jobs"]
  KQ -. "TrainJob not integrated" .- TJ
```

## LLD: evaluation paths

Adapted from the evaluation scenario (Appendix B).

```mermaid
flowchart TB
  subgraph RUN["namespace zuno-ai-run, Kueue LocalQueue"]
    GATE["acceptance gate Job<br/>20 scenarios at 75 percent"]
    GARAK["Garak Jobs<br/>smoke and security"]
    RAGAS["RAGAS Job<br/>faithfulness, context precision"]
    EH["EvalHub<br/>lm-evaluation-harness, garak jobs"]
    LMEJ["LMEvalJobs<br/>off since 2026-11-05"]
  end
  MODELS["local model Services<br/>KServe"]
  UNIFAI["UnifAI agents and RAG"]
  DASHB["RHOAI dashboard<br/>Evaluations"]
  MLF["MLflow experiments"]
  OTEL["OTel collector"] --> PROM["Prometheus"] --> GRAF["Grafana<br/>TrustyAI evaluation"]
  GATE --> UNIFAI
  RAGAS --> UNIFAI
  RAGAS -->|"judge model"| MODELS
  GARAK --> MODELS
  LMEJ --> MODELS
  DASHB -->|"as the user"| EH
  EH -.-> MLF
  GARAK & RAGAS -. "attack success rate, score" .-> OTEL
  LMEJ -. "results" .-> PEFT["peft_regression.py<br/>candidate vs base, max drop 0.05"]
```

Scenarios: [LoRA pipeline, MLflow and Kueue](../demo/scenarios/rhoai/lora-pipeline-mlflow-kueue.md), [model catalog and registry](../demo/scenarios/rhoai/model-catalog-registry.md), [evaluation with TrustyAI and EvalHub](../demo/scenarios/rhoai/evaluation-trustyai-evalhub.md).
