# ADR-0545: Scope the remaining RHOAI/Kubeflow component adoption - finalize TrainJob, explore Kueue priority, evaluate InferenceGraph, exclude NIM

- **Status:** Accepted
- **Target:** v0.7
- **Date:** 2026-09-03 (amended 2026-09-03)
- **Decision owners:** Zuno Demo architecture team

## Context

A live inventory of every RHOAI-managed CRD actually instantiated in the cluster (`zuno-dsc`,
15 `Managed` components plus the standalone Kueue operator) turned up roughly twenty Kind with
zero instances. Rather than adopt any of them "because they are there," each was checked against
three things: existing ADR/roadmap decisions that already ruled on it, the real needs of the six
OKF agents (Tekos/Arkos/Comage/Advantage/Finage/Naveo), and the cluster's actual GPU topology
(two permanent MIG nodes, `zuno-gpu-a`/`zuno-gpu-c`, each `mig-1g.24gb`x2 + `mig-2g.48gb`x1, plus
one scale-from-zero burst node for training, ADR-0351).

Most of the list turned out to be either a deliberate prior rejection or structurally
inapplicable here (see Decision 5). Four items carried a genuine, previously-undecided signal and
were arbitrated directly with the demo's owner:

1. **TrainJob** (Kubeflow Trainer) - ADR-0539 already designed KFP-submitted LoRA training
   compute but shipped it disabled (`training.trainJob.enabled: false`, WP-119).
2. **WorkloadPriorityClass** (Kueue) - the GPU `ResourceQuota` is saturated
   (`mig-1g.24gb` 3/3, `mig-2g.48gb` 2/2, ADR-0542/WP-121) and client-facing agent inference
   shares one `LocalQueue` with internal batch (MMLU/garak/ragas evaluations, day2-stresstest)
   with no priority differentiation.
3. **InferenceGraph** (KServe) - Arkos already chains multiple model calls
   (`draft_node`→`reflect_node`, RAG embed retrieval, pre/post guardrails) but entirely inside
   `agent-runtime`'s own LangGraph code, never as a declarative KServe composition.
4. **NVIDIA NIM** - the `kserve.nim` sub-component is `Managed` on the DSC with no `Account`
   configured; it is a proprietary, NGC-licensed model catalog.

A further finding, made while scoping item 3: `default_reranker_model` is unset in
`components/rag-service`'s OGX configuration (`_validate_reranker_model` only runs when one is
declared, ADR-0322). No reranker is served today - only the `embeddings` `InferenceService`
exists. The real first question for InferenceGraph is therefore not "how to compose
embed→rerank" but "do we want a reranker at all."

## Decision

1. **Finalize TrainJob (WP-126).** Lift ADR-0539's "shipped disabled" state: flip
   `training.trainJob.enabled: true` in `gitops/charts/mlops/values.yaml`, verify the
   scale-from-zero probe for the JobSet-owned pod on `zuno-gpu-burst-a`, then run one real LoRA
   training end to end. This is infra already designed and merged (WP-119) - the only remaining
   work is turning it on and proving it live. Chosen over leaving it dormant indefinitely: the
   Kubeflow Trainer controller has had 15 usable `ClusterTrainingRuntime`s and zero consumers
   since install, and a designed-but-never-run mechanism is exactly the kind of drift this repo's
   own conventions (ADR-0323, `check_docs.py`) exist to catch elsewhere.
