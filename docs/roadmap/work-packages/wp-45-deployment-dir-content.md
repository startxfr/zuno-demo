# WP-45: Real deployment/ directory content (completes ADR-0503)

- **State:** Done (2026-08-18). One recorded generalization of the
  brief: the "for Tekos" manifest-summary case applies to comage/
  advantage/finage too — chart verification showed only Arkos renders
  an `AIAgent` CR (Naveo too, but it is Stage 1 with no `deployment/`
  dir, skipped by design); the generator auto-detects the shape from
  the rendered docs, so only Arkos got `aiagent-snapshot.yaml` and the
  four raw-chart agents got `manifest-summary.md`. Their deployment
  READMEs state whether raw-manifest is deliberate (Tekos, coexistence
  proof) or legacy-pending-promotion (the other three, PROMOTION.md
  step 2). Tekos's Application pair is the legacy-named `zuno-api-*`
  (`gitops/apps/api/`), handled via an override map in the generator.
  Tamper test proven (edited replicas → exit 1 → regenerated). Lint
  gains the blocking ADR-0503 snapshot-drift step.
- **ADRs:** ADR-0503 (deployment half; WP-44 delivers the matrix half)
- **Depends on:** WP-43
- **Blocks:** WP-48
- **Estimated files touched:** ~12

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).

## Goal

Replace the one-line stub READMEs in every existing
`agents/<name>/deployment/` directory (tekos, arkos, comage, advantage,
finage) with a generated, validated deployment snapshot: the agent's
`AIAgent` CR spec as rendered from its chart (or, for plain-manifest
Tekos, a generated summary of its chart's deployment surface), plus a
README naming the chart, Applications and sync-waves that deploy it.

## ADR references

ADR-0503 clause 3. `gitops/` remains the sole applied source (ADR-0022);
the snapshot is a reviewable mirror whose drift fails CI.

## Preconditions (verify before starting)

- WP-43 merged. `helm` available locally (`helm template` renders the
  snapshot input); `oc` NOT needed — this is repo-only.
- Read: `gitops/charts/arkos/templates/aiagent.yaml` (CR-managed shape),
  `gitops/charts/tekos/` (plain-manifest shape),
  `operator/aiagent-operator/config/samples/` (field vocabulary).
- `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

1. `platform/okf/generate_deployment_snapshot.py` — for a CR-managed
   agent: `helm template gitops/charts/<name>` → extract the `AIAgent`
   resource → write `agents/<name>/deployment/aiagent-snapshot.yaml`
   (with a generated-file header naming source chart + this script).
   For Tekos: write `deployment/manifest-summary.md` listing the
   chart's Deployments/Services/Routes with image refs and the
   grandfathered ADR-0350 coexistence note. `--check` mode re-renders
   and diffs, exit non-zero on drift.
2. Generate for the five agents with `deployment/` directories; rewrite
   each `deployment/README.md` to name chart path,
   `gitops/apps/<name>/` Applications, sync-waves, and the snapshot
   regeneration command. (Naveo/cognos/soursage have no `deployment/`
   directory — Stage 1 per ADR-0502; do not create one.)
3. Wire `--check` into `.github/workflows/lint.yml`'s policy-as-code
   job as a blocking step.

## What NOT to touch

Standard list; plus: nothing under `gitops/` changes — the snapshot
follows the chart, never the reverse; no `agent.okf.md` edits (matrix
is WP-44's).

## Acceptance checks (run from repo root; all must pass)

- `python3 platform/okf/generate_deployment_snapshot.py --check` exits
  0; editing a chart value without regenerating makes it exit non-zero
  (restore after proving).
- No `deployment/` directory contains the old one-line stub text.
- `helm lint` clean on touched charts (none expected);
  `check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

None.

## Status updates (then re-run check_docs.py)

See WP-44's Status updates — ADR-0503 goes `Implemented` when both
halves are merged; this brief's State log records which half landed
when. Index + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Creating `deployment/` for Stage-1 agents (born at promotion,
  per PROMOTION.md).
