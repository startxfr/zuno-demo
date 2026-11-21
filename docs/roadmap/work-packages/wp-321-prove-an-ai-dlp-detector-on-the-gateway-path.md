# WP-321: Prove an AI DLP detector on the gateway path

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** WP-319
- **Related:** [ADR-0034](../../adr/0034-compute-effective-classification-from-the-complete-context.md), [ADR-0035](../../adr/0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0567](../../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md), [ADR-0540](../../adr/0540-express-guardrail-policy-as-nemo-rails-configuration.md), [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md)
- **Target:** v0.19
- **Estimated files touched:** ~8: a detector configuration, tests, an evidence file, this brief

## Goal

A controlled proof of concept of content detection (personal data, secrets, identifiers) on one gateway path, with measured quality.

Horizon in the ADR's indicative roadmap: Day 30-60. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Evaluate the candidate detectors (Microsoft Presidio, deterministic secret detection, a local classifier), including the rate of empty or unparseable verdicts (finding F6).
2. Wire one detector on one path as a proof of concept. Detection may raise the classification and never lowers it.
3. Write negative tests for sensitive-data disclosure.
4. Measure false positives, false negatives, latency and multilingual coverage.

## Existing work it builds on

- The classification rules already in force: [ADR-0034](../../adr/0034-compute-effective-classification-from-the-complete-context.md), [ADR-0035](../../adr/0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), and the signed markers of [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md).
- The NeMo Guardrails integration in the ai-gateway ([ADR-0540](../../adr/0540-express-guardrail-policy-as-nemo-rails-configuration.md), [ADR-0567](../../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md)). The proof of concept extends it or sits next to it; it does not replace it.

## Acceptance

- A detector that cannot reach a verdict blocks or escalates, and the test proves it.
- The measurements are recorded with their date and the serving stack used.
