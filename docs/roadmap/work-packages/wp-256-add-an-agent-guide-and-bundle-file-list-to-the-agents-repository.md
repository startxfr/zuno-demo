# WP-256: Add a generic "add an agent" guide and the bundle file list to zuno-demo-agents

- **State:** Not started
- **ADRs:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md)
- **Depends on:** [WP-255](wp-255-okf-field-reference-in-the-agents-repository.md) (the guide links to the field reference)
- **Related:** [WP-258](wp-258-unifaiagentbundle-custom-resource-page-in-the-agents-repository.md)
- **Target repository:** `startxfr/zuno-demo-agents` (public, English); tracked here, landed there by pull request
- **Estimated files touched:** ~6 in zuno-demo-agents: `docs/add-an-agent.md`, `docs/bundle-files.md`, the "Declarative structure" sections of
  the tekos and arkos READMEs, `platform/release/scaffold_agent.py` (one comment), this repository's README links

> Execute this brief as a standalone task. Documentation, plus one comment fix in a script. Opened 2026-11-13 (user's go).

## Why

There is no generic guide to add an agent. The list of files embedded in a bundle exists only in the docstring of `okf_release.py`. The
"Declarative structure" sections of the tekos and arkos READMEs describe paths of zuno-demo that do not exist in this repository, and
`scaffold_agent.py` cites a `PROMOTION.md` that does not exist.

## Goal

A newcomer can add an agent end to end from this repository alone, and knows which files travel in the artifact.

## Content

1. **Guide "add an agent":** scaffold with `scaffold_agent.py`, write `agent.okf.md`, tasks, prompts, tools, rag, policies and tests, run the
   checks, bump the agent `VERSION`, open the pull request, what the release chain then does.
2. **File list of a bundle:** which files are embedded (never `tests/` nor `README.md`), which are optional, and the corp skill embedding
   (`skills/corp/<name>.md`). Derived from `okf_release.py`, not from memory.
3. **Fix the tekos and arkos "Declarative structure" sections** so every path exists in this repository, and fix the dangling `PROMOTION.md`
   reference (write the missing page only if the release flow needs it, otherwise point at `RELEASING.md`).

## Proof

- Following the guide on a scratch agent passes `validate_okf_bundle.py` and the contract-test runner; the scratch agent is not committed.
- Every relative link in the touched files resolves.

## Lots

| Lot | Content |
|---|---|
| 1 | The file list from `okf_release.py`, and the README path fixes |
| 2 | The guide, tried once end to end on a scratch agent; pull request |

## Out of scope

- Changing the scaffold's behaviour, the agents themselves or any policy.
