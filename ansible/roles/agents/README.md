# agents

Applies the Tekos frontend/BFF workloads GitOps Application
(`gitops/apps/api` → `gitops/charts/tekos`, ADR-0008). This is Day 1's
`agents` `run` component (ADR-0056) - `precheck.yml` verifies ArgoCD is
installed and that `zuno-agent-tekos` (created by the Day 0 `namespaces`
role) already exists.

Namespace creation used to live in this role's `configure.yml` too (a
separate `gitops/apps/agents` → `gitops/charts/namespaces` Application
apply); it moved to the new Day 0 `ansible/roles/namespaces` role
(ADR-0056), so this role no longer touches namespaces at all - `make d0
install namespaces` must run first. The formerly separate `api` role/
CONFIG_SCOPE was retired in the same change: once this role stopped
applying namespaces, it was doing exactly what `api` did (apply the
Tekos workloads Application, nothing else) - one role for that job is
enough, and `agents` is the name Day 1's `run` component list uses.

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
0037/0040) as a one-shot in-cluster Job in `zuno-ai-run` - see that file's own
header comment for why a Job (most of what the gate calls has no
OpenShift Route) and for the "acceptance-gate" workload identity's narrow
NetworkPolicy allowances.
