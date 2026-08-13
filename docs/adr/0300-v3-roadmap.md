# v3 roadmap decisions (ADR-0301 – ADR-0309; see also ADR-0326, ADR-0327, ADR-0340, ADR-0342)

- **Status:** Proposed
- **Target:** v3
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

v3 rolls the single-agent pattern v2 established (see [0200-v2-roadmap.md](0200-v2-roadmap.md)) out to the four remaining agents - Arkos, Comage, Advantage and Finage - using the same shared platform rather than forks.

Consolidated from 9 individual ADR files, plus four further decisions promoted to full records once the multi-agent rollout needed them (ADR-0326, ADR-0327, ADR-0340, ADR-0342, listed at the end of this file). Each entry below is its own immutable decision record, citable as `ADR-0NNN`; only the Decision line is unique per entry - [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

### ADR-0301: Introduce LoRA and PEFT model customization

Promoted to a full decision record: see [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) (`ansible/roles/mlops` needed a real design to scaffold against).

### ADR-0302: Build dataset-to-model MLOps pipelines

Promoted to a full decision record: see [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md).

### ADR-0303: Support dynamic LoRA adapter loading

Share base models while selecting approved task/agent adapters dynamically.

### ADR-0304: Optimize model selection using quality cost and latency

Continuously improve routing using measured operational and evaluation signals.

### ADR-0305: Introduce automated model benchmarking

Benchmark candidate models before routing-policy promotion.

### ADR-0306: Expand the agent catalog beyond the initial five agents

Demonstrate that the generic platform supports broader enterprise agent onboarding.

### ADR-0307: Support self-service agent onboarding

Provide controlled templates, validation and workflows for teams to define new agents.

### ADR-0308: Expand agent lifecycle management through the AIAgent Operator

Automate more lifecycle, policy and deployment reconciliation around agent definitions.

### ADR-0309: Introduce policy-driven autonomous optimization

Allow bounded automated tuning of routing, caching and model choices under explicit governance.

### ADR-0326: Generalize the Tekos vertical slice to the four remaining agents

Promoted to a full decision record: see [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md).

### ADR-0327: Define the AIAgent CRD reconciliation contract before implementing the operator

Promoted to a full decision record: see [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md).

### ADR-0340: Extend business-role authorization with CDP and scoped capabilities

Promoted to a full decision record: see [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md).

### ADR-0342: Support multiple agent graph shapes in Agent Runtime

Promoted to a full decision record: see [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md).
