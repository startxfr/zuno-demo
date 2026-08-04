# agents

Applies the agent-surface GitOps Applications: the five namespaces
(`gitops/apps/agents` → `gitops/charts/namespaces`, ADR-0023) and the Tekos
frontend/BFF workloads (`gitops/apps/api` → `gitops/charts/tekos`, ADR-0008).

`main.yml` is what `ansible/playbooks/install.yml` runs for `make install` -
it delegates to `configure.yml`, which applies both Applications in order.
There is no separate `agents` CONFIG_SCOPE (only `api`, see
`ansible/roles/api/README.md`, for re-applying just the Tekos workloads
without touching namespaces) and no separate prepare phase - neither
namespaces nor a plain Deployment/Service/Route have an operator
prerequisite the way Keycloak/Vault/PostgreSQL do.

`check.yml` (`make check`) does a basic HTTP reachability smoke test against
the Tekos frontend's `/healthz` route - the full 20-scenario acceptance
evaluation (ADR-0027/0028) lives under `evaluations/tekos/` and is a
separate concern.
