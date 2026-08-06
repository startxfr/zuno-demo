# namespaces

Applies the namespace-scaffolding GitOps Application (`gitops/apps/agents`
→ `gitops/charts/namespaces`, ADR-0023): the 5 agent namespaces + the
`zuno-auth`/`zuno-data`/`zuno-telemetry`/`zuno-ai-run`/`zuno-ai-build`
platform namespaces, each with a `ResourceQuota` and a default-deny
`NetworkPolicy` baseline. A Day 0 component (ADR-0056) - moved out of
`ansible/roles/agents` so namespace creation is its own explicit,
checkable step rather than only ever happening as a side effect of
deploying the Tekos workloads.

- `precheck.yml` - reads the expected namespace list directly from
  `gitops/charts/namespaces/values.yaml` (never duplicated as a separate
  hardcoded list, so it can't drift from what the chart actually creates)
  and fails, naming exactly which are missing, if any expected namespace
  isn't present.
- `install.yml` - applies the GitOps Application.
- `configure.yml` - re-applies the same Application (idempotent - for an
  explicit on-demand re-sync after a `values.yaml` change, since ArgoCD's
  own `selfHeal: true` already reconciles continuously on its own cycle).

`ansible/roles/agents` still exists and still applies the `api` (Tekos
workloads) Application - it no longer applies this one.
