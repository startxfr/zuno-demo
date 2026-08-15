# aiagent_operator

Day 1 `run` component (`make day1|d1 install|check|uninstall aiagent-operator`).
Deploys the AIAgent CRD + operator manager (ADR-0327/ADR-0308,
`gitops/charts/aiagent-operator`) via its GitOps Application
(`gitops/apps/aiagent-operator`). No Day 0 prerequisite - same no-op `d0`
shape as `ansible/roles/mcp`.

Any agent chart that has migrated to a CR (see `gitops/charts/arkos/`,
this repo's migration proof) depends on this component's Application
having synced first - its own Application's sync-wave (-106) is earlier
than every agent chart's own (-103 and later), so a single `make day1
install` run converges correctly regardless of task order; this role
exists as its own component mainly so `make day1 check|uninstall
aiagent-operator` can target it independently.

`precheck.yml` only checks the Application sync/health state, the same
state-detection pattern every other Day 1 run role uses - it does not yet
consume the operator's own `status.conditions` on any `AIAgent` CR
(`ansible/roles/agents/tasks/check.yml` does that, for the CR-managed
agents specifically - see that role's own README).
