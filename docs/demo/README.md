# Demo catalogue

This directory holds the demonstrations of the Zuno platform:

- **Scenarios**: one brick of the platform, or one feature of a brick, per page. Each page has a 5-minute and a
  15-minute version.
- **Workshops**: several scenarios played in order by a presenter, from 30 minutes to 2 hours.
- **Operations documents**: what to check and freeze before showing anything live.

Every scenario page has the same structure, in this order ([ADR-0617](../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md)). You can open any page and find the same sections in the same place. The Introduction, Personas and Presenter lifecycle carry no ADR or work-package reference and no link into `docs/adr/` or `docs/roadmap/`: those are in References.

| Section | What it gives you |
|---|---|
| Introduction | What the brick is, where it sits in Zuno, the message; the GIF of the 5-minute version comes last, when the owner has said "go <id>" |
| Personas | Each account used or named in the scenario: who it is, what it may do there, and what the presenter does with it |
| Presenter lifecycle | `### Status`, `### Check`, `### Install`, `### Start`, `### Stop`, `### Uninstall`: what is left to the presenter once `make demo <action>` has run, or "Nothing to do." Accounts are named by their Vault path, never their password. It replaces "Before you start" ([ADR-0616](../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)); pages that still have "Before you start" move by 2026-11-17 (WP-273 to WP-280) |
| 5-minute version | The message and one visible proof, for any audience: `Time / Do / Say / You should see` |
| 15-minute version | Starts where the 5-minute version stops and shows the mechanism, for a technical audience |
| If something goes wrong | Symptom, fallback, and the sentence to say |
| Limits | What the scenario does not show, and the brick's named limits |
| Appendix A - HLD | The platform map, with the brick highlighted |
| Appendix B - LLD | The brick's internals, drawn from its chart and component |
| References | The decisions (ADRs, with their one-line meaning) and the work-package evidence the page rests on |
| Page status | The status banner, last: date and content of the last read-only check on demo333, the rehearsal result, whether the page is show-ready ([ADR-0606](../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)), workshops that use it |

New pages start from [`_template-scenario.md`](_template-scenario.md) for a scenario and
[`_template-workshop.md`](_template-workshop.md) for a workshop. A workshop links its scenarios and the version to
play; it does not copy their steps.

## Playing a demo

[ADR-0616](../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md) makes `make demo` the
only interface of a presenter. The commands are built by [WP-270](../roadmap/work-packages/wp-270-build-the-make-demo-lifecycle-engine.md)
and every page moves to them by 2026-11-18. Until a page has its `## Presenter lifecycle` section, follow its "Before
you start" checklist by hand.

| Command | What it does |
|---|---|
| `make demo list` | The demos, their step counts in each version, and whether they are show-ready |
| `make demo use <id> 5\|15` | Selects a scenario and its version for the commands below (a workshop takes no version) |
| `make demo status` | Fast reads: is everything the demo needs installed and healthy |
| `make demo check` | The demo's golden-path probes, its browser check and its own assertions |
| `make demo install` | The demo's own add-on, if it has one; the shared platform is only verified |
| `make demo start` | Prepares the session (warm-up, demo data) |
| `make demo step next`, `make demo step <N>` | Runs the step's reads, then prints its Do, Say and You should see |
| `make demo stop` | Cleans up what the session created |
| `make demo uninstall` | Removes the demo's own add-on; never a shared component |
| `make demo freeze on\|off` | Marks a freeze on this workstation: `install`, `uninstall` and `rehearse` refuse |
| `make demo rehearse <id> 5\|15` | The whole sequence without pauses, with a report. It never runs a changing unit that is declared `not_rehearsed`, and skips an optional or mutating step. When the sequence queues golden-path probes or browser checks, it lists them and asks you to type the demo id (or `DEMO_CONFIRM=<id>` without a terminal): they call the models and spend the probe personas' budgets |
| `make demo golden-path`, `make demo browser` | The catalogue-wide checks ([golden-path.md](golden-path.md)) |

A rehearsal that runs probes asks for the demo id even when no unit changes the cluster (the decision of 2026-11-15, after
an unattended workshop rehearsal started by mistake): one prompt covers the changing units and the probes. A rehearsal
that queues none asks nothing. `status`, `check`, `start` and `step`, run alone, are unchanged.

