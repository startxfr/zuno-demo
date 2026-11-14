# WP-266: Complete the tool and rag notes and the task prompts

- **State:** Done (2026-11-14: notes and prompts in v1.0.0, prompts name tools by capability (PR #53); the 6 new prompts evaluated before and after the promotion, no regression, comage stops guessing the opportunity of a write: [evidence](../evidence/wp-266-prompt-evaluation-2026-11-14.md); Arkos `write-code` 422 fixed separately for v1.0.1)
- **ADRs:** [ADR-0615](../../adr/0615-align-the-zuno-okf-profile-with-upstream-okf-0-2-and-freeze-it-as-profile-1-0.md) (clauses 9, 10)
- **Depends on:** WP-262, WP-265
- **Related:** [WP-267](wp-267-release-and-promote-zuno-demo-agents-v1-0-0.md)
- **Target repository:** `startxfr/zuno-demo-agents`, by pull request into `devel`
- **Estimated files touched:** about 45: `tools/` and `rag/` notes of tekos, arkos and comage; 12 prompts

> Execute this brief as a standalone task. **Cut line:** if the prompts of the active agents are not evaluated by
> Sunday 2026-11-15 12:00, v1.0.0 ships without them and v1.0.1 follows. The format is never cut.

## Why

tekos documents 3 of its 13 tools and the other agents none (ADR-0615 F8). 12 tasks have no prompt, 6 of them on
active agents (F9).

## Content

1. **Notes.** A `tools/<capability>.md` note for every tool, and a `rag/<domain>.md` note for every knowledge domain,
   that tekos, arkos and comage declare (about 30). Each note must be correct against the task declarations and the
   corp tool policy.
2. **Prompts for the active agents** (tekos ×3, comage ×2, arkos `write-code`). Each prompt starts from the system
   message the operator builds today (description plus task body), rewritten as instructions, so behaviour moves as
   little as possible.
3. **Prompts for the placeholders** (advantage ×3, finage ×1, cognos ×1, soursage ×1). These agents are not served,
   so there is no behaviour risk.

## Proof

- The release checks pass, including the prompt-per-task rule.
- On a canary (ADR-0609) or through the acceptance gate: every task of tekos, arkos and comage answers its
  `prompt_examples` correctly, with the expected tools and no regression on the primary tasks. Record the results.

## Out of scope

- Contract test suites for tekos.
