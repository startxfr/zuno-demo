# ADR-0534: Integrate TrustyAI for AI evaluation and guardrails

- **Status:** Implemented
- **Target:** v0.7
- **Date:** 2026-08-30
- **Decision owners:** Zuno Demo architecture team

## Context

Zuno-demo runs multiple AI agents on shared AI services, models, RAG sources and external tools
(MCP). As the platform grows, model availability alone is not sufficient. Zuno also needs
mechanisms to evaluate AI response quality, evaluate RAG effectiveness, detect unsafe or malicious
prompts, protect against jailbreak and prompt injection, apply input/output filters, evaluate
model and agent security, and compare models using reproducible evaluations.

TrustyAI, OpenShift AI's evaluation/guardrails operand, is **already part of this platform**: it is
declared `Managed` on the `DataScienceCluster` (`gitops/charts/openshift-ai/values.yaml`,
`spec.components.trustyai`) and already backs ADR-0108/WP-10's `LMEvalJob` model-benchmarking gate
(Implemented, with four documented upstream 3.5.0-ea.2 operator bugs found and worked around live).
Its `mcpGuardrailsMode` field already exists on that spec and is currently `false` - the guardrails
half of the operand has never been turned on. This decision is therefore about **extending** an
already-integrated capability from benchmarking-only to evaluation-and-guardrails, not about
introducing TrustyAI to the platform.

TrustyAI does not replace the platform's existing components. The real request/response path
(`docs/architecture/logical-architecture.md`, `docs/architecture/ai-architecture.md`) is:

```text
Agent Frontend -> Agent BFF -> Agent Runtime
Agent Runtime -> RAG Service       (retrieval, pgvector)
Agent Runtime -> MCP Gateway       (tool invocation)
Agent Runtime -> AI/Inference Gateway -> {local models (KServe/MaaS), approved SaaS models}
```

Agent Runtime, not the AI/Inference Gateway, is where RAG results, MCP tool calls and the final
response converge - the AI/Inference Gateway only sees raw model routing/fallback/quota. Since
several of this ADR's objectives (RAG quality, jailbreak/prompt-injection detection on the full
exchange, MCP-guardrails) need that converged context, TrustyAI must observe Agent Runtime's
boundary, not only the AI/Inference Gateway's.

## Decision

Zuno-demo will progressively extend its existing TrustyAI integration from model benchmarking
(ADR-0108) to evaluation and guardrails, hooking in **in front of Agent Runtime** so it can
evaluate the full agent exchange - retrieved RAG context, MCP tool use and the final response -
not just raw model calls. The AI Gateway keeps sole responsibility for model routing/fallback/
quota; TrustyAI adds an evaluation/guardrail layer alongside it, never inside it.

```text
Agent
  |
  v
Agent Runtime -----------------------------+
  |                                        |
  +--> RAG Service                         |
  +--> MCP Gateway                         v
  +--> AI/Inference Gateway --> Model   TrustyAI
                                        evaluation & guardrails
                                        (quality / RAG / security)
```

The integration proceeds in three phases.