Each command prints the result of its Ansible file first, then the page section. An action that changes the cluster
shows what it will change and asks you to type the demo id.

## Before any live session

1. Run the golden path: `make demo golden-path`, or only the probes of your scenarios with `ONLY=<probe>,<probe> make
   demo golden-path` ([golden-path.md](golden-path.md), [ADR-0605](../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md)).
2. For a demonstration day, apply the [freeze protocol](freeze-protocol.md) and keep the [rollback](rollback.md) page
   open.
3. Read the status of every page you will play: its status banner at the top, or its `## Page status` section at the end. A page that says "rehearse before showing" has no golden-path
   probe: rehearse it the same day.

## Status legend

- **Show-ready: yes (probe)**: the experience or feature has a golden-path probe. Show it only if the probe passed
  within the last hour.
- **Rehearse first**: no probe exists. Rehearse the scenario on the day before showing it.
- **Not show-ready**: a named reason prevents it today (for example, the GPU node of the world model is off).
- **Page**:
  - **written**: in the new format;
- **Rehearsed on 2026-11-15**: the result of the latest valid `make demo rehearse` report for each version, from the evidence file named in the page's status banner (its `## Page status` section, once the page has one). A PASS says the files and the page play; it does not say "show-ready" (see the banner of each page).

## Scenarios

### Experiences: the clients of one governed backend

| Scenario | Shows | Personas | Golden-path probe | Page | Rehearsed on 2026-11-15 |
|---|---|---|---|---|---|
| [Open WebUI](scenarios/experiences/open-webui.md) | SSO, "Zuno" and "Zuno Code" models, tools by group | sale-01, consultant-02, ai-ops-01 | `open-webui`, `zuno-code` | written (wave 0) | 5: PASS, 15: PASS |
| [OpenClaw](scenarios/experiences/openclaw.md) | One assistant per persona, two sign-ins, token injected by the egress proxy, Confluence for consultant-02 and not for sale-01 | consultant-02, sale-01, ai-ops-01 | `openclaw` | written (wave 1) | 5: PASS, 15: PASS |
| [Dify](scenarios/experiences/dify.md) | The three imported apps (agent, chatflow, workflow), the External Knowledge adapter, every call made as consultant-02 through the token proxy | consultant-02, ai-ops-01, paas-ops-01 | `dify` | written (wave 1) | 5: PASS, 15: PASS |
| [kagent](scenarios/experiences/kagent.md) | Cluster diagnosis with five governed read-only tools, a Secret read refused, acting as ai-ops-01 through the token proxy | ai-ops-01, paas-ops-01 | `kagent` | written (wave 1) | 5: PASS, 15: PASS |
| [OpenShift Lightspeed](scenarios/experiences/lightspeed.md) | The console assistant on a local model through MaaS, cluster reads with the user's own rights, Zuno tools through the mcp-gateway | consultant-02, sale-01, paas-ops-01 (only `consultant`, `sales` and cluster-admins may open the chat) | `lightspeed` | written (wave 1) | 5: PASS, 15: PASS |
| [UnifAI agents](scenarios/experiences/unifai-agents.md) | Workspaces from Keycloak groups, Tekos from the signed release, cluster tools for ai-ops-01 only, starters and templates | consultant-02, ai-ops-01 | `unifai-tekos` (the cluster-tools contrast has no probe) | written (wave 1) | 5: PASS, 15: PASS |
| [UnifAI live RAG](unifai-live-rag.md) | Upload (docling, qwen3-embedding, Qdrant), cited answers, isolation from team workflows and from another persona, optional Confluence resync | consultant-01, sale-01 | none (rehearse first) | written (wave 1) | 5: PASS, 15: PASS |
| [Blender 3D](blender-3d.md) | A sentence becomes editable Blender objects on a local model, behind the workstation entry and the C3 client floor | ai-dev-01, ai-ops-01, paas-ops-01 | `blender` | written (wave 1) | 5: PASS, 15: PASS (install, uninstall not rehearsed) |
| [World model](world-model.md) | Walk into a generated world and change it, prompts screened, on an on-demand GPU node | ai-ops-01, paas-ops-01 | `world-model` (not show-ready: no GPU node) | written (wave 1) | 5: PASS, 15: PASS (not show-ready; the files and the page only) |
| [Claude Code on sovereign models](scenarios/experiences/claude-code-sovereign.md) | Claude Code on the presenter's workstation, signed in by Keycloak device code, its calls translated by the alternative gateway for a local model, each tool approved on the laptop, the trace and the firewall as proof that no model call leaves the cluster | ai-dev-01, ai-ops-01, paas-ops-01 | none (rehearse first: no golden-path probe) | written (wave 5) | 5: PASS (2026-11-18, the owner's workstation, trace row not played), 15: not rehearsed |

