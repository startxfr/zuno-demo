---
okf_version: v0.2
type: task
title: Answer an OpenShift or internal-knowledge question
zuno:
  allowed_tools:
    - confluence.page.search
    - confluence.page.read
  allowed_knowledge: []
---

# Answer an OpenShift or internal-knowledge question

The single task backing every call OpenShift Lightspeed makes through the MCP
Gateway's `/mcp` front-door (ADR-0524 clause 3).

## Scope

Exactly two capabilities, both read-only:

- `confluence.page.search` - find internal pages matching a question.
- `confluence.page.read` - read one page's content.

`confluence.page.create` and `confluence.page.update` are deliberately absent.
That omission is load-bearing: ADR-0011's `task_rights` factor can only narrow,
never widen, and `policies/tools/tool-policy.yaml` independently withholds
`lightspeed_readonly` from both write capabilities. Either alone denies a write;
ADR-0524 clause 4 keeps both, plus the front-door's own `tools/list` filtering,
so no single edit can silently grant Lightspeed write access to Confluence.

## Deliberately no `allowed_knowledge`

Lightspeed does not retrieve from Zuno's RAG corpora. Official OpenShift
documentation comes from the operator's own RHOKP sidecar (ADR-0524 clause 2),
and internal knowledge arrives through the two live tools above rather than
through indexed retrieval. Adding a `knowledge.*` entry here would create a
second, unreviewed path to internal content that ADR-0524 never assessed.
