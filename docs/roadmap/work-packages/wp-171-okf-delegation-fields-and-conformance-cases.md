# WP-171: OKF delegation fields and conformance cases

- **State:** Repo work merged
- **ADRs:** [ADR-0401](../../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md)
- **Depends on:** [WP-170](wp-170-agent-delegation-contract-and-adrs.md)
- **Related:** [ADR-0579](../../adr/0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md), [WP-163](wp-163-okf-v0-3-schema-and-consumers.md), [WP-51](wp-51-adaptation-hooks-conformance.md)
- **Target:** v0.11
- **Estimated files touched:** ~8 in `zuno-demo-agents` (schema, corp limits policy, narrowing check, conformance cases, tests) and ~3 in `zuno-demo` (admission view and narrowing)

## Goal

Make delegation expressible and reviewable in OKF v0.3 as two optional fields, with a corp ceiling, and
prove every reader handles them with the conformance cases.

## Steps

1. `zuno-demo-agents/platform/okf/schema/zuno-okf-v0.3.schema.json`: `zuno.delegation.targets[{agent, task}]`
   and `zuno.limits.delegation.max_depth`. `policies/limits/limits-policy.yaml`: `max_delegation_depth`
   (initial 2) and `delegation.allow_write` (false).
2. `platform/okf/check_narrowing.py`: `max_depth` at most the ceiling; targets well formed, an agent never its own target.
3. Conformance cases: valid with a declared target; target unknown; depth above the ceiling; an agent targeting itself;
   no `delegation` field (no delegation).
4. `zuno-demo`: `okf_narrowing.py` checks the ceiling, the targets and the v0.3-only rule at admission (done); `agents_view`
   is deliberately unchanged, so released conformance cases keep their meaning; `evaluations/common/okf_release.py`
   `agent_declaration` already returns the block.
5. `policies/tools/tool-policy.yaml`: every tool declares `access: read | write` (absent means write), validated by
   `validate_okf_bundle.py`, used by WP-172 to refuse delegated writes.
6. Branch `prep/delegation-schema` on `zuno-demo-agents` (pushed) and a PR to `devel`; the release and its promotion are the maintainer's. Coordinate with the
   session that releases that repository before promoting, since mcp-gateway reads the release at build time.

## Acceptance

Conformance cases pass through all five readers with no skip; the fixtures self-test and the schema validators pass;
`check_okf_read_boundary.py` stays green.

## Progress (2026-10-24)

Merged on `zuno-demo-agents` `devel` (PR #9, `d78a610`, CI green): the two optional fields in the OKF v0.3 schema,
`max_delegation_depth` and `delegation.allow_write` in the corp limits policy, `access: read|write` on every tool
of `tool-policy.yaml`, the narrowing checks, two conformance cases, and the validator now accepting v0.2 and v0.3
content notes (requested by the Tekos v0.3 migration). The admission side in `zuno-demo` was merged earlier (WP-172).

Not live: no release carries it yet (`VERSION` is still 0.3.1). The next release, its promotion into `platform/okf/agents.lock`
and the Tekos v0.3 migration (session on branch `wp-163/tekos-okf-v03`) are the maintainer's to group and cut; until
then the delegation fields exist in no admitted bundle and every delegated call is refused.