### Governance of the backend

| Scenario | Shows | Personas | Golden-path probe | Page | Rehearsed on 2026-11-15 |
|---|---|---|---|---|---|
| [Sovereignty by data classification](scenarios/governance/ai-gateway-sovereignty.md) | C1/C2/C3, the C3 floor keeps Arkos on local models, fail closed, the trace | paas-ops-01, ai-ops-01 | `sovereignty`, `trace` | written (wave 0) | 5: PASS, 15: PASS |
| [Model routing and fallback](scenarios/governance/ai-gateway-routing.md) | "Zuno Code" to Codestral first, preferred and fallback lists per task, `local_only_for`, unready models skipped with an immediate 503, the routing decision API | sale-01, ai-ops-01, paas-ops-01 | `zuno-code` | written (wave 2) | 5: PASS, 15: PASS |
| [Guardrails](scenarios/governance/guardrails.md) | A prompt injection detected in observe mode through Dify, the TrustyAI dashboard, the mode per classification level, what blocking would do | consultant-02, ai-ops-01, paas-ops-01 | `guardrails` | written (wave 2) | 5: PASS, 15: PASS |
| [One budget per persona](scenarios/governance/quotas.md) | One token budget per persona across the experiences, the 2026-11-03 evidence, MaaS budgets versus persona budgets, fail-closed classes, the per-turn ceiling | sale-01, ai-ops-01, paas-ops-01 | none (rehearse first) | written (wave 2) | 5: PASS, 15: PASS |
| [MCP tools by group](scenarios/governance/mcp-tools-by-group.md) | The same question from two personas, two tool sets, the five checks, signed markers, the delegated-credential refusal, one audit | sale-01, consultant-02, finance-01, ai-ops-01, paas-ops-01 | `tools`, `open-webui` | written (wave 2) | 5: PASS, 15: PASS |
| [A2A delegation with approval](scenarios/governance/a2a-delegation-approval.md) | Arkos asks Tekos for a cluster audit with consultant-02's identity, a human approves in UnifAI, the AAP job link, expiry, limits on depth, cycles and budget, the trace | consultant-02, ai-ops-01, paas-ops-01 | `delegation-approval` (the probe proves the request and a refusal; rehearse the approval, the job and the trace) | written (wave 2) | 5: PASS, 15: PASS |
| [Identity and personas](scenarios/governance/identity-personas.md) | One Keycloak account, three group dimensions, the same group opening a workspace and a tool set, OpenShift groups at first sign-in, service accounts, negative fixtures | consultant-02, sale-01, paas-ops-01 | none (rehearse first) | written (wave 2) | 5: PASS, 15: PASS |
| [Multi-gateway](scenarios/governance/multi-gateway.md) | The same clients on the default gateway and on an alternative one: Open WebUI and kagent in 5 minutes, every wired client in 15, the traces side by side, what the alternative road does not enforce | ai-ops-01, paas-ops-01, consultant-02, ai-dev-01 | none (rehearse first; not show-ready: depends on the alternative gateway and the client wiring) | written (wave 5) | not rehearsed |
| [Agents on an alternative gateway](scenarios/governance/agents-alt-gateway.md) | A kagent agent and a Dify app move to the alternative gateway by one setting, no code change; the gateway sees the proxy's identity | ai-ops-01, consultant-02, paas-ops-01 | none (rehearse first; not show-ready: depends on the alternative gateway and the token proxy routes) | written (wave 5) | not rehearsed |

### Red Hat OpenShift AI and models

