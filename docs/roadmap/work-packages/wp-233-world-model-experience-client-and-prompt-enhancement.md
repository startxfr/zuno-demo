# WP-233: World-model experience client and prompt enhancement (delivers ADR-0604 D1, D8)

- **State:** Repo work in review
- **ADRs:** ADR-0604
- **Depends on:** WP-228
- **Blocks:** WP-234
- **Estimated files touched:** ~10

> Execute this brief as a standalone task from the repository root.

## Goal

The `world-model` Keycloak client and group exist, and a user of that group can make a C1 chat call through the ai-gateway
with their own token, so the API can enhance and screen prompts.

## ADR references

ADR-0604 D1, D8, §8.1 to §8.3; ADR-0587, ADR-0592, ADR-0593, ADR-0596.

## Repo changes

1. `gitops/charts/keycloak/files/realm-zuno.json`: confidential client `world-model` (redirect to the oauth2-proxy front
   door, `"secret": "${vault.world_model_client_secret}"`), mappers `groups` and `maas-gateway-audience`
   (`zuno-admin-api`). `gitops/charts/keycloak/values.yaml` `experienceClients`; Vault seeding follows the existing loop.
2. Group `zuno-world-model-users`: the realm import only creates, so the WP-235 role creates or patches it live
   (`ansible/roles/open_webui/tasks/keycloak_admin_group.yml` pattern).
3. `gitops/charts/ai-gateway/values.yaml`: `world-model` in `experienceClients` (telemetry label).
4. No agents-release declaration (checked 2026-11-07): `chat_completions` in `components/ai-gateway/app/main.py` routes a
   call that names no known agent by classification and `X-Zuno-Local-Only` alone, and ADR-0596 task aliases
   (`app/model_tasks.py`) only apply to the fail-closed clients. The API sends `X-Zuno-Data-Classification: C1` and
   `X-Zuno-Local-Only: true`. Re-check if `classification_floor.py` (WP-209) changes the treatment of unknown agents.

## Coordination

Another session owns WP-209 (ai-gateway classification floor) and WP-224 moved some namespaces to STRICT mTLS. Ask before
touching `gitops/charts/ai-gateway/values.yaml`; follow the out-of-mesh path that dify and open-webui use today.

## Verification

`check_docs.py` passes; with the user's go, a token for a test user of the group gets a C1 completion from the ai-gateway,
and a user outside the group is refused by the world-model API (WP-234).
