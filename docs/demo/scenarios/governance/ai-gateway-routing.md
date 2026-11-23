# Scenario: ai-gateway - model routing and fallback

Last reviewed: 2026-11-20

## Introduction

The ai-gateway is the only router between the experiences and the models (see [Appendix A](#appendix-a---hld)). For
each call it builds an ordered list of providers, then tries them in that order. The order is declared per agent or
experience and per task, as a **preferred** list and a **fallback** list, in the signed agents release. The gateway
never reads the question. The task decides: in Open WebUI, OpenClaw and Dify, the model **Zuno Code** selects the task
`code`, whose list puts Mistral Codestral first and the local models after it.

Two rules sit above the order. The data classification removes the providers that may not see the data; that story is
in the [sovereignty scenario](./ai-gateway-sovereignty.md). Availability removes the models that cannot answer now: a
local model whose controller reports it not ready is skipped, and a provider that has just failed is skipped for 60
seconds. When nothing is left, the gateway answers 503 at once. How the list is built and walked is in
[Appendix B](#appendix-b---lld).

**The message:** "The platform picks the model for each task, falls back when a model is down, and never waits on a
model that is not there."

![The 5-minute version of the AI gateway routing demo, recorded live: sale-01 picks Zuno Code in Open WebUI and asks a code question, then ai-ops-01 opens the Grafana panel that names the provider that served Open WebUI, Mistral Codestral. Rows 3:15 and 4:15 are words.](../../../assets/img/demo/ai-gateway-routing.gif)

## Personas

The personas are fictional role accounts of the Keycloak realm `zuno`. They share one
password, kept in Vault at `keycloak/demo-personas`. The [catalogue](../../README.md#personas) lists all of them.

| Persona | Profile | What it can do here | Role in this demo |
|---|---|---|---|
| **sale-01** | Salesperson, front office. Groups `sales`, `agent_comage`, `agent_finage`. | Open WebUI user. Picks between **Zuno** and **Zuno Code** on the default gateway (the picker also lists **Zuno wesh** and the `praxis.` models of the alternative gateway, not used here). Its calls are routed under the client `open-webui`, task `chat` or `code`. | The everyday employee of the 5-minute version: asks a code question with **Zuno Code**. |
| **ai-ops-01** | AI platform operator, back office. Group `ocp-ai-ops` (admin on the Zuno namespaces, `zuno-monitoring` included). | Opens Grafana and the Tempo search UI, both behind the OpenShift sign-in. | Shows which provider served each call (5-minute version), the skipped candidates and the trace (15-minute version). |
| **paas-ops-01** | Platform operator, back office. Group `ocp-paas-ops` (cluster-admin). | Runs the golden-path probe and reads the routing ConfigMaps and the model status. | The presenter's `oc` terminal in the 15-minute version. |

Other identities:
- `eval-consultant-01`, an evaluation copy of consultant-01: the probe `zuno-code` signs in to Open WebUI with it,
  never on stage;
- consultant-01 and consultant-02 are named only: they ran the recorded Codestral fallback drill of 2026-11-05.

## Presenter lifecycle

`make demo use ai-gateway-routing 5|15` selects this page.
Each section below is printed after its action's Ansible file (`ansible/demos/ai-gateway-routing/<action>.yml`) has
run, and says what is left to the presenter. No action of this demo changes the cluster.

### Status

Nothing to do. The file reads the Applications `zuno-ai-gateway-d0`/`-d1`, `zuno-llm-d1` and `zuno-open-webui-d1`,
the Deployments `ai-gateway` and `open-webui`, the gateway environment (`MODEL_TASK_ALIASES`,
`MODEL_READINESS_ENABLED`, `CIRCUIT_BREAKER_ENABLED`, `CIRCUIT_OPEN_SECONDS`), the ConfigMaps
`ai-gateway-model-routing` and `zuno-provider-routing`, the ExternalSecret `llm-provider-mistral-codestral`, the
`LLMInferenceService` models in `zuno-ai-run` (and how many are Ready), the Deployment `grafana-deployment` and the pod
`tempo-tempo-0`. The key of Codestral itself is not
tested. If one is missing or not Healthy, stop and tell the platform owner: this demo installs nothing. The four
local models were `READY True` on 2026-11-13.

### Check

Nothing to do when it passes. It runs the golden-path probe `zuno-code` (see [golden-path.md](../../golden-path.md)).
It asks "Write a one-line Python function that adds two numbers." with the `zuno-code` model through Open WebUI, as
eval-consultant-01. If it fails, see [If something goes wrong](#if-something-goes-wrong).

### Install

Nothing to do. The routing is part of the shared platform: the file runs nothing and
installs nothing (Status reads it).

### Start

Nothing is prepared by the file. What only a person does:

- [ ] A terminal at the repository root, logged in with `oc` as **paas-ops-01**. If `status` reported that the group
  `ocp-paas-ops` is missing, **paas-ops-01** has never signed in to the OpenShift console (still the case on
  2026-11-13): sign in once in a browser first, then log the terminal in.
- [ ] Browser profile 1: `https://open-webui.apps.demo333.startx.fr`, **Continue with Keycloak** as **sale-01**. Start
  a new chat with the model **Zuno** and ask one question before the audience arrives. It wakes the local model and
  gives the dashboard a local series to compare with.
- [ ] Browser profile 2: Grafana `https://grafana-route-zuno-monitoring.apps.demo333.startx.fr`, signed in as
  **ai-ops-01**. Dashboard **Zuno Platform / Five experiences**, last 1 hour, `client` = `open-webui`.
- [ ] 15-minute version: the Tempo search UI `https://tempo-jaegerui-zuno-monitoring.apps.demo333.startx.fr`, signed
  in as **ai-ops-01**, and the Zuno Code live-proof evidence (listed under References) open at section T5.
- Known on screen, not a failure: Open WebUI generates the chat title with the model you picked, so one **Zuno
  Code** question makes two Codestral calls.
- The optional block [The coding pair: Codestral and local only](#the-coding-pair-codestral-and-local-only) is not a step. It is an owner action:
  the lifecycle prints it and never runs it. If you play it, you sign in to UnifAI as **consultant-01** yourself.

### Stop

Nothing to do. Close the two browser profiles and the terminal.

### Uninstall

Nothing to do.

## 5-minute version

| Time | Do | Say | You should see |
|---|---|---|---|
| 0:00 | Profile 1, **sale-01**: open the model picker | "Zuno and Zuno Code. I do not pick a provider: I pick a kind of work. The platform owns the list of models behind each one." | **Zuno** and **Zuno Code**. Since 2026-11-17 the picker also lists **Zuno wesh** and the models prefixed `praxis.` (the alternative gateway): leave them. |
| 0:45 | New chat, **Zuno Code**, ask: `write Python code that checks the format of an email address` | "A code question goes to a code model, Mistral Codestral. If Codestral is down, a model running on our GPUs answers instead." | A Python function with a regular expression, in a few seconds. |
| 2:00 | Profile 2, Grafana, row **Same models, same routing**, panel **Which provider served each experience (over range)** | "Here is the proof. The code question went to Codestral. The other line is the model on our own GPUs, which takes over if Codestral is down. Same chat, same user: the task chose." | For `open-webui`: `mistral-codestral` with outcome `success`. Seen in the take of 2026-11-16: the panel alone, filtered on the client `open-webui`, with the columns Time, client, outcome, provider and Value: `mistral-codestral` `success` 2.01, and `local-gpt-oss-maas` `success` 0. The take asked no warm-up question, so the local line has no call to show; the panel title says "over range", so the Value is computed over the time range (how, not checked); do not read it as a count of questions. |
| 3:15 | Say what happens when a model is down | "If a local model stops, its controller says so and the gateway skips it in milliseconds. Before this rule, the same situation made an Open WebUI chat wait about ten minutes." | |
| 4:15 | Close | "The platform picks the model for each task, falls back when a model is down, and never waits on a model that is not there." | |

## 15-minute version

Run the 5-minute version, then:

| Time | Do | Say | You should see |
|---|---|---|---|
| 5:00 | Terminal: `oc get configmap ai-gateway-model-routing -n zuno-ai-run -o yaml` | "One entry per agent or experience and per task. The order only reorders what the classification allows; it can never add a provider." | `open-webui`/`chat`: `local-gpt-oss-maas`, `local-gpt-oss`. `open-webui`/`code`: `mistral-codestral`, not strict. `arkos`/`write-code`: `local-gpt-oss-maas`, `local-gpt-oss`, then `local-maas`, `local`, local only at every level. `tekos`/`find-relevant-docs`: a `preferred` and a `fallback` list. |
| 6:30 | Open the agents release: [experience-clients/open-webui/tasks/code.md](https://github.com/startxfr/zuno-demo-agents/blob/main/experience-clients/open-webui/tasks/code.md), then [policies/model-routing/model-routing-policy.yaml](https://github.com/startxfr/zuno-demo-agents/blob/main/policies/model-routing/model-routing-policy.yaml) | "The owner of a task declares roles, here `code`. The corporate policy holds the ordered lists. The platform generates the table from the signed release; nobody edits it by hand." | `zuno.models.preferred: [code]` in the task. `preferred:`, `fallback:` and `local_only_for:` entries in the policy. |
| 8:00 | Point at the `local_only_for: [C1, C2, C3]` lines | "Tekos answers from Confluence and the technical documentation. For those tasks, no external model at any level: if no local model answers, the task fails instead of sending the context out." | `local_only_for` on Tekos `answer-technical-question` and `find-relevant-docs`, Arkos `draft-architecture-testimonial` and `workshop-presentation`, Naveo. |
| 9:00 | Open [`platform/ai-gateway/provider-routing.yaml`](../../../../platform/ai-gateway/provider-routing.yaml) | "Fourteen providers. Each local model has two entries: through MaaS first, then direct. Each declares its role, the levels it may serve, its timeout, and the model object whose readiness the gateway watches." | Roles `default`, `quality`, `reasoning`, `specialized`, `code`, `reasoning-external`, `general-external`. `inference_service:` on the 8 local entries; `timeout_seconds` 180 through MaaS, 60 direct. |
| 10:30 | Terminal: `oc get llminferenceservice -n zuno-ai-run`, then `oc set env deploy/ai-gateway -n zuno-ai-run --list \| grep -e MODEL_READINESS -e CIRCUIT_` | "The gateway reads the `Ready` condition every 10 seconds. A model that is not ready is skipped. A provider that failed by timeout, connection error or 5xx is skipped for 60 seconds, then one call tests it again." | Four models `READY True`. `MODEL_READINESS_ENABLED` `true`, `CIRCUIT_BREAKER_ENABLED` `true`, `CIRCUIT_OPEN_SECONDS` `60`. |
| 11:30 | Grafana, panel **Candidates skipped for availability (over range)** | "On 2026-11-02 the GPU nodes were down. Every MaaS candidate waited its full 180 seconds, and an Open WebUI chat reached a SaaS model after about ten minutes. Now the skip costs nothing and is counted." | Skips by client, provider and reason (`not_ready`, `circuit_open`) if a model was down in the range. An empty panel means nothing was skipped. |
| 12:15 | Tempo search UI: service `ai-gateway`, operation `model_call`, tags `zuno.task=code zuno.client=open-webui`, last 15 minutes | "Each call is traced with the provider and whether it ran on our GPUs or outside." | The span of the 5-minute question: `zuno.provider=mistral-codestral`, `zuno.model_kind=saas`, `zuno.classification=C1`, `zuno.model=codestral-latest`. |
| 13:00 | Show the WP-194 evidence, table T5 | "We broke Codestral on purpose on 2026-11-05. The user got a normal answer from the local model, in the same trace, about one second after the failure. The routing decision of such a call names `local-maas`, with `fallback_used: true` and `fallback_from: mistral-codestral`. UnifAI reads it from `GET /v1/routing-decisions/{request_id}`." | Two traces: `mistral-codestral` error `Invalid model` in under a second, then `local-maas` ok in 40 to 66 s. |
| 14:15 | Close | Repeat the message. | |

### The coding pair: Codestral and local only

Optional, 3 minutes, since agents v1.0.1 (promoted on demo333 on 2026-11-14). The same code request goes to two
agents. The task decides which models may serve it: Tekos works at C2 (since agents v1.2.5) and lists Mistral Codestral first, Arkos works at C2 too but its code task keeps local models only.

Dry-run on 2026-11-14:
- **API and Tempo, not the UI.** Tekos answered in 1.8 s and Arkos in 23 s. The Tempo search below returned exactly the
  values in the last column.
- **Personas.** `consultant-01` holds both `agent_tekos` and `agent_arkos`.
- **Acceptance gate.** Scenarios tekos 21 and arkos 22 (`chat_routing`) prove the same thing there.

| Do | Say | You should see |
|---|---|---|
| UnifAI as **consultant-01**, workspace `agent-tekos`, workflow `tekos-write-code`, ask: `Write a Kubernetes NetworkPolicy allowing ingress only from the istio-system namespace.` | "Tekos works on public and internal data, C2. A code request goes to the best code model, Mistral Codestral." | A NetworkPolicy manifest in a few seconds. |
| Workspace `agent-arkos`, workflow `arkos-write-code`, same request | "Arkos works on our customers' architecture. Its code task is local only: the same request never leaves our GPUs and gpt-oss-20b answers." | The same kind of manifest, a little slower (plan, draft and write stages). |
| Tempo search UI: service `ai-gateway`, operation `model_call`, tag `zuno.task=write-code`, last 15 minutes | "Same request, two agents, two models. Nobody chose the model: the policy of the task did." | Tekos: `zuno.provider=mistral-codestral`, `zuno.model=codestral-latest`, `zuno.model_kind=saas`, `zuno.classification=C2`. Arkos: `zuno.provider=local-gpt-oss-maas`, `zuno.model=gpt-oss-20b`, `zuno.model_kind=local`, `zuno.classification=C2`. |

## If something goes wrong

| Symptom | Fallback | Say |
|---|---|---|
| The **Zuno Code** answer takes 40 seconds or more | Carry on. Codestral failed and a local model answered. Show the provider panel: `mistral-codestral` with outcome `error`, then a local provider. | "This is the fallback at work: Codestral failed, our own model answered the same question." |
| 503 "no eligible provider is available for classification ...: ... not ready" | Show it. Every provider the call could use is down or skipped. | "The gateway answers at once instead of waiting minutes on models that are not there." |
| The probe prints `FAIL zuno-code no zuno-code model in Open WebUI` | The model list of Open WebUI lost **Zuno Code**. Show **Zuno** only and play the configuration steps of the 15-minute version. | |
| The panel shows no `open-webui` series | Widen the time range to 3 hours. Export and scrape take about a minute. | |
| **Candidates skipped for availability (over range)** is empty | Say that nothing was down in the range, and quote the measurement of 2026-11-02 instead. | "An empty panel is the good case." |
| No span in the Tempo search | Widen to the last hour, or drop the `zuno.client` tag. | |
| Grafana does not load | Skip the panels. Show the ConfigMap and the WP-194 evidence. | |

## Limits

- **The gateway never reads the question.** "Zuno Code" is the user's choice. A code question asked to **Zuno** stays
  on the local models; a chat question asked to **Zuno Code** goes to Codestral.
- **A tool turn stays local.** In an experience client, a turn that carries a tool result is C2 and local-only
  (ADR-0594). "Zuno Code" reaches Codestral only for a tool-free C1 conversation. See the
  [sovereignty scenario](./ai-gateway-sovereignty.md).
- **Readiness covers the local models only.** A SaaS outage is found by its first failure: one call pays the timeout,
  then the breaker skips the provider for 60 seconds. The breaker is in memory and per replica.
- **A slow but ready model is still waited for.** 180 s through MaaS, 60 s direct (user decision 2026-10-31, a cold
  model compiles its kernels on the first requests).
- **The routing decision lives 120 seconds** in Redis and names the serving provider and the first candidate. It does
  not list the skipped candidates: those are only on the counter `zuno_model_candidates_skipped`.
- **Arkos writes code on local models.** Its `write-code` task carries `local_only_for` at every level (Arkos was
  floored at C3 until agents v1.2.5, and is C2 now), so Codestral is not a candidate for it. It runs on the local models
  only, gpt-oss-20b first. Codestral serves Tekos and "Zuno Code".
- **The skip of a down model is told, not shown.** Showing it live needs a model taken down. It was proven on demo333
  on 2026-11-03 (WP-188): models skipped while not ready, served again without a gateway restart.

## Appendix A - HLD

Where the ai-gateway sits in Zuno. The highlighted box is the subject of this page. Plain arrows carry requests,
dotted arrows carry identity, policy or telemetry.

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

## Appendix B - LLD

How the ai-gateway builds and walks the candidate list. Drawn from `components/ai-gateway/app/main.py`
(`chat_completions`, `_invoke_with_fallback`, `_availability_skip`, `_nothing_available`), `app/model_tasks.py`,
`app/model_routing_policy.py`, `app/routing.py` (`RoutingTable.candidates_for`, `_apply_preference`),
`app/model_readiness.py`, `app/circuit_breaker.py`, `app/routing_decisions.py` and `app/telemetry.py`, with
`platform/ai-gateway/provider-routing.yaml`, `gitops/charts/ai-gateway/files/model-routing.generated.yaml` and
`platform/okf/generate_stack_config.py`.

```mermaid
flowchart TB
  REQ["POST /v1/chat/completions<br/>X-Zuno-Agent, X-Zuno-Task, model"]
  subgraph GW["ai-gateway pod, namespace zuno-ai-run"]
    TASK["1. Task<br/>experience client + model zuno-code<br/>= task code (MODEL_TASK_ALIASES)"]
    LEVEL["2. Effective level and local-only<br/>floor, tool markers, local_only_for<br/>(sovereignty scenario)"]
    ELIG["3. Eligible providers<br/>eligible_for holds the level,<br/>local only if required, minus exclude"]
    ORDER["4. Order<br/>preferred then fallback of (agent, task),<br/>other survivors in table order;<br/>strict = listed providers only"]
    NONE{"every candidate<br/>not ready or breaker open?"}
    LOOP["5. Next candidate"]
    AVAIL{"model Ready and<br/>breaker closed?"}
    CALL["6. Call<br/>180 s through MaaS, 60 s direct,<br/>no SDK retry"]
    OK{"answered?"}
    REC["7. Record<br/>span model_call, zuno_model_calls_total,<br/>routing decision"]
    E503["503 at once<br/>no eligible provider is available"]
    EFAIL["502, or 503 if every candidate was skipped<br/>all eligible providers failed"]
  end
  REL[("agents release<br/>policies/model-routing,<br/>experience-clients/*/tasks")]
  CMR[("ConfigMap ai-gateway-model-routing<br/>32 preferences")]
  CMP[("ConfigMap zuno-provider-routing<br/>14 providers: role, eligible_for,<br/>inference_service, timeout")]
  LIS[("LLMInferenceService Ready<br/>polled every 10 s")]
  REDIS[("Redis in zuno-auth<br/>routing decision, 120 s")]
  API["GET /v1/routing-decisions/request_id<br/>provider, model, kind, classification,<br/>fallback_used, fallback_from"]
  REQ --> TASK --> LEVEL --> ELIG --> ORDER --> NONE
  NONE -- yes --> E503
  NONE -- no --> LOOP --> AVAIL
  AVAIL -- "no: skip, count<br/>zuno_model_candidates_skipped" --> LOOP
  AVAIL -- yes --> CALL --> OK
  OK -- "timeout, connection error, 5xx:<br/>breaker open 60 s" --> LOOP
  OK -- yes --> REC
  LOOP -- "no candidate left" --> EFAIL
  REL -. "generate_stack_config.py" .-> CMR
  CMR -.-> LEVEL & ORDER
  CMP -.-> ELIG
  LIS -.-> NONE & AVAIL
  CALL -->|"kind local"| MAAS["MaaS gateway, then the direct twin<br/>gpt-oss-20b, qwen models"]
  CALL -->|"kind saas, C1 or C2"| SAASP["SaaS providers<br/>Codestral, OVHcloud, Mistral..."]
  REC -.-> REDIS
  API -.-> REDIS
  REC -.-> TEMPO["Tempo<br/>zuno.provider, zuno.model_kind,<br/>zuno.task, zuno.client"]
```

## References

The decisions this page rests on:

- [ADR-0419](../../../adr/0419-split-model-preference-into-preferred-fallback-with-prompt-slot-overrides.md): a
  preference is a `preferred` list and a `fallback` list; it only reorders the eligible providers.
- [ADR-0417](../../../adr/0417-consume-codestral-via-mistral-api.md): Codestral for code tasks; `strict` keeps a task
  on its listed providers only.
- [ADR-0581](../../../adr/0581-derive-stack-configuration-from-the-admitted-corp-bundle.md): the routing table is
  generated from the admitted agents release.
- [ADR-0596](../../../adr/0596-let-experience-clients-pick-a-declared-code-model-routed-to-codestral-first.md): "Zuno
  Code" maps to the task `code`, Codestral first, the local models as fallback.
- [ADR-0591](../../../adr/0591-route-only-to-ready-local-models-and-fail-fast-on-stalled-candidates.md): only ready
  local models are tried, a circuit breaker skips a provider that just failed, and an empty list is a 503 at once.
- [ADR-0550](../../../adr/0550-demonstrate-sovereign-ai-through-classification-specialization-and-resilience.md):
  `local_only_for` per task, and the routing decision published per request.
- [ADR-0349](../../../adr/0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md): Restructure demo personas, ocp-* cluster-access groups and two new agents.
- [ADR-0616](../../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md): Prepare and play every catalogue demo through one make demo lifecycle.

Evidence:

- [WP-194](../../../roadmap/evidence/wp-194-zuno-code-live-proof.md): the live proof of Zuno Code, section T5.

## Page status

> **Status:** Rehearsed on 2026-11-15 through `make demo rehearse ai-gateway-routing`: the 5-minute version PASS at
> 02:21 (11 units, 96 s); the 15-minute version PASS at 02:24 (20 units, 44 s). Evidence:
> [WP-276](../../../roadmap/evidence/wp-276-governance-rehearsals-2026-11-15.md). Prerequisites checked read-only on
> demo333 on 2026-11-13: Applications
> `zuno-ai-gateway-d0`/`-d1`, `zuno-llm-d1` and `zuno-open-webui-d1` Synced and Healthy; Deployment `ai-gateway` 1/1;
> gateway environment `MODEL_TASK_ALIASES=zuno-code=code:Zuno Code`, `MODEL_READINESS_ENABLED=true`,
> `CIRCUIT_BREAKER_ENABLED=true`, `CIRCUIT_OPEN_SECONDS=60`,
> `MARKER_FAIL_CLOSED_CLIENTS=open-webui,openclaw-*,dify,kagent`; ConfigMap `ai-gateway-model-routing` (30
> preferences, `open-webui`/`code`: `prefer: [mistral-codestral]`, not strict) and ConfigMap `zuno-provider-routing`
> (14 providers) identical to the repository files; ExternalSecret `llm-provider-mistral-codestral` `SecretSynced` (the
> key itself was not tested);
> the four `LLMInferenceService` Ready; Deployment `open-webui` 1/1; Grafana 1/1 and `tempo-tempo-0` Running.
> **paas-ops-01** had still not signed in to OpenShift.
> **Show-ready ([ADR-0606](../../../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)):**
> yes, golden-path probe `zuno-code`.
> **Personas:** see [Personas](#personas).
> **Used in workshops:** [Sovereign and governed AI](../../workshops/sovereign-governed-ai.md), [One backend,
> three experiences](../../three-experiences.md).
