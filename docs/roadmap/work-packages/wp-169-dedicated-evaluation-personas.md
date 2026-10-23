# WP-169: Dedicated evaluation personas

- **State:** Done (2026-10-23)
- **ADRs:** [ADR-0530](../../adr/0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md) (dated note of 2026-10-23)
- **Depends on:** none
- **Related:** [WP-156](wp-156-retire-zuno-agent-and-rag-code.md), [WP-157](wp-157-slim-the-ai-gateway-via-maas.md)
- **Target:** v0.4 (version of ADR-0530, the decision it notes)
- **Estimated files touched:** ~6 in `zuno-demo` (keycloak chart values, a ConfigMap and a Job, its tests, ADR-0530 note, this brief); the harness switch is a separate change owned by the evaluation harness work.

> Decision of 2026-10-23 (user): evaluations stop signing in as the demo
> personas. On 2026-10-23 repeated acceptance-gate and parity runs as
> `consultant-01` exhausted its ai-gateway daily budget (3M tokens, `standard`
> class); UnifAI then got 429 on every model call and the tekos gate failed
> for a reason unrelated to the change under test. Handled as its own work
> item, with its own Job.

## Goal

The evaluation harnesses, probes and evaluation Jobs sign in as dedicated
`eval-*` personas with the same groups as the demo personas they stand for, so
their token spend lands on their own per-user budget and a presenter's persona
is never starved by a test run.

## Design

- `gitops/charts/keycloak/values.yaml` `evalPersonas`: `eval-consultant-01`,
  `eval-sale-01`, `eval-adv-01`, `eval-finance-01`, `eval-board-01`, each with
  `copyOf`, the realm-file user whose groups it copies. The negative personas
  (`*-entitlement-only-*`, `*-role-only-*`) are refused before any model call,
  spend nothing and keep their own users.
- `templates/configmap-eval-personas.yaml` resolves the groups from
  `files/realm-zuno.json` at render time (one source of truth); an unknown
  `copyOf` fails the render.
- `templates/job-eval-personas.yaml`, an ArgoCD Sync hook after the client
  reconcile (which creates the `agent_*` groups): creates a missing persona,
  sets the shared `demo-personas-password` on every run and adds every missing
  group membership. Nothing is ever deleted. The realm import is create-only
  and ADR-0530's reconcile excludes users, hence this separate Job.
- Budgets: ai-gateway counts per user, so each `eval-*` persona already has
  its own budget. The `eval-` prefix lets a quota policy give them a class of
  their own later if a larger budget is wanted (WP-157).

## Steps

1. Chart values, ConfigMap, Job and tests (`platform/keycloak/tests`).
2. Land on `devel`; on demo333 check the Job log, then sign in as each persona
   through `zuno-evaluations` and compare its `groups` claim with the source
   persona's.
3. The evaluation harness owners switch the harnesses, probes, stresstest,
   RAGAS (`ragasEval.persona`) and the acceptance-gate Job to the `eval-*`
   names.
4. Run `platform/keycloak/tests` in CI (today no workflow runs it).

## Acceptance

Each `eval-*` persona signs in and its token carries exactly the groups of its
source persona; a full acceptance-gate run as `eval-consultant-01` leaves
`consultant-01`'s budget untouched.
