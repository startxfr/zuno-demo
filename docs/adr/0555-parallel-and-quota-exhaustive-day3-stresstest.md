# ADR-0555: Parallel-by-default Day 3 stresstest, generalized quota/limit exhaustion proofs

- **Status:** Implemented (parallel execution, the request-rate proof
  generalization, and the new token-budget proof all live-verified
  2026-09-09, the latter after a `make d1 build ai-gateway` + redeploy -
  see Known out-of-scope gaps)
- **Target:** v0.5
- **Date:** 2026-09-09
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md)
  (the per-agent stresstest this ADR reshapes the execution model of),
  [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md) (the
  quota-policy source and the original, Tekos-only request-rate 429 proof
  this ADR generalizes). Neither is superseded.

## Context

`make d3 stresstest` ran arkos/tekos/comage's stresstest Jobs strictly
sequentially - one agent's Job fully created, waited-on (up to a 40-minute
budget each) and its log parsed before the next agent's Job was even
created (`ansible/roles/day3/tasks/stresstest_job.yml`'s single `loop:` over
`stresstest_job_run_one.yml`). A 3-agent run's wall-clock was the sum of all
three, not the slowest one.

Separately, this repo already had exactly one live proof that "deliberately
exceeding a Kuadrant/Limitador limit and getting a 429 is the *expected,
positive* result" (`platform/testing/quota_429.py`, ADR-0511/WP-54) - but it
was hardcoded to Tekos only, and covered only the request-RATE dimension
(a GET-only demo Route, no real inference cost). No token-BUDGET
exhaustion proof existed anywhere in the repo.

## Decision

### A. Parallel by default, sequential opt-in

Split `stresstest_job_run_one.yml` (create-then-block-wait-then-parse, one
per agent) into `stresstest_job_create_one.yml` (Job creation only) and
`stresstest_job_wait_one.yml` (wait/fetch/parse only). `stresstest_job.yml`
now runs, controlled by `day2_stresstest_parallel` (default `true`):

- **Parallel (default):** the create loop runs to completion for every
  agent first (near-instant), so every agent's Job is already running
  concurrently on the cluster by the time the wait loop starts. The wait
  loop is still sequential in Ansible's own execution order, but each
  iteration only "catches up" to whichever Job already finished while an
  earlier iteration was waiting - total wall-clock becomes
  `max(agent durations)`, not `sum(agent durations)`, with zero
  `async:`/`poll:`/JobSet machinery (async cannot cleanly wrap a whole
  `include_tasks:` file; nothing about the per-agent Job specs needed to
  change, only how creation vs waiting is sequenced).
- **Sequential (`make d3 stresstest SEQUENTIAL=1`):** calls the original,
  unmodified `stresstest_job_run_one.yml` - byte-identical to every run
  before this ADR.

Threaded through the Makefile as `SEQUENTIAL=<0|1>` ->
`-e day2_stresstest_parallel=<true|false>`, on both the AAP JSON payload and
the direct `ansible-playbook` fallback. No AAP `survey_spec` change needed -
`zuno-day3-stresstest`'s Job Template already accepts arbitrary extra_vars
via `askVariablesOnLaunch: true`.

### B. Generalize the request-rate 429 proof to every stresstest-covered agent

`gitops/charts/connectivity-link`'s `quotaEnforcement` moved from a single
Tekos-only route (`routeName`/`demoHostname`/`demoBackendService`/
`demoBackendPort` scalars) to a `routes: [...]` list, one entry per agent
(tekos/arkos/comage, each's own `<agent>-frontend` backend). Every template
that used to render ONE HTTPRoute/AuthPolicy/RateLimitPolicy/gateway-Route
now `{{- range }}`s over that list:

- `templates/quota-demo-route.yaml` (HTTPRoute + AuthPolicy, Day2
  `zuno-connectivity-link-quota-d1` Application)
- `templates/quota-demo-gateway.yaml`'s OpenShift `Route` object (the
  Gateway/ConfigMap/Service stay SHARED - Gateway API dispatches by Host
  header at the HTTPRoute layer, only the OpenShift Route fronting it is
  one-hostname-per-object)
- `platform/okf/generate_quota_enforcement.py`'s `_render_rlp()` (GENERATED
  file `templates/quota-ratelimitpolicies.yaml` - one `RateLimitPolicy` per
  route now, `zuno-quota-<route-name>`, each still holding every quota
  class's per-dimension limits, since Kuadrant allows only one
  RateLimitPolicy per targetRef)

Both `gitops/apps/connectivity-link/application-d1.yaml` (Day1, gateway
half) and `gitops/apps/connectivity-link-quota/application-d1.yaml` (Day2,
route half) carry the same `routes:` list in their inline Helm values
(duplicated between the two Applications, matching the pre-existing
`demoHostname` duplication this generalizes from - both MUST agree, a
mismatch here already had a live incident, see application-d1.yaml's own
comment). `ansible/tasks/apply_gitops_app.yml`'s domain-token substitution
is a blanket string replace across the whole values block, confirmed safe
with any number of `apps.mycluster.example.com` occurrences before relying
on it for three.

`platform/testing/quota_429.py`'s Tekos-only gate is now
`AGENT not in ("tekos", "arkos", "comage")`, and `_demo_url()` builds
`https://<agent>-quota-demo.<domain>` instead of the hardcoded
`tekos-quota-demo` prefix. No other change needed - `_auth_headers()`/burst/
classify logic was already agent-agnostic.