| Scenario | Shows | Personas | Golden-path probe | Page | Rehearsed on 2026-11-15 |
|---|---|---|---|---|---|
| [MaaS portal and API keys](scenarios/rhoai/maas-portal-api-keys.md) | A self-service key on a group subscription, token limits, revocation | ai-dev-01, ai-ops-01, paas-ops-01 | none (rehearse first) | written (wave 0) | 5: PASS, 15: PASS |
| [GenAI playground](scenarios/rhoai/genai-playground.md) | The ready-made playground: chat on gpt-oss-20b through MaaS, a document answered with a citation, MCP tools with the user's own OpenShift token (9 tools for `ocp-ai-ops`, 0 for `ocp-ai-dev`) | ai-ops-01, ai-dev-01, paas-ops-01 | none (rehearse first) | written (wave 3) | 5: PASS, 15: PASS |
| [Model serving with llm-d on MIG](scenarios/rhoai/model-serving-llmd-mig.md) | Five models on MIG slices of two 96 GB cards, the GPU quota and its wedged rollouts, hardware profiles, autoscaling, the scale-from-zero training node, the failover drill | paas-ops-01, ai-ops-01 | none (rehearse first) | written (wave 3) | 5: PASS, 15: PASS |
| [External models](scenarios/rhoai/external-models.md) | Mistral Large and OVHcloud gpt-oss-120b published as ExternalModels, subscribed by the ai-gateway only, the `ipp-managed` label trap, C1/C2 eligibility, SaaS still called directly by the gateway | paas-ops-01, ai-ops-01 | none (rehearse first) | written (wave 3) | 5: PASS, 15: PASS |
| [Model catalog and registry](scenarios/rhoai/model-catalog-registry.md) | Red Hat's curated catalog, the dashboard route trap, a registry gated on the evaluation | ai-dev-01, paas-ops-01, ai-ops-01 | none (not show-ready: no model registry on demo333; the catalog part can be rehearsed) | written (wave 3) | 5: PASS, 15: PASS (catalog reads only) |
| [LoRA pipeline with MLflow](scenarios/rhoai/lora-pipeline-mlflow-kueue.md) | A past pipeline run, the TrainJob on a scale-from-zero GPU node, MLflow tracking, the adapter registered and served (recorded evidence), the packed LoRA module trap | ai-dev-01, paas-ops-01 | none (rehearse first) | written (wave 3) | 5: PASS, 15: PASS |
| [Evaluation with TrustyAI and EvalHub](scenarios/rhoai/evaluation-trustyai-evalhub.md) | RAGAS and Garak scores on the TrustyAI dashboard, 20 scenarios per agent at 75%, EvalHub and its RBAC, Kueue admitting the evaluation Jobs, LMEvalJobs off on 3.6 EA | ai-ops-01, ai-dev-01, paas-ops-01 | none (rehearse first) | written (wave 3) | 5: PASS, 15: PASS |

### Foundation and trust

| Scenario | Shows | Personas | Golden-path probe | Page | Rehearsed on 2026-11-15 |
|---|---|---|---|---|---|
| [GitOps and Day 0-3](scenarios/foundation/gitops-day0-3.md) | `make dN verb component` and its four days, which verbs are read-only, the Argo CD Applications on `devel`, the known-good and drift checks, the golden path, freeze and canary rules | paas-ops-01 | none (rehearse first) | written (wave 4) | 5: PASS, 15: PASS |
| [Signed agent release (OKF)](scenarios/foundation/okf-signed-agent-release.md) | An agent's sheet in its own repository, one digest in `agents.lock`, `okf-fetch` VERIFIED from the internal Quay, offline admission, promotion by pull request, revocation | paas-ops-01 | none (rehearse first) | written (wave 4) | 5: PASS, 15: PASS |
| [Image signing and admission](scenarios/foundation/image-signing-admission.md) | RHTAS in the cluster, image policies in enforce mode, images pinned by digest and pulled from Quay through mirror sets, the verify Job and the release ledger, the mirror-set drain trap | paas-ops-01 | none (rehearse first) | written (wave 4) | 5: PASS, 15: PASS |
| [Vault and PKI](scenarios/foundation/vault-pki.md) | Vault on Raft with KMS auto-unseal and TLS, ExternalSecrets in every namespace, Let's Encrypt and Vault-issued certificates, Transit signing for the gateways | paas-ops-01, ai-ops-01 | none (rehearse first) | written (wave 4) | 5: PASS, 15: PASS |
| [Service mesh and Kiali](scenarios/foundation/service-mesh-kiali.md) | STRICT mTLS, short-lived SPIFFE identities from Vault PKI, injection versus allowlist, the MaaS gateway on the same mesh, the Kiali graph | paas-ops-01, ai-ops-01 | none (rehearse first) | written (wave 4) | 5: PASS, 15: PASS |
| [Observability and traces](scenarios/foundation/observability-trace.md) | A Tekos turn found in Tempo with its span tags, the Run Trace dashboard, usage and cost per experience, the collector pipeline, two counting traps, Perses in the console | consultant-02, ai-ops-01, paas-ops-01 | `trace` (with `unifai-tekos`) | written (wave 4) | 5: PASS, 15: PASS |
| [AAP audited operations](scenarios/foundation/aap-audited-operations.md) | Job templates and workflows from Git, reader versus ops rights in the AAP UI, a check job and its pod, the agents' audit tools and their rate limit | consultant-03, consultant-02, paas-ops-01 | none (rehearse first) | written (wave 4) | 5: PASS, 15: PASS |

