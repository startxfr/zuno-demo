# WP-49: Pinned-ref builds (promotes ADR-0507)

- **State:** Not started
- **ADRs:** ADR-0507
- **Depends on:** WP-48
- **Blocks:** WP-50, WP-51
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root.
> Cross-repo clause in force: zuno-demo copies remain in place and
> authoritative; this WP only adds the pinned consumption path and
> proves it identical.

## Goal

zuno-demo builds consume `zuno-okf` at the single pinned ref
(`platform/okf/zuno-okf.ref`): CI fetches the pin into the build
context so every existing Dockerfile `COPY agents/ policies/ ...`
instruction works against the fetched tree, byte-for-byte, proven by
building both ways.

## ADR references

ADR-0507 clauses 1–2, 4; clause 3's CRD widening rides here too (an
additive pattern change is small enough to carry with the pin work).

## Preconditions (verify before starting)

- WP-48 merged and mirror still in sync (re-diff the six roots first —
  parallel sessions and zuno-okf reviews may have moved either side;
  resync before pinning).
- Read: `.github/workflows/build-publish.yml` (matrix +
  sign-okf-bundles job), every `components/*/Dockerfile` COPY of
  `agents`/`policies`, `components/mcp-gateway/app/policy.py`'s
  classification.yaml load path (the composition seam), the CRD
  `okfBundleRef` pattern in
  `operator/aiagent-operator/api/v1alpha1/aiagent_types.go`.

## Repo changes (step by step)

1. `platform/okf/zuno-okf.ref` — one commit SHA (the WP-48 mirror
   head), documented header comment; the only zuno-okf ref anywhere in
   zuno-demo.
2. CI: a fetch step in `build-publish.yml` (and a `make`-level helper
   for local builds) that clones zuno-okf at the pin, **verifies the
   resolved SHA equals the pin**, and lays the six roots into the build
   context; fail the build on any fetch/verify error — no silent
   fallback.
3. Compose the split policy tree: images must carry both the fetched
   package policies and zuno-demo's
   `policies/data-classification/classification.yaml` (ADR-0506
   clause 2) — adjust COPY ordering/paths so the merged layout is
   identical to today's.
4. Prove identity: build every OKF-consuming image once from in-repo
   copies, once via the fetch path; compare the OKF content layers
   (hash the copied trees). Record the comparison in the State log.
5. CRD: widen the `okfBundleRef` pattern to accept
   `<repo>@<ref>:agents/<name>` alongside the bare form; regenerate the
   CRD manifest + chart copy; envtest for both forms; no live CR
   changes.
6. `sign-okf-bundles` signs the fetched tree at the pin (ADR-0106 at
   the new source).

## What NOT to touch

Standard list; plus: no deletion of in-repo copies (WP-50); no
component code (hooks are WP-51); no gitops chart changes beyond the
regenerated CRD copy.

## Acceptance checks

- Full build matrix green via the fetch path; the layer-hash comparison
  shows identity; a deliberately corrupted pin SHA fails the build
  visibly (restore after proving).
- `grep -R zuno-okf` over zuno-demo finds refs only in the pin file,
  this brief, the ADRs/roadmap and the WP-48 note.
- Operator envtest green with both `okfBundleRef` forms;
  `check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

Read-only CI credential for zuno-okf (repo secret) — blocking for the
first CI run; confirm one signed-bundle verification against the
pinned tree.

## Status updates (then re-run check_docs.py)

On merge: ADR-0507 → `Partially implemented (pin + fetch + identity
proof merged; cutover pending WP-50)`. Index + tracker + MEMORY.md
accordingly.

## Out of scope / deferred

- Deleting anything (WP-50). Pin-bump cadence/policy (governance doc
  territory, noted in the ADR).
