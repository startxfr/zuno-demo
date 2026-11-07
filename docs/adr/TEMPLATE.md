# ADR-NNNN: <Decision in the imperative, as one sentence>

<!--
Template for a new record (ADR-0606 clause 5). Before writing:
1. Reserve the number. Take the next free number from `origin` and from every local branch
   (`git for-each-ref` plus a `ls docs/adr` on each), then tell every live working session which number you take.
   `platform/docs/check_docs.py` fails when two files share a number.
2. Name the file `NNNN-<slug>.md`, where the slug is the title in lower case with hyphens.
3. Add the index row to docs/adr/README.md, under the section that matches **Target:**, with the bare status phrase.
4. Log the addition in docs/adr/CHANGELOG.md when it creates or moves a band.
Delete this comment.
-->

- **Status:** Proposed
- **Target:** v0.NN
- **Date:** YYYY-MM-DD
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-NNNN](NNNN-slug.md)

<!-- Optional header fields, only when they apply: **Extends:**, **Supersedes:** (the superseded record must name this
one back), **Amended:**, **Renumbered:**. -->

## Context

What forces the decision, in a few sentences. State facts with their evidence: a file path, a commit, a measured value,
a date.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | <what is true> | <where it can be checked> |

## Decision

**<The whole decision in one bold sentence.>**

1. **<Name of the clause>.** What is decided, concretely enough for a work package to implement it and for a reviewer to
   check it. Cite the work package that carries it.
2. **<Name of the clause>.** ...

## Alternatives considered

- **<Alternative>.** Why it was not chosen, or under which condition it would be.

## Consequences

- What becomes easier, harder or more expensive.

## Security considerations

What this changes for identities, secrets, network reach or the supply chain, or "None beyond ...".

## Operational considerations

What an operator runs, watches or schedules differently.

## Work packages

[WP-NNN](../roadmap/work-packages/wp-NNN-slug.md) (<what it carries>).

<!--
Later changes are appended as dated sections, never as rewrites of the clauses above:
## Update YYYY-MM-DD (WP-NNN): <what was learned or built>
## Amendment (YYYY-MM-DD): <retarget or correction, and why>
-->
