# Arkos Deployment

Real deployment surface (ADR-0503/WP-45; formerly a one-line stub):

- **Chart:** `gitops/charts/arkos/` — **CR-managed**: renders exactly
  one resource, the `zuno.zuno.ai/v1alpha1 AIAgent` CR the
  aiagent-operator reconciles into the frontend/BFF
  Deployment/Service/Route/ServiceAccount/NetworkPolicy/ExternalSecret/
  OKF-reference-ConfigMap set (ADR-0327/ADR-0308; Arkos was the WP-38
  migration proof — see the chart's git history for the pre-migration
  raw manifests).
- **Applications:** `gitops/apps/arkos/application-d0.yaml` /
  `application-d1.yaml` (`zuno-arkos-*`), sync-wave `-103` (after the
  operator's own `-106`), target namespace `zuno-ai-run`.
- **Snapshot:** [`aiagent-snapshot.yaml`](aiagent-snapshot.yaml) — the
  generated, CI-checked copy of the rendered CR. Regenerate after any
  chart change:
  `python3 platform/okf/generate_deployment_snapshot.py`
  (drift fails the lint chain's ADR-0503 step).

`gitops/` remains the sole applied source (ADR-0022) — this directory
mirrors it for review, never the reverse.
