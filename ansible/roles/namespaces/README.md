# namespaces

Applies the namespace-scaffolding GitOps Application (`gitops/apps/namespaces`
→ `gitops/charts/namespaces`, ADR-0023): the 5 agent namespaces + the
`zuno-auth`/`zuno-data`/`zuno-telemetry`/`zuno-ai-run`/`zuno-ai-build`
platform namespaces, each with a `ResourceQuota` and a default-deny
`NetworkPolicy` baseline. A Day 0 component (ADR-0056) - moved out of
`ansible/roles/agents` so namespace creation is its own explicit,
checkable step rather than only ever happening as a side effect of
deploying the Tekos workloads. (`gitops/apps/agents` is a stale, orphaned
directory left over from before this move - nothing applies it any more.)

- `precheck.yml` - state detection, never fails: checks the
  `zuno-namespaces` Application's Synced+Healthy status, setting
  `namespaces_state_installed` and a line in the shared `/tmp` state
  report (see `ansible/playbooks/day0_check.yml`).
- `install.yml` - applies the GitOps Application (idempotent - ArgoCD's
  own `selfHeal: true` also reconciles continuously on its own cycle, but
  re-running this role gives an explicit on-demand re-sync after a
  `values.yaml` change).

`ansible/roles/agents` still exists and still applies the `api` (Tekos
workloads) Application - it no longer applies this one.