## Workshops (presenter-led)

| Workshop | Built from | Duration | Page | Rehearsed on 2026-11-15 |
|---|---|---|---|---|
| [One backend, three experiences](three-experiences.md) | UnifAI, Open WebUI, OpenClaw, then one dashboard block (backend, routing, one budget) | 30 min | written (wave 1) | workshop: PASS |
| [One governed backend, many experiences](five-experiences.md) | UnifAI, Open WebUI, OpenClaw, Dify, kagent, Lightspeed, Blender, then one dashboard block (backend, routing, guardrails, tools, budget) | 45-55 min | written (wave 1) | workshop: PASS (blender-3d install, uninstall not rehearsed) |
| [Sovereign and governed AI](workshops/sovereign-governed-ai.md) | Identity, tools, sovereignty, routing, guardrails, budget, then the trace | 45 min | written (wave 2) | workshop: PASS |
| [Agentic AI](workshops/agentic-ai.md) | UnifAI agents, MCP tools, live RAG, delegation with approval (15-minute version), kagent, the signed agents release, sovereignty | 60 min | written (wave 2) | workshop: PASS |
| [RHOAI end to end](workshops/rhoai-end-to-end.md) | Catalog, serving, external models, MaaS key, playground, LoRA pipeline, evaluation | 70-90 min | written (wave 3) | workshop: PASS |
| [Trusted platform and operations](workshops/trusted-platform-ops.md) | GitOps, signed images, signed agents, Vault, mesh, observability (15-minute version), AAP | 60 min | written (wave 4) | workshop: PASS |

**Two-hour combinations:**
- sovereign and governed AI, then agentic AI;
- RHOAI end to end, then the MaaS and sovereignty scenarios in their 15-minute versions;
- trusted platform and operations, then sovereign and governed AI.

Leave 10 minutes for questions between two workshops.

## Stress and coverage

The [Day 3 stresstest](../platform/stresstest.md) (ADR-0624) replays the scenarios with drivers in `evaluations/stress/`. A bare id is the golden moment of the scenario, `<id>-state` its read-only state check (the assertions of `ansible/demos/<id>/{status,check}.yml`, read from a Job over the Kubernetes API), `load-*` a load driver. The scenario pages are not changed by the stresstest. Status as of 2026-11-19, read from the drivers: the repository work is in review, the live runs are not made yet. `load-ai-gateway` (chat completions straight on the ai-gateway, no UI) serves no single scenario; the samplers `saturation` and `limitador-counters` serve all of them.

