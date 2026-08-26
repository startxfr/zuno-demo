# Cognos onboarding - remaining steps

Scaffolded by `platform/templates/agent/scaffold_agent.py` (ADR-0307,
WP-41 template), applied **partially** by WP-43 (ADR-0502 Stage-1
parity): only the identity artifacts (`keycloak-fragment.json`, this
checklist) were taken from the generator's output — the existing
hand-authored bundle (`agent.okf.md`, `tasks/coming-soon.md` with
`allowed_tools: []`) was deliberately kept, and no gitops chart,
Applications or evaluations skeleton were generated (they arrive when
someone chooses to build Cognos, per WP-43's own scope). Statuses:

1. ~~**Review/adjust the prose**~~ N/A (WP-43): the hand-authored
   ADR-0349 bundle prose was kept as-is - it already describes the
   intended build better than a scaffold skeleton would.
2. ~~**Merge `keycloak-fragment.json`**~~ ALREADY DONE (ADR-0349,
   before this file existed): the `cognos-frontend` confidential client
   and `agent_cognos` group are live in `realm-zuno.json`; the fragment
   here is the reference copy every Stage-1 agent carries. Note: no
   `cognos-entitlement-only-user-01` fixture exists yet - add it with
   the first real task (it only matters once there is a tool boundary
   to prove).
3. **Add policy entries** - PARTIALLY DONE (2026-08-21; domain repointed
   2026-08-26 by ADR-0219): `tasks/review-historical-commercial-data.md`
   declares `allowed_knowledge: [knowledge.sxa-legacy]`; `board` is present
   in that domain's `allowed_groups` (`policies/knowledge/
   knowledge-policy.yaml`), so no policy edit was needed for this grant
   before or after the repoint. `tasks/coming-soon.md` still declares `allowed_tools: []` and
   no knowledge domains - still nothing to grant there. Remaining tools/
   domains from the intended build (ADR-0349 §6) still need this same
   step when their real tasks are authored.
4. **Register the GitOps Application** - OPEN: no
   `gitops/charts/cognos/` or `gitops/apps/cognos/` exists (WP-43
   scope: charts arrive when someone chooses to deploy Cognos). Run
   the generator's gitops output, or the ADR-0506 split's gitops
   generator, at build time.
5. **Add `cognos` to `ansible/roles/agents/tasks/check.yml`** - OPEN,
   with step 4.
6. **Run the validators** - DONE for the current bundle state (WP-43
   merge: `validate_okf_bundle.py`, `check_knowledge_refs.py`,
   `check_docs.py` all PASS).
7. **Promote** (ADR-0502): follow
   `platform/templates/agent/PROMOTION.md` - the named Stage-1 -> Stage-2
   checklist (scenario review, CR deploy, 75% gate, Stage-2 directory
   content, `zuno.status: active`, README update). Steps 1-6 above are
   its assumed scaffold-time baseline; for Cognos, real tasks (via the
   ADR-0307 template workflow) and an evaluations skeleton come first.