### C. New token-budget exhaustion proof (AI Gateway's own ledger)

New dedicated `stresstest` quota class in `policies/quotas/quota-policy.yaml`
- deliberately tiny (2,000 tokens/5m per user) so ~10-20 short real chat
calls exhaust it, keeping the real-inference/GPU cost of proving
enforcement marginal on this cluster's already-tight GPU quota (see the
2026-09-04 GPU-quota-saturated incident). `standard`/`intensive` are
untouched - they were deliberately raised 2026-09-02 after a real
stresstest run legitimately consumed ~1.2M tokens against the old, too-low
ceiling, and re-tightening either to make an exhaustion proof cheaper would
risk breaking real demo traffic.

New `platform/testing/token_quota_429.py`, wired into
`day2_stresstest.py::main()` as a new `token_quota` layer alongside the
existing `quota` layer: sends short real `X-Zuno-Quota-Class: stresstest`
chat calls directly to AI Gateway (`/v1/chat/completions`, same in-cluster
direct-call pattern `evaluations/*/security_checks.py` already uses) until
a 429 is observed (`quota.ledger.check()` -> `app/main.py`'s
`status_code=429`), and asserts that 429 as the expected, positive result -
same "a 429 anywhere proves enforcement" philosophy as `quota_429.py`'s own
`_classify()`.

## Known out-of-scope gaps

- **RHOAI MaaS's own Kuadrant TokenRateLimitPolicy (the `/sales`
  MaaSSubscription tier, `gitops/charts/models/values.yaml`) is NOT what
  Part C exercises**, even though it is the more literal "Limitador +
  Authorino, token dimension" mechanism. Live-verified 2026-09-09: that
  path is currently unreachable by any persona-driven request at all -
  `maas-gateway-auth`'s AuthPolicy (`openshift-ingress`) only accepts
  `Bearer sk-oai-*` API keys or Kubernetes ServiceAccount TokenReview, no
  Keycloak-JWT authentication rule, because `ModelsAsService.spec.
  externalOIDC` (the flag `components/ai-gateway/app/maas_adapter.py`'s own
  comment names as the prerequisite) is not set on this cluster. A `sale-01`
  (`/sales`-group demo persona) Keycloak token sent straight at
  `https://maas.<domain>/zuno-ai-run/gpt-oss-20b/v1/chat/completions`
  returns 401. Enabling `externalOIDC` is a separate, cluster-wide MaaS
  authentication decision with its own security review, not something to
  fold into a stresstest scenario - left open for a future ADR.
- **The `token_quota` layer needed a `make d1 build ai-gateway` + redeploy
  before it proved genuine budget exhaustion.** `quota_budgets.yaml`
  (regenerated by `generate_quota_enforcement.py`) is baked into the
  ai-gateway container image at build time, not mounted from a live-synced
  ConfigMap - confirmed live 2026-09-09: before the rebuild, the deployed
  pod's `/app/app/quota_budgets.yaml` had no `stresstest` class, so
  `token_quota_429.py` got an immediate 429 from `quota.py`'s fail-closed
  handling of an *unknown* class rather than genuine exhaustion (still a
  real, correctly-classified PASS - an unknown class failing closed is
  itself a legitimate safety property, just not proof of the intended
  budget-tracking behavior). After the rebuild (commit `05333171`, signed,
  auto-rolled out via the Deployment's `ImageChangeTrigger`, confirmed live
  in the pod's `/app/app/quota_budgets.yaml`) a full `make d3 stresstest
  agents` run showed the intended behavior: tekos hit 429 at call 4/24 and
  comage at call 7/24, several real chat calls in between (some timing out
  under GPU load rather than returning instantly - real inference, not an
  instant reject) before the `stresstest` class's 2,000-token/5m ceiling
  was crossed; arkos passed the same assertion in the same run.
- Multi-model coverage in `day2_bulk.py`'s corpus (the "exhaustive
  multi-model usage" ask) needed no code change: `policies/model-routing/
  model-routing-policy.yaml` already gives different tasks per agent
  different preferred-model orderings (e.g. Tekos's `answer-technical-
  question` prefers gpt-oss variants first, `find-relevant-docs`/`check-
  my-drive-docs` prefer qwen35/wesh variants first), and `day2_bulk.py`'s
  corpus already cycles through every message-bearing scenario per agent -
  verified, not changed. Per-call model-routing visibility in the run's own
  log output was considered and dropped: `day2_bulk.py` calls
  `BFF_URL/api/chat` through the full agent-runtime/BFF stack, and neither
  layer forwards ai-gateway's own `zuno_provider`/model fields back to the
  caller - surfacing that would need a BFF/agent-runtime response-shape
  change, out of scope for a stresstest-harness ADR.

## Security considerations

No RBAC/NetworkPolicy widening: parallel execution reuses each agent's
already-independent Job spec unchanged; the generalized quota-demo Routes
extend an existing, reviewed pattern (Keycloak JWT + Kuadrant rate limiting)
to two more already-public agent frontends, nothing new port- or
credential-wise; the new `stresstest` quota class is additive and
`fail_mode: closed`, touching no existing class's enforcement.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Acceptance criteria and Review evidence.

## Migration / evolution

If `ModelsAsService.spec.externalOIDC` is ever enabled (a separate,
future decision), revisit whether `token_quota_429.py` should switch to
proving the `/sales` MaaSSubscription tier directly instead of (or in
addition to) AI Gateway's own ledger - record that as a dated correction
note here rather than a silent behavior change.
