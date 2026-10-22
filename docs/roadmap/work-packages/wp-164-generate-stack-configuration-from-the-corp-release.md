# WP-164: Generate stack configuration from the corp release

- **State:** Not started
- **ADRs:** [ADR-0581](../../adr/0581-derive-stack-configuration-from-the-admitted-corp-bundle.md)
- **Depends on:** [WP-160](wp-160-admit-the-corp-okf-release-in-zuno-demo.md), [WP-163](wp-163-okf-v0-3-schema-and-consumers.md)
- **Related:** [ADR-0530](../../adr/0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md), [ADR-0570](../../adr/0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md), [WP-157](wp-157-slim-the-ai-gateway-via-maas.md), [WP-162](wp-162-keyless-okf-verification-in-unifai-operator.md)
- **Target:** v0.12
- **Estimated files touched:** ~25 in `zuno-demo` — `platform/okf/generate_stack_config.py` and tests, the generated files of ADR-0581 clause 2, the charts that merge them (`keycloak`, `models`, `connectivity-link`, `ai-gateway`, `unifai`, per-agent charts still alive), the keycloak reconcile Job script, `lint.yml`, `okf-promote.yml`, removal of `generate_quota_enforcement.py` and of `zuno_unifai_values.okf.bundles` from `confidential.yml` handling.

> Every value copied by hand from a bundle today becomes generated or
> disappears.

## Goal

`generate_stack_config.py` produces, from the locked release, the Keycloak
groups, MaaS subscriptions, Kuadrant policies, ai-gateway routing and
guardrail inputs, per-agent values and UnifAI bundle values; `--check` gates
every PR; the hand-maintained copies are gone.

## Steps

1. **Inventory** each target in ADR-0581's table: read the current file,
   list hand-written vs agent-derived entries, decide the merge (separate
   generated values file layered by the chart).
2. **Generator** with one emitter per target and golden-file tests; absorb
   `generate_quota_enforcement.py` (coordinate with WP-157 if it has
   changed that script to emit TokenRateLimitPolicies).
3. **Charts** read the generated files; remove the duplicated hand-written
   entries.
4. **Keycloak** reconcile Job (ADR-0530) extended to `agent_<name>` groups:
   create and update, never delete, never touch membership.
5. **UnifAI** bundles values generated with digests from the corp index and
   `verify.keyless` (WP-162); drop the `confidential.yml` path.
6. **Wire** `--check` into `lint.yml` and the generation into
   `okf-promote.yml`.
7. **Live on demo333:** promote a release that adds a tool to one task and a
   new group to one agent; check the generated diff, the RateLimitPolicy
   `Enforced` plus a real 429 (WP-54 lesson), the group created in Keycloak,
   and the UnifAI bundle re-emitted.

## Acceptance

`--check` green; no agent-derived value is hand-written anywhere in
`gitops/`; the step 7 promotion produces exactly the expected diff and
takes effect live; a release that widens beyond corp policies is refused
before generation.
