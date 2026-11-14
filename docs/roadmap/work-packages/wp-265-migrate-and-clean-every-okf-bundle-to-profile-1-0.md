# WP-265: Migrate and clean every OKF bundle to profile 1.0

- **State:** Not started
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clauses 2 to 4, 10)
- **Depends on:** WP-262
- **Related:** [WP-266](wp-266-complete-tool-and-rag-notes-and-task-prompts.md), [WP-267](wp-267-release-and-promote-zuno-demo-agents-v1-0-0.md)
- **Target repository:** `startxfr/zuno-demo-agents`, by pull request into `devel`
- **Estimated files touched:** about 120: every published document of the 8 agents, the experience clients, the corp skills and policies, the READMEs, the scaffold

> Execute this brief as a standalone task. A one-off migration script does the mechanical part; the prose is edited by
> hand. Every agent `VERSION` becomes 1.0.0.

## Why

All 8 agents are on legacy versions and carry stale trust metadata (ADR-0615 F6). The published prose has about 110
stale or foreign references (F7). The READMEs, `NEXT_STEPS.md` files, stub directories and the scaffold are stale (F7).

## Content

1. **Migration script** (not committed). It sets `okf_version: "0.2"` and `zuno.profile: "1.0"` and maps the envelope
   (ADR-0615 clause 4):
   - `resource` at `blob/main/<path>`;
   - `sources` as objects;
   - `verified` as an empty list;
   - `stale_after`;
   - `zuno.maintainer`;
   - upstream `status` where it applies.

   It runs over the 8 agents, `experience-clients/` and the corp skills and policies that are published.
2. **`index.md`** for every bundle, written by `generate_index.py`.
3. **Published prose** made platform-neutral. Remove or rewrite every reference to Agent Runtime, `components/`,
   `evaluations/`, `gitops/`, `MEMORY.md`, `docs/agents` and the bare `v0`. Fix the false statements and the dangling
   `policies/data-classification`. YAML comments count too.
4. **READMEs:**
   - rewrite the 8 agent READMEs: purpose, tasks, structure, status;
   - delete `NEXT_STEPS.md`, and the README-only `tools/`, `rag/` and `policies/` directories of advantage and finage;
   - fix the doubled `PROMOTION.md` URL.
5. **`platform/templates/agent/scaffold_agent.py`** writes a profile 1.0 skeleton (`agent.okf.md`, a task, its prompt,
   `index.md`, `VERSION`) and nothing for a platform.
6. Drop the rule "a placeholder declares exactly one task" from the docs.

## Proof

- **Release checks.** The six release checks, `generate_index.py --check` and the platform-neutral lint pass, with
  every document on profile 1.0.
- **Stale terms.** `grep` finds none of the stale terms in published files.
- **No behaviour change.** `admit_okf_bundle.py admit --dev` (zuno-demo, after WP-263) passes on the `devel-<sha12>`
  artifacts, and the diff of `generate_stack_config.py` shows no change of tools, knowledge, groups or ceilings.

## Out of scope

- New notes and prompts (WP-266).
