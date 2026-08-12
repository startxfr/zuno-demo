# v3 roadmap decisions (ADR-0301 – ADR-0309)

- **Status:** Proposed
- **Target:** v3
- **Date:** 2026-08-04
- **Decision owners:** Zuno Demo architecture team

Consolidated from 9 individual ADR files. Each entry below is its own immutable decision record, citable as `ADR-0NNN`; only the Decision line is unique per entry - [Standard clauses](README.md#standard-clauses) (Context, Alternatives, Consequences, Security/Operational considerations, Migration/evolution, Related ADRs) apply to every entry unless overridden here.

### ADR-0301: Introduce LoRA and PEFT model customization

Allow efficient task/domain adaptation, starting with Comage candidate use cases.

### ADR-0302: Build dataset-to-model MLOps pipelines

Automate dataset preparation, training, evaluation, registry and deployment.

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
