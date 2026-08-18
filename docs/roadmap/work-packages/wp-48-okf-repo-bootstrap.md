# WP-48: zuno-okf repository bootstrap (starts ADR-0506)

- **State:** Not started
- **ADRs:** ADR-0506 (started here, completed by WP-50)
- **Depends on:** WP-44, WP-45, WP-46 (extract the finished v0.1
  content, not a draft)
- **Blocks:** WP-49
- **Estimated files touched:** ~5 in zuno-demo; the new repository

> Execute this brief as a standalone task. First WP under the
> okf-roadmap's **cross-repo clause**: until WP-50 merges, zuno-demo
> remains authoritative for all OKF content and zuno-okf is a mirror —
> never edit the same content in both.

## Goal

Bootstrap the `zuno-okf` repository as a history-preserving mirror of
the six content roots, with self-contained CI (validators, contract
suite, drift checks) green and the ADR-0508 conformance skeleton in
place. zuno-demo is untouched except for a mirror-state note.

## ADR references

ADR-0506 clauses 1–3, 5 (mirror step); ADR-0508 clause 2 (the
`okf-package.yaml` + `conformance/` skeleton is born here, fixtures
finalized in WP-51 Part A).

## Preconditions (verify before starting)

- Operator has created the GitHub `zuno-okf` project (same org, branch
  protection, CODEOWNERS per ADR-0506 clause 3) — blocking human step.
- WP-44/45/46 merged; `git filter-repo` (preferred) or subtree-split
  available.
- Confirm the moved-roots list against ADR-0506 clause 1 verbatim,
  including `policies/quotas/` if WP-54 has merged by execution time
  (record its presence/absence in the State log).

## Repo changes (step by step)

1. History-preserving extraction of: `agents/`, `platform/okf/schema/`,
   `platform/templates/agent/scaffold_agent.py`,
   `policies/tools/tool-policy.yaml`,
   `policies/knowledge/knowledge-policy.yaml`
   (+ `policies/quotas/quota-policy.yaml` if present), `evaluations/`
   — unchanged relative paths, per ADR-0506 clause 1.
2. Port the self-contained validators zuno-okf CI needs (bundle
   validation, knowledge-refs check, ADR-0504 contract runner, matrix
   and deployment-snapshot `--check`, quota-policy lint) — copied at
   this stage, not moved; zuno-demo keeps running its own until WP-50.
3. `okf-package.yaml` (schema version marker) + `conformance/` skeleton
   with a README defining the fixture format (ADR-0508 clause 2).
4. zuno-okf CI workflow running the ported checks; green on the mirror.
5. zuno-demo: add the mirror-state note (one line in
   `platform/okf/README.md` or equivalent) naming zuno-okf, the mirror
   date, and the single-writer rule; okf-roadmap tracker update.

## What NOT to touch

In zuno-demo: everything — no deletions, no Dockerfile/CI changes (all
WP-49/50). In zuno-okf: no content edits beyond the ported
validators/CI — it is a mirror.

## Acceptance checks

- `git log --follow` in zuno-okf shows pre-extraction history for a
  sampled bundle file and policy file.
- zuno-okf CI green; a diff of the six roots between repositories is
  empty.
- zuno-demo's full lint chain still green (nothing changed).

## Operator / human follow-up (not executable by the model)

Repository creation + protection (precondition); review/approve the
CODEOWNERS ownership map (ADR-0506 clause 3).

## Status updates (then re-run check_docs.py)

On merge: ADR-0506 → `Partially implemented (zuno-okf bootstrapped as
mirror; pin and cutover pending WP-49/WP-50)`. Index + tracker +
MEMORY.md accordingly.

## Out of scope / deferred

- Any consumption change (WP-49). Any deletion (WP-50). Fixture
  content (WP-51A). Generator split (WP-50).
