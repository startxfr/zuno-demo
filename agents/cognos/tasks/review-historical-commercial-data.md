---
okf_version: v0.2
type: task
title: Review historical commercial data
zuno:
  allowed_tools: []
  allowed_knowledge:
    - knowledge.sxa
---

# Review historical commercial data

Answer a board-level question grounded in `knowledge.sxa` (ADR-0217/WP-067) -
a weekly, already-anonymized legacy commercial corpus, distinct from
`knowledge.sxa-legacy` (ADR-0216/WP-065).

**Declared, not yet functional (ADR-0036, ADR-0502).** Cognos is
`status: placeholder` (`agent.okf.md`): no gitops chart, no Application, no
running Agent Runtime workflow exists for it - a placeholder agent has zero
tool-call/retrieval capability by construction regardless of what a task
declares, matching `tasks/coming-soon.md`'s own framing. This task's
`allowed_knowledge` entry follows `agents/cognos/NEXT_STEPS.md`'s step 3
("add policy entries... when real tasks are authored") - the policy grant
(`policies/knowledge/knowledge-policy.yaml`'s `knowledge.sxa` entry already
lists `board`) is ready and correct, but nothing serves it until a separate
future ADR/WP promotes Cognos out of placeholder (Stage-1 -> Stage-2:
gitops chart, Application, evaluations skeleton, ADR-0502's promotion
checklist).
