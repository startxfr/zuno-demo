# WP-255: Write a readable OKF field reference in zuno-demo-agents

- **State:** Repo work merged (2026-11-13, shipped in zuno-demo-agents v0.14.4; the proofs that need a canary or unifai-compare remain)
- **ADRs:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md),
  [ADR-0579](../../adr/0579-extend-okf-to-v0-3-with-skills-model-roles-guardrails-and-limits.md) (the v0.3 fields)
- **Depends on:** none
- **Related:** [WP-256](wp-256-add-an-agent-guide-and-bundle-file-list-to-the-agents-repository.md),
  [WP-257](wp-257-publish-verify-and-roll-back-an-okf-release-documented.md),
  [WP-258](wp-258-unifaiagentbundle-custom-resource-page-in-the-agents-repository.md),
  [WP-259](wp-259-position-the-agents-repository-as-a-reusable-reference.md)
- **Target repository:** `startxfr/zuno-demo-agents` (public, English). The WP is tracked here; the work lands there by pull request.
- **Estimated files touched:** ~3 in zuno-demo-agents: a new `docs/okf-reference.md`, `README.md` (the OKF table and a stale sentence), the schema links

> Execute this brief as a standalone task. Documentation only: no agent, policy or schema changes. Opened 2026-11-13 (user's go) at the
> request of the unifai-compare session, which will link to the pages and no longer carries this documentation in the UnifAI fork.

## Why

UnifAI is becoming generic and will only link to the OKF documentation, which must live in zuno-demo-agents. Today a reader has no
single readable reference of the fields: the README table still says v0.2, and one sentence ("the operator does not map
`zuno.limits` yet") is stale because limits are applied since ADR-0579 (WP-164).

## Goal

One page lists every OKF field a bundle author writes, with its type, where it is valid, what bounds it and one example.

## Content

1. **Base fields of an agent** (`agent.okf.md` frontmatter) and **of a task** (`tasks/*.md`): `allowed_tools`, `allowed_knowledge`,
   `prompts`, `live_read_tool` and the others the schemas define; the `zuno:` block and the `vnd.zuno.okf.*` media types.
2. **`delegation`**: what an agent declares to call another, and what the platform checks.
3. **Writing policies** (`policies/`): the layout, the rule that an agent may only narrow a corp policy, and how
   `platform/okf/check_narrowing.py` reports a widening.
4. **v0.2 to v0.3**: which fields are new, which version a consumer reads.
5. Fix the README table (v0.2) and the stale limits sentence.

## Source

The JSON schemas `platform/okf/schema/*-v0.3.schema.json`, the checks in `platform/okf/`, the three real agents under `agents/`, and
ADR-0579 in zuno-demo. Every field in the page is checked against a schema: a field a schema does not know is not documented.

## Proof

- A link check passes on the new page. A listed example validates with the repository's schema validator.
- unifai-compare receives the final path and anchors.

## Lots

| Lot | Content |
|---|---|
| 1 | Field inventory from the schemas, as a table |
| 2 | Prose, examples and the README fixes; validate the examples; pull request |

## Out of scope

- A neutral OKF v0.4 (an idea for the UnifAI 0.2 line; the owner decides whether to propose it).