| Demo id | Stress drivers | Status |
|---|---|---|
| claude-code-sovereign | `claude-code-sovereign`, `-state` | replayed (Praxis workstation entry; spends the Praxis budget, one request at a time; needs the egress opening of WP-308) |
| dify | `dify`, `dify-state` | replayed (through its token proxy) |
| kagent | `kagent`, `kagent-state` | replayed (through its token proxy) |
| lightspeed | `lightspeed-state` | state only; not replayed: the assistant needs an OpenShift token a Job does not have |
| openclaw | `openclaw-state` | state only; not replayed: its path is the operator's egress proxy inside each persona's pod |
| open-webui | `open-webui`, `open-webui-zuno-code`, `open-webui-zuno-wesh`, `open-webui-state` | replayed (Open WebUI's API as a stress persona) |
| unifai-agents | `unifai-agents`, `unifai-agents-state`, `load-unifai-scenarios` | replayed; the load driver replays the active agents' scenarios as concurrent turns |
| unifai-live-rag | `unifai-live-rag`, `unifai-live-rag-state` | state check in the profiles; the `unifai-live-rag` driver is mutating and opt-in (profile `mutating`, as `stress-mutate-01`): it uploads one small, uniquely named document to the persona's Personal library, waits until it is indexed, then deletes it and checks it is gone |
| blender-3d | `blender-3d`, `blender-3d-state` | replayed (device sign-in, then the workstation entry); skipped when the entry is off |
| world-model | `world-model-state` | state only (one assertion); not deployed on demand, no replay driver |
| aap-audited-operations | `aap-audited-operations-state` | state only |
| gitops-day0-3 | `gitops-day0-3-state` | state only |
| image-signing-admission | `image-signing-admission-state`, `image-signing-refusal` | state check in the profiles; `image-signing-refusal` is opt-in (profile `mutating`) and stores nothing: it offers an unsigned, tag-referenced image as a dry-run pod create to the namespace `zuno-stress-admission`, and the admission webhook must refuse it. The namespace and its one pod-create grant exist only when `stressImageProof.enabled` is set (default off) |
| observability-trace | `observability-trace`, `observability-trace-state` | replayed (a Tekos turn, then its trace read in Tempo by run id) |
| okf-signed-agent-release | `okf-signed-agent-release-state` | state only |
| service-mesh-kiali | `service-mesh-kiali-state` | state only |
| vault-pki | `vault-pki-state` | state only |
| a2a-delegation-approval | `delegation-approval`, `a2a-delegation-approval-state` | state check in the profiles; the `delegation-approval` driver is mutating and opt-in (profile `mutating`, as `stress-mutate-01`): it asks Arkos for a delegated write, rejects the pending approval (never approves it), checks that a stale request id answers 409, and cancels and deletes its session |
| agents-alt-gateway | `agents-alt-gateway-state` | state only; pending Phase 58 (the kagent agent on Praxis is not rolled out, so that object is not judged) |
| ai-gateway-routing | `ai-gateway-routing`, `ai-gateway-routing-state` | replayed (one `zuno-code` call, routing decision read back) |
| ai-gateway-sovereignty | `ai-gateway-sovereignty`, `ai-gateway-sovereignty-state` | replayed (Arkos kept local at C3, Tekos control call) |
| guardrails | `guardrails`, `guardrails-state` | replayed (the DAN prompt, its span read in Tempo) |
| identity-personas | `identity-personas`, `identity-personas-state` | replayed in part: the stress persona's Keycloak token, with its issuer, client, expiry and number of groups read (the signature is checked by the gateways, not here) |
| mcp-tools-by-group | `mcp-tools-by-group`, `mcp-tools-by-group-state`, `load-mcp-gateway` | replayed (`search_confluence` through the REST path; the load driver varies the queries) |
| multi-gateway | `multi-gateway`, `multi-gateway-state` | replayed in part: one short question through the ai-gateway and one through Praxis (device sign-in of the public client `claude-code`), one row each; the state check stays pending Phase 58 for the kagent agent on Praxis (WP-297 to WP-303) |
| quotas | `quotas`, `quotas-state` | state check in the profiles; the `quotas` driver is mutating (it spends a stress persona's budget until a 429) and is in no profile |
| evaluation-trustyai-evalhub | `evaluation-trustyai-evalhub-state` | state only |
| external-models | `external-models-state` | state only |
| genai-playground | `genai-playground-state` | state only |
| lora-pipeline-mlflow-kueue | `lora-pipeline-mlflow-kueue-state` | state only |
| maas-portal-api-keys | `maas-portal-api-keys`, `maas-portal-api-keys-state` | replayed in part: the MaaS entry must refuse a `/v1/models` call without an API key (the 2:15 step); needs egress to the MaaS route |
| model-catalog-registry | `model-catalog-registry-state` | state only (demo333 has no ModelRegistry instance) |
| model-serving-llmd-mig | `model-serving-llmd-mig-state` | state only; the model path itself is loaded by `load-ai-gateway` and watched by the `saturation` sampler |
| five-experiences, three-experiences | the drivers of the experience scenarios they list | composition: no driver of their own |
| agentic-ai, rhoai-end-to-end, sovereign-governed-ai, trusted-platform-ops (workshops) | none | compositions of scenarios: no driver of their own |

## Personas

The demonstrations sign in with fictional role accounts of the Keycloak realm `zuno`
([ADR-0349](../adr/0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md)). They are role names, not
people. They share one password, kept in Vault at `keycloak/demo-personas`; it is never written in these pages.
Groups drive everything a persona can do: which agents it may call, which tools it gets, which model budget it holds,
and what it may see on the cluster. Source of truth: `gitops/charts/keycloak/files/realm-zuno.json`.

| Persona | Profile | Keycloak groups | Used in the demonstrations |
|---|---|---|---|
| **sale-01** | Salesperson, front office | `sales`, `agent_comage`, `agent_finage` | Open WebUI (three tools, named when asked), OpenClaw (its own assistant, no Confluence), the shared budget, RAG isolation |
| **sale-02** | Salesperson, front office | `sales`, `agent_comage`, `agent_soursage` | not used yet |
| **consultant-01** | Consultant and architect, front office | `consultant` with six Confluence subgroups, `agent_comage`, `agent_tekos`, `agent_arkos`, `agent_naveo`, `aap_admin` | UnifAI live RAG; copied by the probe identity `eval-consultant-01` |
| **consultant-02** | Consultant and architect, front office | `consultant` with Confluence build OpenShift and OpenShift AI and the four architecture spaces, `agent_tekos`, `agent_arkos`, `aap_ops` | UnifAI, Dify, OpenClaw (with Confluence), the Open WebUI contrast, delegation with approval |
| **consultant-03** | Consultant (run), front office | `consultant` with Confluence run OpenShift and Keycloak, `agent_tekos`, `aap_reader` | not used yet |
| **finance-01**, **finance-02** | Finance, middle office | `finance`, `agent_finage` | the tools contrast (Drive and Gmail only) |
| **adv-01**, **adv-02** | Sales administration, middle office | `adv`, `agent_advantage` | not used yet |
| **board-01**, **board-02** | Executive board, back office | `board`, `agent_advantage`, `agent_finage`, `agent_cognos` | not used yet |
| **recrut-01** | Recruiter, back office | `recrut`, `agent_comage`, `agent_soursage` | not used yet |
| **ai-dev-01** | AI developer, back office | `ocp-ai-dev` (edit on the Zuno namespaces), `agent_tekos` | MaaS key, Blender, the playground (no tools) |
| **ai-ops-01** | AI platform operator, back office | `ocp-ai-ops` (admin on the Zuno namespaces), `agent_tekos`, `openwebui_admin` | kagent, Tekos with cluster tools, Grafana and Tempo, the world model, the playground (nine tools) |
| **paas-dev-01** | Platform developer, back office | `ocp-paas-dev` (cluster-reader), `agent_tekos`, `aap_ops` | not used yet |
| **paas-ops-01** | Platform operator, back office | `ocp-paas-ops` (cluster-admin), `agent_tekos`, `aap_admin`, `openwebui_admin` | the presenter's `oc` terminal: probes and cluster-wide checks |

An OpenShift group is created when its first member signs in. On 2026-11-12, **sale-01** and **paas-ops-01** had never
signed in to OpenShift on demo333: sign each persona in once before a session that needs its OpenShift rights
(Lightspeed, the MaaS portal, the presenter's terminal).

Other identities, never signed in on stage:
- `eval-consultant-01` and the other `eval-*` accounts are copies used by the golden-path probes and the evaluations.
- The `*-entitlement-only-user-01` and `*-role-only-user-01` accounts are negative fixtures for access-denied tests.
- `dify-admin@zuno.local` is Dify's local administrator (Vault `zuno/dify/admin`).
- Some experiences call the platform as a service account that carries exactly the groups of one persona:
  - `service-account-dify` and `service-account-openclaw-consultant-02` act as **consultant-02**;
  - `service-account-openclaw-sale-01` acts as **sale-01**;
  - `service-account-kagent` acts as **ai-ops-01**.

## Operations documents

- [Golden path](golden-path.md): the automated probes and the screens to check before a live session.
- [Freeze protocol](freeze-protocol.md): what stops changing before a demonstration day.
- [Rollback](rollback.md): how to roll back an experience or a gateway.
- [Stresstest](../platform/stresstest.md): the profile-driven campaign that replays the scenarios (the table above says which driver replays which).
- [Demo day 2026-11-09](demo-day-2026-11-09.md): the runbook of that day, kept as a record and as an example.
