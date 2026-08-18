# Comage Deployment

Real deployment surface (ADR-0503/WP-45; formerly a one-line stub):

- **Chart:** `gitops/charts/comage/` — a **raw-manifest chart** (same
  shape as Tekos's). Unlike Tekos, this is legacy rather than
  deliberate: only Arkos was migrated as the WP-38 proof and Naveo was
  born CR-managed — **Comage's migration to a single `AIAgent` CR is a
  promotion-time step** (`platform/templates/agent/PROMOTION.md`
  step 2).
- **Applications:** `gitops/apps/comage/application-d0.yaml` /
  `application-d1.yaml` (`zuno-comage-*`), sync-wave `-101`, target
  namespace `zuno-ai-run`.
- **Snapshot:** [`manifest-summary.md`](manifest-summary.md) — the
  generated, CI-checked list of every object the chart renders.
  Regenerate after any chart change:
  `python3 platform/okf/generate_deployment_snapshot.py`
  (drift fails the lint chain's ADR-0503 step).

`gitops/` remains the sole applied source (ADR-0022) — this directory
mirrors it for review, never the reverse.
