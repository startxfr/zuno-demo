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

`check.yml` (`make check`) is the ADR-0053 layered acceptance and security
gate. It structurally validates the four catalog-only agents'
`agent.okf.md` OKF v0.2 Markdown bundles (ADR-0038 -
`okf_version`/`type`/`zuno.status: placeholder`) - v0 formalizes Tekos as
the only mandatory end-to-end business path (ADR-0031), but catalog-only is
not the same as unchecked - then does a basic HTTP reachability smoke test
against the Tekos frontend's `/healthz` route, then hands off to
`run_acceptance_gate.yml`, which runs `evaluations/tekos/`'s full gate
(the 20-scenario acceptance evaluation at a 75% threshold, ADR-0027/0028,
plus every mandatory security-negative check, ADR-0032/0033/0034/0035/
0037/0040) as a one-shot in-cluster Job in `zuno-ai` - see that file's own
header comment for why a Job (most of what the gate calls has no
OpenShift Route) and for the "acceptance-gate" workload identity's narrow
NetworkPolicy allowances.
