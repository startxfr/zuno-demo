# Ansible Automation

Ansible is a thin bootstrapper behind the public `make` interface, not the
configuration engine — see ADR-0022 and ADR-0024. It exists to get from
"a bare cluster-admin token" to "ArgoCD is reconciling everything else":

1. `make precheck` / `make prepare` walk `PREP_COMPONENTS` in order
   (`openshift-ai`, `datascience`, `nvidia-gpu`, `argocd`, `vault`,
   `external-secrets`, `keycloak`, `postgresql`, `observability`, `smtp`).
   `argocd` installs the OpenShift GitOps operator; `vault` installs itself
   as a GitOps Application, then imperatively initializes/unseals (the one
   component that can't depend on Vault for its own bootstrap secret);
   `external-secrets` installs the operator.
2. `make configure` walks `CONFIG_SCOPES` in order (`vault`,
   `external-secrets`, `argocd`, then the business scopes). `vault`
   configures the Kubernetes auth method and `eso-reader` policy/role;
   `external-secrets` registers the `ClusterSecretStore` against it;
   `argocd` applies the root App-of-Apps (`gitops/root-app-of-apps.yaml`).
   Every scope after that applies its own child ArgoCD `Application` under
   `gitops/apps/<scope>/` via the shared task
   `ansible/tasks/apply_gitops_app.yml`, rather than configuring anything
   inline — ArgoCD reconciles the referenced Helm chart or local manifest.

No secret is ever written to a Git-tracked file. Anything a role needs at
run time comes from Vault via the `community.hashi_vault` lookup plugin;
anything a workload needs comes from an `ExternalSecret`.

Install the required collections once: `ansible-galaxy collection install -r requirements.yml`.

Every role keeps the existing `precheck` / `prepare` / `configure` task
split so `make precheck <component>`, `make prepare <component>` and
`make configure <scope>` remain independently runnable.
