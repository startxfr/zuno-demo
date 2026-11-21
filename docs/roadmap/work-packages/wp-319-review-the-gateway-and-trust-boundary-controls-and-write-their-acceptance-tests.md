# WP-319: Review the gateway and trust-boundary controls and write their security acceptance tests

- **State:** Not started (proposed by ADR-0625 on 2026-11-21; the ADR is `Proposed`, so this work package is not approved)
- **ADRs:** [ADR-0625](../../adr/0625-evolve-zuno-toward-a-modular-sovereign-enterprise-ai-platform.md)
- **Depends on:** none
- **Related:** [ADR-0602](../../adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md), [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md), [ADR-0613](../../adr/0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md), [ADR-0035](../../adr/0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0036](../../adr/0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md), [ADR-0567](../../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md)
- **Target:** v0.19
- **Estimated files touched:** ~6: one review page, the negative tests, this brief

## Goal

A written review of the control paths of the three gateways, and a set of security acceptance tests that every later profile reuses.

Horizon in the ADR's indicative roadmap: Day 0-30. The horizons count from the start of an approved initiative. They are not calendar dates.

## Proposed work

1. Review local-by-default handling, fail-closed behaviour, signed context propagation, non-bypassable control paths, guardrails and privilege boundaries.
2. List every control that is switched off or in observe mode on the cluster, with its date and its reason (finding F6 of the ADR).
3. Write the security acceptance tests as automated negative tests.

## Existing work it builds on

- The hardening of [ADR-0602](../../adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md) and [ADR-0603](../../adr/0603-close-the-medium-severity-security-gaps-found-in-the-2026-11-06-review.md), the three remaining windows of [ADR-0613](../../adr/0613-close-the-three-remaining-live-hardening-items-of-adr-0603-in-mid-december.md) ([WP-252](wp-252-limit-or-accept-the-keycloak-http-listener.md), [WP-253](wp-253-verify-full-database-transport-for-every-client.md), [WP-254](wp-254-intermediate-ca-and-separate-istio-service-account.md)) and the [post-demo hardening list](../post-demo-hardening.md). This work package reviews and tests; it does not redo them.
- The enforcement points already decided: [ADR-0035](../../adr/0035-prevent-restricted-internal-context-from-reaching-external-models.md), [ADR-0036](../../adr/0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md), [ADR-0567](../../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md).

## Acceptance

- An attempt to route C3 data, or unclassified sensitive content, to an unauthorized external model is rejected, including when local inference is unavailable.
- Direct MaaS access and the alternative gateway paths cannot get around the restrictions.
- The list of switched-off controls exists and is dated.
