# ADR-0630: Name every test account `test-<type>-<name>` and give each type its marker group

- **Status:** Proposed
- **Target:** v0.18
- **Date:** 2026-11-23
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md) (the negative fixtures),
  [ADR-0624](0624-drive-the-day3-stresstest-from-scenario-drivers-and-named-profiles.md) (the load pool and the `loadtest` class),
  [ADR-0629](0629-give-every-platform-persona-the-cluster-and-aap-tools-and-set-the-agent-data-ceilings.md) (the same review)

## Context

On 2026-11-23 the platform owner asked for the test accounts to share one prefix, `test-` followed by the type of test,
with groups of their own and quotas of their own. The accounts had grown by use: five `eval-*` and one `eval-ai-dev-01`
(evaluations), five `stress-*` twins, `stress-mutate-01` and ten `stress-load-NN` (stress and load), and eleven
`<agent>-entitlement-only-user-01` and `<role>-role-only-user-01` fixtures (security checks). The twins copied the business
groups of a demo persona and shared two marker groups, `/zuno-evaluation` and `/zuno-loadtest`; the fixtures lived in the
realm file with one group each.

## Decision

1. **One name.** A test account is `test-<type>-<name>`, with `<type>` one of `stress`, `eval`, `func`, `demo`.
2. **One marker group per type, except fixtures.** `/test-stress`, `/test-eval` and `/test-demo`. A twin keeps copying the
   business groups of its source persona, which is what gives it the tools and knowledge of that persona; the marker group
   gives it a quota class and nothing else. No policy lists a marker group.
3. **Fixtures keep one group.** A `test-func-*` fixture exists to prove a refusal with exactly one group (ADR-0040), so it has
   no marker group. It has no quota class of its own: a refused call spends no token.
4. **Quota mapping.** `/test-stress` runs under the `loadtest` class and `/test-eval` under the `evaluation` class, through
   `quotaLoadtestGroup` and the new `evaluationGroup` of the ai-gateway chart. `test-stress-mutate-01` moves from `evaluation`
   to `loadtest` with the rest of its type. A class for `func` and `demo` needs the gateway to read a list of groups, and a
   release of the quota policy; it is not part of this decision.
5. **All accounts come from the Job.** The fixtures leave the realm file and join `evalPersonas`, because the realm import is
   create-only and the Job is the one path that reaches a live realm.
6. **No deletion by the platform.** The old accounts stay in Keycloak, unused, until the demo of 2026-11-24 is over; the owner
   deletes them by hand ([test accounts](../platform/test-accounts.md)).

## Consequences

- A test run is told from a demo run by the name and by the marker group, in traces, audit lines and the Keycloak console.
- Scripts, probes and pages that named an old account name the new one; `EVAL_TWIN_PREFIX` defaults to `test-eval-` and the
  day-3 Jobs set `test-stress-`.
- The first sync of the Keycloak chart creates 33 accounts and four groups (32 twins and fixtures, with their memberships);
  until the ai-gateway is given the two group names, the new accounts run under `standard`.
- Old accounts out of the marker groups fall back to `standard` as soon as the gateway names the new groups.
