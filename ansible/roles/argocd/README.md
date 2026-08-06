# argocd

Installs the OpenShift GitOps (ArgoCD) operator and applies the root
App-of-Apps (`gitops/root-app-of-apps.yaml`). This is the mechanism that
turns a bare cluster-admin token into a fully configured platform: every
other component's `configure` step is either driven by this Application or
independently reapplies its own child Application (see
`ansible/tasks/apply_gitops_app.yml`).

Runs first among prerequisite components - see
`ansible/playbooks/{precheck,install}.yml`.
