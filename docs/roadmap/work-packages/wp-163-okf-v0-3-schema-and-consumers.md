# WP-163: OKF v0.3 schema and its consumers

- **State:** Not started
- **ADRs:** [ADR-0579](../../adr/0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md)
- **Depends on:** [WP-158](wp-158-bootstrap-the-zuno-demo-agents-repository.md), [WP-160](wp-160-admit-the-corp-okf-release-in-zuno-demo.md)
- **Related:** [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0567](../../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md), [WP-162](wp-162-keyless-okf-verification-in-unifai-operator.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md)
- **Target:** v0.12
- **Estimated files touched:** ~15 in `zuno-demo-agents` (v0.3 schemas, validator, narrowing check, `policies/guardrails/guardrails-policy.yaml`, skills, eight bundles); ~10 in `zuno-demo` (mcp-gateway `app/agent_declarations.py`, mlops, `admit_okf_bundle.py validate`, tests); the operator's embedded schemas in the fork.

> Consumers first, bundles last: no bundle declares `okf_version: v0.3`
> until every reader accepts it.

## Goal

OKF v0.3 expresses skills, model roles, guardrail modes and per-agent
limits; a widening against the corp policies is refused in CI and at
admission; every consumer reads v0.2 and v0.3; the eight agents are
migrated.

## Steps

1. **Schemas** `schema/zuno-okf-*-v0.3.schema.json` and the new
   `zuno-okf-skill-v0.3.schema.json` per ADR-0579 clauses 1-4, aliases for
   `zuno.max_tokens` and `zuno.memory`.
2. **Corp guardrails policy** `policies/guardrails/guardrails-policy.yaml`
   (minimum mode per classification), written from the human spec in
   `policies/guardrails/README.md` and the current ai-gateway behaviour
   (ADR-0567).
3. **Narrowing check** (ADR-0579 clause 5) in `validate_okf_bundle.py`, with
   one failing fixture per widening kind; the same check in
   `admit_okf_bundle.py validate`.
4. **Consumers.** mcp-gateway, mlops and the operator's `internal/okf/`
   accept v0.3 (skills appended to the system prompt in order; ignored
   fields listed in the operator's `status.unmapped`).
5. **Migrate the bundles** in `zuno-demo-agents`: tekos first, release,
   promote, check; then the others. Extract repeated prompt passages into
   skills only where two tasks really share them.

## Acceptance

Both schema versions validate; widening fixtures fail with a message naming
the corp clause; a v0.3 tekos release is admitted and served identically
apart from the intended changes.

## Open questions

- Where is the skill body injected for UnifAI nodes: the system prompt (as
  for agent-runtime) or a UnifAI-native construct, if one exists in the
  fork?
