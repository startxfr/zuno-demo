# WP-50: OKF extraction cutover (completes ADR-0506 and ADR-0507)

- **State:** Not started
- **ADRs:** ADR-0506, ADR-0507 (both completed here)
- **Depends on:** WP-49
- **Blocks:** WP-52
- **Estimated files touched:** ~25 (mostly deletions)

> Execute this brief as a standalone task from the repository root.
> This is the stream's one risky change-set — everything was prepared
> by WP-48/WP-49 precisely so this commit only *removes* the duplicate
> source and repoints references. If any acceptance check fails, revert
> the whole commit; never patch forward half-cut-over.

## Goal

zuno-demo stops containing the moved content: the six roots are
deleted, the scaffold generator splits into its two per-repo halves,
and every reference (CI, validators, docs) points at the pinned fetch
path. zuno-okf becomes the sole source, per the cross-repo clause's
end state.

## ADR references

ADR-0506 clauses 1–2, 4–5 (cutover + generator split); ADR-0507
(consumption now exclusive).

## Preconditions (verify before starting)

- WP-49 merged; identity proof recorded; final mirror re-sync done and
  the pin bumped to the sync head.
- Enumerate every zuno-demo reader of the six roots before deleting:
  `grep -R` for `agents/`, `policies/tools`, `policies/knowledge`,
  `policies/quotas`, `evaluations/`, `platform/okf/schema`,
  `scaffold_agent` across `Makefile`, `.github/workflows/`,
  `platform/`, `ansible/`, `components/*/Dockerfile`, `docs/`. The
  list drives step 3; attach it to the State log.

## Repo changes (step by step)

1. Delete the six roots from zuno-demo (they live in zuno-okf at the
   pin).
2. Generator split (ADR-0506 clause 4): `scaffold_agent.py`'s
   bundle+evaluations half is already in zuno-okf (WP-48 mirror) —
   strip zuno-demo's copy down to the GitOps half
   (`platform/templates/agent/scaffold_gitops.py`, chart +
   Applications + keycloak-fragment consumption from a shared
   `AgentSpec` file); relocate `test_scaffold_validate_discard.py`'s
   bundle-side assertions to zuno-okf CI, keep the gitops-side test in
   `lint.yml`.
3. Repoint every reader from the step-0 enumeration: lint jobs that
   validated bundles locally now run against the fetched pin (or are
   retired here because zuno-okf CI owns them — decide per job from
   the ADR-0506 clause-3 split, record each decision); evaluation
   runner reads scenarios from the fetched pin; docs references
   updated.
4. Update contract docs: `operator/aiagent-operator/CONTRACT.md`'s
   `okfBundleRef` wording to the ADR-0507 semantics;
   `platform/architecture/agent-platform-separation.md`'s bundle-source
   description; root `README.md`'s OKF paragraph (also fix its stale
   "AIAgent CRD/operator is retargeted to v1" line while touching it —
   ADR-0308/0350 are Implemented).
5. Full gate: entire lint chain, full build matrix via the pin,
   `check_docs.py`, operator envtest.

## What NOT to touch

Standard list; plus: `policies/data-classification/classification.yaml`
and `platform/bindings/` (they stay — ADR-0506 clause 2); no zuno-okf
content edits in the same change-set (single-writer discipline ends
with this merge, but not inside it).

## Acceptance checks

- None of the six roots exist in zuno-demo; the step-0 enumeration has
  zero unrepointed survivors (`grep` re-run is clean).
- Full build matrix + lint chain + envtest green; images identical to
  WP-49's fetch-path builds.
- Onboarding dry-run: both generator halves run against a throwaway
  `AgentSpec` and validate-discard cleanly in their own repos.
- `check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

Confirm one full ArgoCD sync cycle and one agent evaluation run
post-cutover behave identically (no manifest changed, but the
evaluation runner's scenario source moved).

## Status updates (then re-run check_docs.py)

On merge + the operator confirmation: ADR-0506 → `Implemented - see
the zuno-okf repository and platform/okf/zuno-okf.ref.`; ADR-0507 →
`Implemented - see platform/okf/zuno-okf.ref and build-publish.yml.`
Index + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Hooks (WP-51, runs in parallel). Mounted artifacts (WP-52).
