# WP-333: Name the test accounts `test-<type>-<name>` and give each type its marker group

- **State:** Done (applied to demo333 on 2026-11-23)
- **ADRs:** [ADR-0630](../../adr/0630-name-every-test-account-test-type-and-give-each-type-its-marker-group.md)
- **Depends on:** none
- **Target:** v0.18
- **Estimated files touched:** ~85: the Keycloak chart (`evalPersonas`, the realm file), the ai-gateway chart and the `llm` role, the stress and evaluation scripts and tests, the demo pages

## Goal

Every test account is `test-<type>-<name>` with the marker group of its type, the two quota classes follow the marker
groups, and the harnesses sign in as the new accounts.

## Work

1. `evalPersonas`: 33 accounts named `test-stress-*`, `test-eval-*`, `test-func-*` and the four marker groups; the fixtures
   leave `realm-zuno.json`.
2. ai-gateway chart: `evaluationGroup`; inventory `zuno_ai_gateway_quota_loadtest_group: test-stress`,
   `zuno_ai_gateway_evaluation_group: test-eval`.
3. Harnesses: `EVAL_TWIN_PREFIX`, `STRESS_PERSONAS`, the RAGAS persona, the probes, the checks and their tests.
4. Pages and the convention table ([test accounts](../../platform/test-accounts.md)).
5. Apply: sync the Keycloak chart (the Job creates the accounts), then the ai-gateway; a short stress run.

## Acceptance criteria

- The Job reports 33 accounts present; each `test-stress-*` and `test-eval-*` account holds its marker group and the groups of its source.
- A short stress run signs in as `test-stress-*` and its calls run under `loadtest`; `make d2 check agents` passes.
- The tests of `platform/keycloak`, `evaluations`, `components/ai-gateway` and `platform/demo` pass.

## Review evidence

2026-11-23, demo333: the Keycloak Job created 33 accounts and 212 memberships; three of them signed in with the personas value.
The ai-gateway runs with `QUOTA_LOADTEST_GROUP=test-stress` and `EVALUATION_GROUP=test-eval`. `make d2 check agents`: 18/19
scenarios, 14/14 security checks, 5/5 gate checks. `make d3 stresstest PROFILE=smoke` through AAP (job 1658): 13/13 rows
passed as the `test-stress-*` accounts. The `mutating` profile has not run under the `loadtest` class yet.
