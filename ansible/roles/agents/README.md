# agents

Applies each real agent's frontend/BFF workloads GitOps Application:
Tekos's (`gitops/apps/api` → `gitops/charts/tekos`, ADR-0008) and, since
WP-31 (ADR-0326), Arkos's (`gitops/apps/arkos` → `gitops/charts/arkos`,
kept a distinct app-directory name rather than reusing `api`'s legacy
name so a third/fourth agent's Application doesn't have to fight over
it). This is Day 1's `agents` component (ADR-0056) - `precheck.yml`
reports (never fails) whether every one of the `zuno-{api,arkos}-{d0,d1}`
Applications is Synced+Healthy. No operator involved, so all of this
component's content is `-d1` - the `-d0` Applications are no-ops (see
`gitops/apps/README.md`).

Namespace creation used to live in this role too (a separate
`gitops/apps/agents` → `gitops/charts/namespaces` Application apply); it
moved to the new Day 0 `ansible/roles/namespaces` role (ADR-0056), so
this role no longer touches namespaces at all - `make d0 install
namespaces` must run first. The formerly separate `api` role/
CONFIG_SCOPE was retired in the same change: once this role stopped
applying namespaces, it was doing exactly what `api` did (apply the
Tekos workloads Application, nothing else) - one role for that job is
enough, and `agents` is the name Day 1's component list uses.

`check.yml` (`make day1|d1 check agents`) is the ADR-0053 layered
acceptance and security gate - `day1_check.yml` runs it *instead of*
`precheck.yml` for this role specifically (a full functional/security
gate is a stronger "is this installed and working" signal than a
lightweight Application state check). `precheck.yml` still exists for
file-layout consistency but is never invoked while that special case is
in place. It structurally validates the four catalog-only agents'
`agent.okf.md` OKF v0.2 Markdown bundles (ADR-0038 -
`okf_version`/`type`/`zuno.status: placeholder`) - v0 formalizes Tekos as
the only mandatory end-to-end business path (ADR-0031), but catalog-only is
not the same as unchecked. Arkos (ADR-0326/WP-31) deliberately stays in
that same structural-check loop even though its bundle/graph-shape/chart
are all real now: `zuno.status` stays `placeholder` until the operator
confirms the live acceptance gate passes, so it still correctly reports
`placeholder` here. The check then does a basic HTTP reachability smoke
test against both the Tekos AND Arkos frontends' `/healthz` routes (Arkos
gets a smoke test, never its behavioral gate - `evaluations/arkos/`
requires the human scenario review WP-31's brief gates on first), then
hands off to `run_acceptance_gate.yml`, which runs `evaluations/tekos/`'s
full gate (the 20-scenario acceptance evaluation at a 75% threshold,
ADR-0027/0028, plus every mandatory security-negative check,
ADR-0032/0033/0034/0035/0037/0040) as a one-shot in-cluster Job in
`zuno-ai-run` - see that file's own header comment for why a Job (most of
what the gate calls has no OpenShift Route) and for the "acceptance-gate"
workload identity's narrow NetworkPolicy allowances. Once Arkos's own
scenarios are reviewed and its status flips to `active`, running its own
`evaluations/arkos/run_acceptance_gate.py` the same way becomes the
operator's job, not this role's default automatic path.
