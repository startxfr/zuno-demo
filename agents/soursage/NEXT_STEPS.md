# Soursage onboarding - remaining steps

Scaffolded by `platform/templates/agent/scaffold_agent.py` (ADR-0307,
WP-41 template), applied **partially** by WP-43 (ADR-0502 Stage-1
parity): only the identity artifacts (`keycloak-fragment.json`, this
checklist) were taken from the generator's output — the existing
hand-authored bundle (`agent.okf.md`, `tasks/coming-soon.md` with
`allowed_tools: []`) was deliberately kept, and no gitops chart,
Applications or evaluations skeleton were generated (they arrive when
someone chooses to build Soursage, per WP-43's own scope). Statuses:

1. ~~**Review/adjust the prose**~~ N/A (WP-43): the hand-authored
   ADR-0349 bundle prose was kept as-is - it already describes the
   intended build (Workday `workday.profile.any.read` + a future
   LinkedIn capability) better than a scaffold skeleton would.
2. ~~**Merge `keycloak-fragment.json`**~~ ALREADY DONE (ADR-0349,
   before this file existed): the `soursage-frontend` confidential
   client and `agent_soursage` group are live in `realm-zuno.json`;
   the fragment here is the reference copy every Stage-1 agent
   carries. Note: the fragment names `recrut` as the business role;
   ADR-0349 scopes Soursage to `recrut` AND `sales` - a
   two-role nuance for the policy step below. No
   `soursage-entitlement-only-user-01` fixture exists yet - add it
   with the first real task.
3. **Add policy entries** - OPEN, deliberately empty today:
   `tasks/coming-soon.md` declares `allowed_tools: []` and no
   knowledge domains, so there is nothing to grant. When real tasks
   are authored, add `recrut` (and `sales` where ADR-0349 intends it)
   to `allowed_groups` for each declared tool/domain - the Workday
   ADR-0340 scoped capability `workday.profile.any.read` is the
   expected first entry.
4. **Register the GitOps Application** - OPEN: no
   `gitops/charts/soursage/` or `gitops/apps/soursage/` exists (WP-43
   scope: charts arrive when someone chooses to deploy Soursage). Run
   the generator's gitops output, or the ADR-0506 split's gitops
   generator, at build time.
5. **Add `soursage` to `ansible/roles/agents/tasks/check.yml`** - OPEN,
   with step 4.
6. **Run the validators** - DONE for the current bundle state (WP-43
   merge: `validate_okf_bundle.py`, `check_knowledge_refs.py`,
   `check_docs.py` all PASS).
7. **Promote** (ADR-0502): follow
   `platform/templates/agent/PROMOTION.md` - the named Stage-1 -> Stage-2
   checklist (scenario review, CR deploy, 75% gate, Stage-2 directory
   content, `zuno.status: active`, README update). Steps 1-6 above are
   its assumed scaffold-time baseline; for Soursage, real tasks (via
   the ADR-0307 template workflow) and an evaluations skeleton come
   first.
