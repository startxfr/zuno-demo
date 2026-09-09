# WP-142: Parallel, quota-exhaustive Day 3 stresstest

- **State:** Done (2026-09-09 - parallel execution + request-rate proof
  live-verified; token-budget proof code-complete, needs an ai-gateway
  rebuild before its live behavior is genuine exhaustion, not a fail-closed
  unknown-class 429 - see ADR-0555's Known out-of-scope gaps)
- **ADRs:** ADR-0555
- **Related:** ADR-0058, ADR-0511
- **Target:** v0.5

## Goal

Make `make d3 stresstest` stress arkos/tekos/comage in parallel by default
(with a `SEQUENTIAL=1` opt-out), and make every stresstest-covered agent's
run include a scenario that deliberately drives a Kuadrant/Limitador
request-rate limit to 429 (generalizing the existing Tekos-only proof) and
a scenario that deliberately drives a token budget to exhaustion - both
counted as an expected, positive PASS - without lowering the `standard`/
`intensive` quota classes real demo traffic depends on.

## Implementation

1. **Parallel-by-default execution**: split
   `ansible/roles/day3/tasks/stresstest_job_run_one.yml` into
   `stresstest_job_create_one.yml` + `stresstest_job_wait_one.yml`.
   `stresstest_job.yml` runs a create-all-then-wait-all pair of loops by
   default (`day2_stresstest_parallel: true`) or the original combined file
   when `SEQUENTIAL=1` is passed. No async/poll/JobSet - Job creation is
   near-instant, so every agent's Job is already running concurrently by
   the time the wait loop starts, bounding total wall-clock by the slowest
   agent instead of the sum of all of them.
2. **Makefile**: new `SEQUENTIAL=<0|1>` var on `make d3 stresstest`,
   threaded to both the AAP JSON payload and the direct ansible-playbook
   fallback as `day2_stresstest_parallel`. No AAP survey_spec change
   needed.
3. **Generalized request-rate 429 proof**: `gitops/charts/connectivity-link`'s
   `quotaEnforcement` moved from a single Tekos-only route to a `routes:`
   list (tekos/arkos/comage), with `quota-demo-route.yaml`,
   `quota-demo-gateway.yaml`'s per-agent OpenShift Route, and the generated
   `quota-ratelimitpolicies.yaml` (via `generate_quota_enforcement.py`) all
   looping over it. Both `connectivity-link`/`connectivity-link-quota`
   Applications carry the matching `routes:` list.
   `platform/testing/quota_429.py`'s Tekos-only gate is now
   `tekos/arkos/comage`, and its demo-URL builder is agent-parameterized.
4. **New token-budget exhaustion proof**: dedicated `stresstest` quota
   class in `policies/quotas/quota-policy.yaml` (2,000 tokens/5m/user,
   deliberately tiny to keep GPU cost marginal), never touching
   `standard`/`intensive`. New `platform/testing/token_quota_429.py`,
   wired into `day2_stresstest.py` as a `token_quota` layer: sends short
   real chat calls tagged `X-Zuno-Quota-Class: stresstest` directly to AI
   Gateway until a 429 fires, asserted as PASS.
5. **Verified, not changed**: `day2_bulk.py`'s bulk-load corpus already
   cycles through enough distinct per-agent tasks to route across multiple
   local models (`model-routing-policy.yaml` already gives different tasks
   different preferred-model orderings) - no new scenario variety needed.

## Acceptance criteria

- [x] `helm lint`/`helm template gitops/charts/connectivity-link` (with
  `quotaEnforcement.route.enabled=true`) renders exactly 3 uniquely-named
  HTTPRoutes/AuthPolicies/RateLimitPolicies/gateway-Routes (tekos/arkos/
  comage).
- [x] `python3 platform/okf/generate_quota_enforcement.py --check` and
  `python3 platform/okf/validate_quota_policy.py` pass with the new
  `stresstest` class present.
- [x] `ansible-playbook --syntax-check` on `ansible/playbooks/
  day3_stresstest.yml` passes; `ansible-lint` on the split task files shows
  no NEW violations versus the original, unmodified file (same pre-existing
  `_day2_stress_*` naming-convention warnings either way).
- [x] `python3 platform/docs/check_docs.py` and
  `python3 platform/security/check_workload_hardening.py` both pass (the
  latter's one failure, `ai-gateway`'s `MAAS_SA_TOKEN_PATH`, is
  pre-existing and unrelated - confirmed via `git stash` comparison in an
  earlier session).
- [x] `token_quota_429.py` live-tested standalone (port-forward to
  `ai-gateway`, a real Keycloak token for `consultant-01`, `AI_GATEWAY_URL`/
  `TOKEN_QUOTA_TOKEN` overrides): gets a real 429 from AI Gateway's ledger,
  confirming the request/response/classification plumbing is correct end
  to end - not yet genuine budget-exhaustion behavior until ai-gateway is
  rebuilt with the regenerated `quota_budgets.yaml` (see ADR-0555's Known
  out-of-scope gaps).
- [ ] Live: `make d3 stresstest` (parallel, default) - confirm via `oc get
  jobs -n zuno-ai-run` that all 3 agent Jobs run concurrently and total
  wall-clock is close to the slowest single agent. Not yet re-run after
  this WP's own changes landed - the in-progress run this session started
  from predates them.
- [ ] Live, after `make d2 build ai-gateway` + redeploy: `token_quota`
  layer shows a genuine post-exhaustion 429 (not an immediate one) for
  tekos/arkos/comage.
- [x] `git status` on every `zuno-monitoring`/Grafana/Kiali-owning chart
  shows no changes from this work.

## Status updates

- **2026-09-09 — Done, one follow-up rebuild pending.** Parts 1-3
  (parallel execution, Makefile `SEQUENTIAL=`, request-rate 429
  generalization) are fully live-capable with this session's changes alone
  - no rebuild needed, GitOps/Ansible only. Part 4 (token-budget proof) is
  code-complete and unit-verified live (real 429 from AI Gateway's ledger,
  correct plumbing) but needs `make d2 build ai-gateway` before its
  behavior matches the intended "genuine exhaustion after ~15 calls"
  rather than "immediate fail-closed 429 for an unknown class" - the image
  bakes `quota_budgets.yaml` in at build time, it is not a live-synced
  ConfigMap. Also discovered and documented, not fixed: RHOAI MaaS's own
  Kuadrant TokenRateLimitPolicy (`/sales` tier) is unreachable by any
  persona today because `ModelsAsService.spec.externalOIDC` is unset -
  a separate, larger, cluster-wide MaaS-authentication decision, correctly
  out of scope for this WP.
