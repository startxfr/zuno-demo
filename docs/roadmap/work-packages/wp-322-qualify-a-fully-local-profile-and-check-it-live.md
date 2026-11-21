# WP-322: Qualify a fully local profile and check it live

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** WP-319, WP-320
- **Related:** [ADR-0021](../../adr/0021-route-models-according-to-c1-c2-c3-classification.md), [ADR-0020](../../adr/0020-support-both-local-and-external-llm-providers.md), [ADR-0541](../../adr/0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md), [ADR-0417](../../adr/0417-consume-codestral-via-mistral-api.md), [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- **Target:** v0.19
- **Estimated files touched:** ~10: a profile overlay, a check script and its schedule, tests, this brief

## Goal

One deployment profile with no external inference, enforced and checked on a schedule.

Horizon in the ADR's indicative roadmap: Day 30-60. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Disable external inference through the profile, not role by role.
2. Qualify the local dependencies the profile needs and its policy enforcement.
3. Write the recurring check that compares the live cluster with its declared profile: egress destinations, model providers, registries, trust roots and every guardrail that is switched off.

## Existing work it builds on

- Classification routing ([ADR-0021](../../adr/0021-route-models-according-to-c1-c2-c3-classification.md)) and the provider list of [ADR-0020](../../adr/0020-support-both-local-and-external-llm-providers.md), [ADR-0541](../../adr/0541-integrate-mistral-and-gpt-oss-120b-as-maas-externalmodels.md) and [ADR-0417](../../adr/0417-consume-codestral-via-mistral-api.md) (finding F3).
- The day-0 modes of [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md) and the overlays of WP-320.
- The acceptance tests of WP-319.

## Acceptance

- With the profile applied, a call to any external model is refused at the gateway and at the network boundary.
- A failure does not fall back to a weaker profile (finding F7).
- The live check reports a switched-off control as a dated exception.
