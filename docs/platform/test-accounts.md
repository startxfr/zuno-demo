# Test accounts

Every Keycloak account that is not a person of the demo is a test account. It is named `test-<type>-<name>`, its type is
one of four, and it carries the marker group of its type. The convention is [ADR-0630](../adr/0630-name-every-test-account-test-type-and-give-each-type-its-marker-group.md);
the accounts are declared in `gitops/charts/keycloak/values.yaml` (`evalPersonas`) and created by the Job
`zuno-keycloak-eval-personas`, which creates users and memberships and never deletes.

| Type | Marker group | Accounts | Used by | Quota class |
|---|---|---|---|---|
| `stress` | `/test-stress` | `test-stress-consultant-01`, `-sale-01`, `-adv-01`, `-finance-01`, `-board-01`, `test-stress-mutate-01`, `test-stress-load-01` to `-10` | the stress runner, the day-3 stresstest Jobs, the load pool (`make d3 stresstest`) | `loadtest` |
| `eval` | `/test-eval` | `test-eval-consultant-01`, `-sale-01`, `-adv-01`, `-finance-01`, `-board-01`, `test-eval-ai-dev-01` | RAGAS, the acceptance gate, the probes, the Blender golden path | `evaluation` |
| `func` | none, by design | `test-func-<agent>-entitlement-only-user-01` (6), `test-func-<role>-role-only-user-01` (5) | the functional and security checks that prove a refusal (ADR-0040) | `standard` |
| `demo` | `/test-demo` | none yet | reserved for demo simulation accounts | none |

## Rules

- **Authorization stays with the business group.** A `test-stress-*` or `test-eval-*` account copies the groups of the demo
  persona named in `copyOf`, so it passes exactly the tools and knowledge that persona passes. The marker group adds no
  right: no tool or knowledge policy lists a `test-*` group. It carries the quota class and tells traces and audits that
  the call is a test.
- **A fixture holds one group.** A `test-func-*` account proves that an agent group without a business role, or the reverse,
  is refused. A marker group would add a second group to the account, so fixtures have none.
- **One budget per account.** The ai-gateway keys a token budget by account, so each type has its own budgets and a test run
  never drains the budget of a demo persona.
- **Quota mapping.** `zuno_ai_gateway_quota_loadtest_group` (`test-stress`) and `zuno_ai_gateway_evaluation_group`
  (`test-eval`) in `ansible/inventories/<cluster>/cluster.yml` give the group of each class. `/test-func` and `/test-demo`
  have no class yet: the gateway reads one group per class, and a class per type needs a release of the quota policy.
- **Password.** Every test account shares the personas' password (`zuno_personas_mainpwd`, Secret `demo-personas-password`),
  set again on every run of the Job.

## Accounts of before 2026-11-23

The accounts named `eval-*`, `stress-*` and the eleven `*-only-user-01` fixtures were replaced by the names above. They are
left in Keycloak, unused, until the demo of 2026-11-24 is over, and are then deleted by hand:

```bash
# list them (username only), then delete each one with the Keycloak admin console or `kcadm.sh delete users/<id>`
kcadm.sh get users -r zuno -q max=200 --fields username | grep -E '"(eval-|stress-)|-only-user-01'
```

The groups `/zuno-evaluation` and `/zuno-loadtest` stay until the same moment; no policy maps them any more.
