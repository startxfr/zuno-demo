# v0.3 roadmap decisions (ADR-0301 – ADR-0309; see also ADR-0326, ADR-0327, ADR-0340, ADR-0342, ADR-0353)

- **Status:** Proposed
- **Target:** v0.3
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

v0.3 rolls the single-agent pattern v0.2 established (see [adr-decisions-v0.2.md](adr-decisions-v0.2.md)) out to the four remaining agents - Arkos, Comage, Advantage and Finage - using the same shared platform rather than forks.

Consolidated from 9 individual ADR files, plus four further decisions promoted to full records once the multi-agent rollout needed them (ADR-0326, ADR-0327, ADR-0340, ADR-0342, listed at the end of this file). Each entry below is its own immutable decision record, citable as `ADR-0NNN`; only the Decision line is unique per entry - [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

### ADR-0301: Introduce LoRA and PEFT model customization

Promoted to a full decision record: see [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) (`ansible/roles/mlops` needed a real design to scaffold against).

### ADR-0302: Build dataset-to-model MLOps pipelines

Promoted to a full decision record: see [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md).

### ADR-0303: Support dynamic LoRA adapter loading

Promoted to a full decision record: see [ADR-0303](0303-support-dynamic-lora-adapter-loading.md) (WP-39 implementation).

### ADR-0304: Optimize model selection using quality cost and latency

Promoted to a full decision record: see [ADR-0304](0304-optimize-model-selection-using-quality-cost-and-latency.md) (WP-40 implementation).

### ADR-0305: Introduce automated model benchmarking

Promoted to a full decision record: see [ADR-0305](0305-introduce-automated-model-benchmarking.md) (WP-40 implementation).

### ADR-0410: Expand the agent catalog beyond the initial five agents

Promoted to a full decision record and re-streamed to v0.4 as ADR-0410, formerly ADR-0306 (2026-08-15): see [ADR-0410](0410-expand-the-agent-catalog-beyond-the-initial-five-agents.md) (WP-41 implementation).

### ADR-0307: Support self-service agent onboarding

Promoted to a full decision record: see [ADR-0307](0307-support-self-service-agent-onboarding.md) (WP-41 implementation).

### ADR-0308: Expand agent lifecycle management through the AIAgent Operator

Promoted to a full decision record: see [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md) (WP-38 implementation).

### ADR-0309: Introduce policy-driven autonomous optimization

Promoted to a full decision record: see [ADR-0309](0309-introduce-policy-driven-autonomous-optimization.md) (WP-42 implementation).

### ADR-0326: Generalize the Tekos vertical slice to the four remaining agents

Promoted to a full decision record: see [ADR-0326](0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md).

### ADR-0327: Define the AIAgent CRD reconciliation contract before implementing the operator

Promoted to a full decision record: see [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md).

### ADR-0340: Extend business-role authorization with CDP and scoped capabilities

Promoted to a full decision record: see [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md).

### ADR-0342: Support multiple agent graph shapes in Agent Runtime

Promoted to a full decision record: see [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md).

### ADR-0353: Support an optional external registry as the first-party runtime image source

Decide whether/how gitops charts may optionally source first-party runtime images from Quay (or another external registry) instead of the in-cluster mirror + BuildConfig default ADR-0115 leaves unchanged - and, if adopted, how that differs from ADR-0352's "internal vs external" axis (which governs who deploys platform infrastructure services, not where first-party application images come from).
