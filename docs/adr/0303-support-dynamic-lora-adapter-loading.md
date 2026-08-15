# ADR-0303: Support dynamic LoRA adapter loading

- **Status:** Partially implemented (request-level selection and guards merged; GPU verification pending)
- **Target:** v0.3
- **Date:** 2026-08-15
- **Decision owners:** Zuno Demo architecture team

## Decision

Share base models while selecting approved task/agent adapters
dynamically (the stub decision, promoted verbatim from
`docs/adr/0300-v0.3-roadmap.md`).

The AI Gateway resolves the serving target per request: an agent/task
whose model-routing policy declares an approved adapter is routed to
that adapter module on the shared vLLM runtime (vLLM multi-LoRA
request-level selection); requests without a declared adapter use the
base model. Adapter approval remains a reviewed GitOps change (ADR-0302's
promotion rule); a C2/C3-classified adapter is only selectable on serving
paths already authorized for that classification (ADR-0021/0034).
Selection is recorded in traces and usage metering.

See [Standard clauses](README.md#standard-clauses) for Context,
Alternatives, Consequences, Security/Operational considerations,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0301](0301-introduce-lora-and-peft-model-customization.md)
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md)
- [ADR-0304](0300-v0.3-roadmap.md#adr-0304-optimize-model-selection-using-quality-cost-and-latency)