2. **Explore Kueue-aware priority ordering for `zuno-ai-run`'s batch Jobs (WP-127).** Design (not
   yet apply) a small set of priority tiers so quality/security-gate batch Jobs are never queued
   behind lower-stakes batch under a saturated GPU quota. Scoped as research/design first, not a
   live change: the quota-saturation problem is real and measured (ADR-0542), but the right tier
   boundaries are not yet known and a wrong first cut would be disruptive to reverse under
   production load.

   *Amended 2026-09-03 (WP-127)* - the original text above named `WorkloadPriorityClass` and
   framed the goal as protecting agent-serving inference from batch delay. Both are corrected by
   what WP-127's own research found: `LLMInferenceService` predictors are not Kueue-managed at
   all (`kueueOperand.integrationFrameworks: [BatchJob]` is the only integration enabled, per
   `gitops/charts/kueue/values.yaml`) - Kueue cannot delay a workload it never admits, so
   protecting serving from batch is not achievable through Kueue and is not this WP's goal.
   Separately, Kueue was found to already derive a `Workload`'s `spec.priority` from the pod's
   standard Kubernetes `priorityClassName` (live-proven: `day2-stresstest-*` Jobs, which set
   `priorityClassName: zuno-platform-weak`, get `spec.priority: 1`; every other batch Job in
   `zuno-ai-run` - LMEval MMLU, its cache-prefetch, `job-garak-security`, `job-garak-smoke`,
   `job-ragas-eval` - sets no `priorityClassName` and gets `spec.priority: 0`), so introducing a
   new Kueue-native `WorkloadPriorityClass` CRD would duplicate a mechanism that already works.
   The corrected goal: reuse the existing `PriorityClass` hierarchy
   (`gitops/charts/admin-context/templates/priorityclass-*.yaml`) to order batch Jobs against each
   other - concretely, today's quality/security-gate Jobs (MMLU, garak-security, ragas) sit at
   `spec.priority: 0`, *below* the day2-stresstest drills at `1`, which is not intentional and is
   the real problem this WP now targets. Protecting agent-serving from GPU contention is a
   separate, native-Kubernetes concern (`ResourceQuota`/pod-preemption, not Kueue) and is logged
   here as a candidate for a future ADR, not part of WP-127.
3. **Evaluate InferenceGraph for the RAG pipeline only (WP-128).** First resolve whether a
   reranker is wanted at all (none is served today); only if so, compare a declarative
   `InferenceGraph` composing `embeddings`→reranker against the status quo of composing them in
   `rag-service`/OGX application code. Arkos's `draft`→`reflect`/guardrails chaining explicitly
   stays out of this WP's scope and stays in `agent-runtime`: it is business/agent logic with
   conditional branching, budget clamping (ADR-0544) and classification-aware behavior, not a
   fixed graph of served models - InferenceGraph composes `InferenceService`s, not agent
   reasoning, and moving that logic into KServe would duplicate control agent-runtime already
   owns.
