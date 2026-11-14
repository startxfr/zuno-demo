# WP-259: Position zuno-demo-agents as a reference others can copy, and publish stable links

- **State:** Repo work merged (2026-11-13, shipped in zuno-demo-agents v0.14.4; the proofs that need a canary or unifai-compare remain)
- **ADRs:** [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md)
- **Depends on:** [WP-255](wp-255-okf-field-reference-in-the-agents-repository.md), [WP-256](wp-256-add-an-agent-guide-and-bundle-file-list-to-the-agents-repository.md),
  [WP-257](wp-257-publish-verify-and-roll-back-an-okf-release-documented.md), [WP-258](wp-258-unifaiagentbundle-custom-resource-page-in-the-agents-repository.md)
- **Target repository:** `startxfr/zuno-demo-agents` (public, English); tracked here, landed there by pull request
- **Estimated files touched:** ~3 in zuno-demo-agents: `README.md`, `docs/README.md` (an index), the CHANGELOG entry

> Execute this brief as a standalone task. Opened 2026-11-13 (user's go). Last of the five: it needs the pages it links.

## Why

The repository does not say that it is a reference someone can copy for their own agents, nor how a team outside zuno adapts it. UnifAI
asks for definitive paths and anchors on `main` or on a `v*` tag, to link to them.

## Goal

The README states the repository's role in one sentence and links an index of the documentation. The anchors UnifAI links to are stable.

## Content

1. **A positioning sentence** and a short "use it for your own agents" section: what to change (identity, registry, corp policies, the
   `zuno` contract namespace), what to keep.
2. **A documentation index** page linking the four pages above.
3. **Stable anchors:** the final paths and heading anchors are sent to unifai-compare, on `main` or on a `v*` tag, after the pull request merges.
4. **`contractNamespace`:** once unifai-compare fixes the names, a short note that zuno sets it to `zuno` (headers `X-<Ns>-*`, metadata `<ns>.*`).
5. **Housekeeping:** the local checkout has 2 unpushed WP-222 commits and is 7 commits behind `origin/devel`; resolve it by working in a
   separate worktree from `origin/devel` and leaving the shared checkout untouched.

## Proof

- Every link of the index resolves on the merged branch. Anchors are listed in the message to unifai-compare.

## Out of scope

- A neutral OKF v0.4 (an idea for the UnifAI 0.2 line).
