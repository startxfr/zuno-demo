# Naveo onboarding - remaining steps

Scaffolded by `platform/templates/agent/scaffold_agent.py` (ADR-0307,
WP-41). Steps 1-6 were completed in the WP-41b merge itself (statuses
below); 7-8 remain - the same human-review + live-gate bar every
hand-built agent clears.

1. ~~**Review/adjust the prose**~~ DONE (WP-41b): the scaffolded persona
   was kept - a deliberately simple synthetic persona (ADR-0410:
   "synthetic persona, existing knowledge domains and capabilities only")
   whose prompt file additionally gained the OKF `type: prompt`
   frontmatter the generator originally omitted (a real generator bug the
   agent-runtime suite caught; fixed in the generator too).
2. ~~**Merge `keycloak-fragment.json`**~~ DONE (WP-41b):
   `naveo-frontend` confidential client + `agent_naveo` group +
   `naveo-entitlement-only-user-01` fixture merged into
   `realm-zuno.json`; `consultant-user-01` also gained `/agent_naveo`
   (the persona-membership judgment call the generator deliberately
   leaves to a human); `externalsecret-naveo-frontend.yaml`,
   `templates/keycloak.yaml` vault-file mount, and both Vault seeds
   (`keycloak/naveo-frontend`, `naveo/frontend-session`) registered.
3. ~~**Add policy entries**~~ DONE (WP-41b) - as zero edits: `consultant`
   was ALREADY in `allowed_groups` for every declared tool
   (search_confluence, web_search, list_drive_files) and knowledge domain
   (knowledge.tech, knowledge.project) - the cleanest possible ADR-0410
   proof that a template agent composes existing capabilities without
   widening any policy.
4. ~~**Register the GitOps Application**~~ DONE (WP-41b): sync-wave -96
   (after Finage's -97; the operator's own -106 is far earlier) plus
   `ansible/roles/agents` install/uninstall/precheck entries.
5. ~~**Add `naveo` to check.yml**~~ DONE (WP-41b): structural
   placeholder check + frontend reachability smoke test.
6. ~~**Run the validators**~~ DONE (WP-41b): all PASS (6 OKF bundles).
7. **Human review checkpoint**: review the 20 scenarios in
   `evaluations/naveo/scenarios.yaml` before any live gate run counts
   (ADR-0326's own completion pattern).
8. **Operator**: deploy via the `AIAgent` CR (needs the aiagent-operator
   deployed first - WP-38's own pending cluster step), run the 75% gate,
   flip `agents/naveo/agent.okf.md`'s `zuno.status` to `active` -
   discharges ADR-0410, and the template flow having produced it
   discharges ADR-0307.