**Phase 1 - Extend the existing TrustyAI enablement (informal target: v0.5).** TrustyAI is already
`Managed` and already serves LM-Eval (ADR-0108). This phase only:
- confirms the operand's health beyond the LM-Eval path already exercised (`oc get
  datasciencecluster zuno-dsc`, TrustyAI component conditions);
- documents the existing `spec.components.trustyai` block (`eval.lmeval`, `mcpGuardrailsMode`) as
  the shared configuration surface this ADR will extend, rather than re-declaring it;
- introduces no agent-specific evaluation logic yet.

This phase is a platform-readiness check on top of what already exists, not a new enablement: it
installs no new operator, `Subscription` or `OperatorGroup` - the entire TrustyAI operand already
lives inside the existing Day 1 `openshift-ai` component, and this phase touches nothing there
beyond documentation and a health check.

**Phase 2 - Evaluate and protect the AI chain (informal target: v0.6).**
*(Amended 2026-09-02, WP-108 live evidence: this phase originally said "flip `mcpGuardrailsMode`
on". That flip was executed and reverted the same hour - on this operand version the flag
redeploys the TrustyAI operator with `--enable-services NEMO_GUARDRAILS` only, killing the
LMEvalJob controller (an ADR-0108 regression), EvalHub, TrustyAIService and
GuardrailsOrchestrator; at `false` the operator already runs all five services, so the guardrails
capability this ADR wants was never actually off. `mcpGuardrailsMode` therefore stays `false`,
and Phase 2 uses the already-enabled `GuardrailsOrchestrator`/NeMo-guardrails/EvalHub surfaces
instead.)* Wire TrustyAI, observing Agent Runtime's boundary, to progressively
evaluate or control:
- RAG quality;
- response quality;
- jailbreak attempts and prompt injection;
- input and output filtering;
- sensitive or inappropriate content;
- model and agent security;
- general model behaviour and reliability.

Where relevant, standard TrustyAI/OpenShift AI evaluation frameworks - **LM-Eval** (already in use,
ADR-0108), **RAGAS** and **Garak** (both new to this repo) - are preferred over Zuno-specific
implementations.

```text
                 TrustyAI
                    |
       +------------+-------------+
       v            v             v
    Quality        RAG          Security
   evaluation   evaluation    evaluation
       |            |             |
    LM-Eval       RAGAS          Garak
```

These evaluations should eventually become part of the validation criteria used before an AI
configuration is considered suitable for Zuno agents.

**Phase 3 - Evaluate customized models (informal target: v0.7).** Extend the TrustyAI evaluation
chain to models customized by Zuno, especially models produced via PEFT/LoRA. The objective is not
only to verify that fine-tuning improves the targeted behaviour, but also to detect regressions in
existing capabilities: expected task quality, general response quality, RAG behaviour, tool/MCP
usage capability, security and jailbreak resistance.

```text
Base model
    |
    +--------------+
    v              v
baseline        PEFT/LoRA
evaluation        model
                    |
                    v
               evaluation
                    |
                    v
              comparison
