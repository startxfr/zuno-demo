# namespaces

Applies the namespace-scaffolding GitOps Application (`gitops/apps/namespaces`
→ `gitops/charts/namespaces`, ADR-0023): the 5 agent namespaces + the
`zuno-auth`/`zuno-data`/`zuno-telemetry`/`zuno-ai-run`/`zuno-ai-build`
platform namespaces, each with a `ResourceQuota` and a default-deny
`NetworkPolicy` baseline. A Day 0 component (ADR-0056) - moved out of
`ansible/roles/agents` so namespace creation is its own explicit,
checkable step rather than only ever happening as a side effect of
deploying the Tekos workloads.

Namespace objects are cluster-scoped, so this component's entire content
is `-d0` (`zuno-namespaces-d0`) - `-d1` (`zuno-namespaces-d1`) is a no-op,
applied anyway for the uniform two-Application pattern every component
follows (see `gitops/apps/README.md`). The formerly orphaned
`gitops/apps/agents/` directory (a stale duplicate of this same chart,
never applied by any role) has been removed.

- `precheck.yml` - state detection, never fails: checks both the
  `zuno-namespaces-d0` and `zuno-namespaces-d1` Applications' Synced+Healthy
  status, setting `namespaces_state_installed` and a line in the shared
  `/tmp` state report (see `ansible/playbooks/day0_check.yml`).
- `install.yml` - applies both GitOps Applications (idempotent - ArgoCD's
  own `selfHeal: true` also reconciles continuously on its own cycle, but
  re-running this role gives an explicit on-demand re-sync after a
  `values.yaml` change).

`ansible/roles/agents` still exists and still applies the `api` (Tekos
workloads) Applications - it no longer applies this one.
