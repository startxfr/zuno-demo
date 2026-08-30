# ADR-0303: Support dynamic LoRA adapter loading

- **Status:** Superseded by ADR-0526 for the serving mechanism it depends on (ADR-0301 decision 1, itself unconditionally superseded); the request-level adapter-selection code, classification guard and tracing/metering attribute (WP-39) stay merged and correct but exercise a mechanism the project's only real customization case did not use, and no other candidate is planned. Prior status for the record: Partially implemented (request-level selection and guards merged; GPU verification pending).
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

## Evolution (2026-08-30)

This ADR's mechanism only makes sense on top of ADR-0301 decision 1 (adapters
served through vLLM's native multi-LoRA, `--enable-lora`/`--lora-modules`, one
shared base-model deployment carrying several registered adapters). ADR-0301's
own Status line already declares that decision 1 is superseded by ADR-0526
without qualification — not "superseded for the wesh case," the serving
mechanism itself. ADR-0303 has no foundation left without it, so its Status
is reclassified `Superseded` to match, rather than staying `Partially
implemented` behind a note that it is merely waiting on a future candidate.

ADR-0526's own `## Alternatives considered` section rejected keeping decision
1 intact for reasons that are not specific to the wesh case: serving one
adapter via `--enable-lora` on a dedicated pod costs the same GPU as merging
and serving it as its own model, no adapter-download mechanism exists in
`gitops/charts/models` to load a registered adapter onto a serving pod in the
first place, and a shared instance exposing both the base and adapter model
ids makes routing/telemetry ambiguous for no compensating benefit. A scan of
the v0.4–v0.7 roadmap and every pre-live agent's `NEXT_STEPS.md` (cognos,
naveo, soursage) found no declared future need for a second adapter either.

Kept honest: ADR-0526's own `## Consequences` section states this mechanism
is "neither implemented nor contradicted; it is bypassed" — a deliberate
choice not to declare it dead outright. The structural case for multi-LoRA
sharing (several small adapters on one deployment, relevant if GPU capacity
stays exactly saturated — `zuno-ai-run`'s MIG quota is 3/3 mig-1g.24gb, 2/2
mig-2g.48gb per ADR-0526's Consequences) remains real in principle. Reviving
this mechanism needs a new ADR decision backed by a genuinely new, non-merged
adapter and an actual multi-adapter-sharing need — not an assumption baked
into "Operator pending."

This corrects the 2026-08-29 "keep frozen, Partially implemented" decision
recorded in this repo's root `MEMORY.md`, and this file's own earlier
2026-08-30 Evolution note (same day, same session) which had not yet drawn
this conclusion.

## Related ADRs

- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0034](0034-compute-effective-classification-from-the-complete-context.md)
- [ADR-0301](0301-introduce-lora-and-peft-model-customization.md)
- [ADR-0302](0302-build-dataset-to-model-mlops-pipelines.md)
- [ADR-0304](0300-v0.3-roadmap.md#adr-0304-optimize-model-selection-using-quality-cost-and-latency)
- [ADR-0526](0526-fine-tune-and-serve-a-french-urban-register-model-variant.md) — supersedes the ADR-0301 serving mechanism this ADR depends on; see Evolution above