```

A customized model must therefore not be adopted only because it performs better on its fine-tuned
task - it must also demonstrate that critical existing capabilities have not significantly
regressed.

## Non-goals

This decision does not replace ADR-0108's `LMEvalJob` benchmarking gate (Phase 2 extends it, does
not supersede it); does not move RAG/MCP orchestration out of Agent Runtime or into TrustyAI or the
AI/Inference Gateway; and does not itself define concrete evaluation datasets, thresholds or pass/
fail policies - those are left to later, phase-specific ADRs/WPs as noted below.

## Operational considerations

Phase 1 verification reads `spec.components.trustyai` conditions on the `zuno-dsc`
`DataScienceCluster`, the same object ADR-0108's `LMEvalJob` checks already depend on. Every
change to this operand must be validated the same way ADR-0108 validated `LMEvalJob`: a live run
against this cluster, not just a green sync - a rule WP-108 vindicated twice in one day
(`TrustyAIReady` stayed `True` while the flag rewrote the operator's whole enabled-services list,
and ArgoCD's `ignoreDifferences` on the DSC `/spec` means a values commit alone never reaches the
cluster - a manual `oc patch` is required). Day-2/Day-3 check wiring
(`make d2/d3 check trustyai` or equivalent) should follow the existing `models`/`trustyai`
precheck pattern in `ansible/roles/models/tasks/precheck.yml` rather than inventing a new one.

The new frameworks and wiring this ADR introduces (RAGAS, Garak, the Agent Runtime guardrail
hooks) are carried by a new Day 2 component, `trustyai-config`, mirroring the `aap`/`aap-config`
and `lightspeed`/`lightspeed-config` split (own chart, own Ansible role, own `-d0`/`-d1` Application
pair). This is distinct from `spec.components.trustyai` itself, which stays inside the existing Day
1 `openshift-ai` component - `trustyai-config` has no Day 1 half of its own because there is no
separate operator to install.

Two visibility clarifications from the 2026-09-02 human live test (which failed on exactly this
point - the chain worked but was invisible in every UI, spawning WP-113):
- The RHOAI dashboard's only TrustyAI surface, the per-project "Model monitoring bias" card
  ("Configure TrustyAI service"), configures a `TrustyAIService` CR - the predictive-model
  bias/fairness monitoring service. It is **deliberately left unconfigured**: it is unrelated to
  this ADR's generative evaluation/guardrails scope, and configuring it would only make the card
  look populated while monitoring nothing. Do not "fix" the empty card.
- None of this ADR's real artifacts (`LMEvalJob`, `GuardrailsOrchestrator`, the Garak/RAGAS Jobs,
  the observe-only detections) appear anywhere in the RHOAI dashboard on this release train. The
  intended observability surface is the `zuno-trustyai` Grafana dashboard (WP-113): guardrails
  and evaluation results pushed as metrics through the platform's standard OTLP pipeline
  (ADR-0029), alongside CLI/`make d3 check trustyai-config`.

Guardrail enforcement (the `GuardrailsOrchestrator`/NeMo detectors and the Agent Runtime
evaluation hooks) starts in observe/log-only mode: evaluations run and are recorded, but no request is blocked on their
result. Flipping any of this to blocking enforcement is a deliberate, separate decision made once
observation has produced enough evidence to set thresholds without an unacceptable false-positive
rate - it is not part of this ADR's initial rollout and is not required for WP-107/WP-108/WP-109 to
be considered done.

## Migration / evolution

This decision is executed by three WPs: [WP-107](../roadmap/work-packages/wp-107-trustyai-baseline-verification-and-config-scaffold.md)
(Phase 1 - baseline verification and the `trustyai-config` scaffold), [WP-108](../roadmap/work-packages/wp-108-trustyai-ragas-garak-guardrails-enablement.md)
(Phase 2, infrastructure half - Garak and built-in guardrails-detector smoke enablement,
observe-only, not yet wired to real agent traffic; its live run is what refuted the
`mcpGuardrailsMode` premise and found the RAGAS gap - RAGAS moved to WP-109 with the wiring),
and [WP-109](../roadmap/work-packages/wp-109-trustyai-zuno-stack-integration-and-model-comparison.md)
(Phase 2's Zuno-specific wiring at the Agent Runtime boundary, merged with Phase 3's PEFT/LoRA
comparison gate rather than scheduled as a separate WP - a decision made when these WPs were
authored, since both extend the same evaluation chain onto Zuno-specific content). A fourth WP,
[WP-113](../roadmap/work-packages/wp-113-trustyai-observability-dashboard.md), was added
2026-09-02 after the human live test of the implemented chain failed on UI visibility: it gives
the chain its Grafana observability surface (see Operational considerations). Concrete
evaluation datasets, thresholds and evaluation policies beyond what these three WPs establish are
still left to later ADRs/WPs as the Zuno architecture matures, as is any move from observe-only to
blocking guardrail enforcement.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Consequences,
Security considerations, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0108](0108-automate-model-evaluation-with-lm-eval.md) - the existing TrustyAI/LM-Eval
  integration this decision extends from benchmarking-only to evaluation-and-guardrails.
- [ADR-0107](0107-introduce-automated-model-quality-gates.md) - the model quality gate LM-Eval
  results already feed, and that Phase 2/3's RAGAS/Garak/PEFT-LoRA results should extend.
- [ADR-0010](0010-introduce-a-central-mcp-gateway.md),
  [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md) - the MCP Gateway boundary
  Phase 2's guardrails sit alongside, not inside.
