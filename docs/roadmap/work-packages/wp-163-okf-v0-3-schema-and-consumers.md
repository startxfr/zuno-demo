# WP-163: OKF v0.3 schema and its consumers

- **State:** Done (2026-10-24)
- **ADRs:** [ADR-0579](../../adr/0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md)
- **Depends on:** [WP-158](wp-158-bootstrap-the-zuno-demo-agents-repository.md), [WP-160](wp-160-admit-the-corp-okf-release-in-zuno-demo.md)
- **Related:** [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md), [ADR-0567](../../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md), [WP-162](wp-162-keyless-okf-verification-in-unifai-operator.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md)
- **Target:** v0.12
- **Estimated files touched:** ~15 in `zuno-demo-agents` (v0.3 schemas, validator, narrowing check, `policies/guardrails/guardrails-policy.yaml`, skills, eight bundles); ~10 in `zuno-demo` (mcp-gateway `app/agent_declarations.py`, mlops, `admit_okf_bundle.py validate`, tests); the operator's embedded schemas in the fork.

> Consumers first, bundles last: no bundle declares `okf_version: v0.3`
> until every reader accepts it.

## Progress (2026-10-23)

Steps 1-3 and the zuno-demo half of step 4 are built; step 5 (migrating
bundles) has NOT started, on purpose.

- zuno-demo-agents `devel` (5d51969): v0.3 schemas for every type plus
  `skill`; corp ceilings `policies/guardrails/guardrails-policy.yaml`
  (modes off < observe < block, minimum per classification seeded from the
  ai-gateway's observe everywhere, categories pii/injection) and
  `policies/limits/limits-policy.yaml` (max_tokens 8192, the schema bound;
  max_concurrent_requests 10, a seed value nothing enforces yet);
  `check_narrowing.py` with 13 tests; both in CI and in publish.yml.
  Deviation from ADR-0579 clause 1: corp skills live in `policies/skills/`,
  not at the repository root, so they ship in the corp artifact's policies
  layer without a new layer type.
- zuno-demo: `platform/supply-chain/okf_narrowing.py`, a copy of the rule
  re-rooted on an extracted release, run by `admit_okf_bundle.py validate`
  (a widening is refused at admission too; tested); `generate_stack_config.py`
  exposes each agent's `models`, `guardrails` and `limits` (with the v0.2
  `zuno.memory` alias) for the consumers still to come.

Corp skills reach consumers inside the agent artifact (zuno-demo-agents
8a26fc2): every `corp/<name>` a task references is written into the agent's
v2 layer as `skills/corp/<name>.md`, so unifai-operator needs no second
source; the agent's digest changes with the skill and the version gate
forces the agent's bump. This refines ADR-0577 clause 1's layer content.

Bundles stay v0.2 until both: unifai-operator embeds the v0.3 schemas and
maps skills (owned by the session that owns the fork), and agent-runtime,
whose registry refuses anything but v0.2 (`app/registry.py`), is retired by
WP-156. mcp-gateway, mlops and agent-frontend do not check the version and
read only fields v0.3 keeps.


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

## Update (2026-10-24)

The consumer side is no longer blocked: unifai-operator reads OKF v0.2 and v0.3 since 0.1.27 (the v0.3
schema maps, skills appended to the node's system message, `models`, `guardrails` and `limits` listed as
unmapped in the bundle status), which answers the open question on where a skill body goes. The remaining
step is the migration of the agents' bundles to v0.3 in `zuno-demo-agents` and its promotion (release
0.3.0, [WP-165](wp-165-cut-over-and-remove-agents-from-zuno-demo.md)'s cycle), after which the
acceptance is checked live.

## Live acceptance (2026-10-24, zuno-demo-agents v0.4.0)

The tekos bundle was migrated to OKF v0.3 (whole bundle, including the six content notes, once the
validator accepted v0.2 and v0.3 notes) and released in v0.4.0, promoted in `platform/okf/agents.lock`
(okf-corp@sha256:af3824cd…, okf-tekos@sha256:9a991bbb…, tekos 0.3.0). On demo333 the
UnifaiAgentBundle `tekos` is Verified (keyless, `publish.yml` on tag `v0.4.0`), Valid "OKF v0.3, 4 tasks,
shape retrieve_reason_respond", WithinCeilings, Emitted (17 objects) and Ready; mcp-gateway fetched and
verified the same release (8 agents); a tekos chat as consultant-01 answered 200 and ends with the
"— Tekos" signature. `models`, `guardrails` and `limits` stay unmapped in the operator, so they have no
runtime effect yet. The other seven bundles still declare OKF v0.2 and migrate with their own releases.