4. **Explicitly exclude NVIDIA NIM.** No WP, no exploration planned. NIM's catalog is proprietary
   and NGC-licensed, directly at odds with this platform's local/open-model, sovereignty-routed
   posture (ADR-0021/0114/0201/0414's C1/C2/C3 sovereignty framing). Recorded here so a future
   pass does not adopt it "by default" on the strength of `kserve.nim` already being `Managed` on
   the DSC.
5. **No action, explicitly motivated, on the rest of the inventoried gap:**
   - `LocalModelCache`/`LocalModelNamespaceCache`/`LocalModelNodeGroup`/`LocalModelNode` - already
     removed (WP-086) after an operator-vs-PV-binder write-conflict loop; re-enabling would
     reproduce a known incident for no identified benefit.
   - `TrustyAIService` (the bias/fairness root CR, distinct from the `LMEvalJob`/
     `GuardrailsOrchestrator`/`NemoGuardrails`/`EvalHub` chain already live) - deliberately left
     unconfigured per ADR-0534: it monitors predictive models, this platform serves generative
     ones.
   - `ProvisioningRequestConfig` (Kueue) - structurally blocked: the cluster's autoscaler cannot
     see `nvidia.com/mig-*` resources (ADR-0351), the same limitation that already forced
     `zuno-gpu-c` to become a permanent MIG node rather than an autoscaled one.
   - `Cohort`, `MultiKueue`/`MultiKueueConfig` - one `ClusterQueue`, one cluster; nothing to
     cohort or federate.
   - `TrainedModel`, `PyTorchJob`, `TFJob`, `MPIJob`, `XGBoostJob`, `PaddleJob`, `JAXJob`,
     `Viewer` - no distributed multi-node training need is documented anywhere in this repo;
     ADR-0539 confirms `numNodes: 1` suffices for the one real fine-tuning case (`-wesh`), and the
     only other attempted case (`comage-lora`) never ran for lack of data.
   - `AITenant` - not a design choice: it is a CR already correctly declared on the Zuno side
     (`spec.gateway.name: maas-default-gateway`) but invisible via `oc get aitenant -A` due to a
     upstream RHOAI bug already tracked in ADR-0541. Nothing new to decide here.
   - `ClusterServingRuntime` - purely operational (cluster-wide vs. namespaced runtime
     definitions); no need while the model catalog stays inside one namespace (`zuno-ai-run`).
   - `Topology` (Kueue) - weak signal only: two GPU nodes do span two AZs, but placement is
     already handled by the hand-authored MachineSet design (ADR-0351), and no Kueue-native
     topology need is documented.
   - `AdmissionCheck` (Kueue) - no external governance-gate need (budget approval, etc.) is
     identified anywhere in this repo.

   `Topology` and `AdmissionCheck` are not rejected on principle - they are unadopted for lack of
   a concrete driving need, and should be reconsidered if one appears (e.g. a materially deeper
   multi-AZ resilience requirement, or a cost-approval workflow).

## Non-goals

Executing any live cluster change as part of this ADR itself - decisions 1-3 are each tracked by
their own WP (WP-126/127/128), and each requires its own explicit go-ahead before touching the
cluster, consistent with how every prior GPU-node/quota-affecting WP in this stream (WP-117,
WP-121) was run. Negotiating or evaluating a NIM/NGC entitlement (decision 4 is a scope exclusion,
not a deferred evaluation). Revisiting `Topology`/`AdmissionCheck` absent a new concrete need.

## Operational considerations

- WP-126's live run triggers a real scale-up of the `zuno-gpu-burst-a` `MachineAutoscaler`
  (min 0/max 1) - a genuine node provisioning event, not a no-op flag flip, and must be confirmed
  before execution.
- WP-127's design must not regress the GPU-MIG `ClusterQueue`/`ResourceFlavor` quota ADR-0538
  decision 3 and WP-117 already established; it adds priority ordering within the existing quota,
  it does not resize it.
- WP-128 is pure research/recommendation; it produces no CR and touches no running service.

## Verification

- `platform/docs/check_docs.py` - PASS (this ADR's index row, target/section placement, and the
  three new WP tracker rows/briefs it introduces).
- WP-126/127/128 each carry their own acceptance checks in their briefs; none are claimed complete
  by this ADR.

## Migration / evolution

Each of decisions 1-3 gets its own future update, not a superseding ADR, as its WP concludes:
WP-126's live run updates ADR-0539's Status; WP-127's pilot recommendation feeds a future decision
on whether to apply the priority classes live; WP-128's recommendation feeds a future decision on
whether to deploy a reranker at all and, if so, how to compose it. Decision 4 (NIM exclusion) is
revisited only by a new ADR if a concrete client-facing need for NIM interoperability arises.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, and Review evidence.

## Related ADRs

- [ADR-0539](0539-delegate-lora-training-compute-to-a-kfp-submitted-trainjob.md),
  [ADR-0538](0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md) - the TrainJob
  mechanism decision 1 finishes turning on.
- [ADR-0542](0542-autoscale-one-served-model-through-llminferenceservice-spec-scaling.md),
  [ADR-0321](0321-delegate-kueue-lifecycle-to-the-red-hat-build-of-kueue-operator.md) - the
  saturated-quota context motivating decision 2's `WorkloadPriorityClass` exploration.
- [ADR-0322](0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md) - the
  RAG provider configuration decision 3's research starts from (`default_reranker_model` unset).
- [ADR-0534](0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md) - the `TrustyAIService`
  scope exclusion decision 5 reaffirms rather than reopens.
- [ADR-0351](0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md) -
  the MIG-blind-autoscaler limitation decision 5 cites against `ProvisioningRequestConfig`, and
  the burst node decision 1's live run uses.
- [ADR-0541](0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md) - the upstream
  `AITenant` visibility bug decision 5 points back to rather than re-litigates.
- [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md),
  [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md),
  [ADR-0414](0414-consolidate-zuno-ai-run-into-three-tiered-mig-predictors.md) - the sovereignty
  framing decision 4's NIM exclusion is grounded in.
