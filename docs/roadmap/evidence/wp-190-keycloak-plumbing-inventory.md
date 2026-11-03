# WP-190 phase 4: inventory of the Keycloak client plumbing common to the three experiences

- **Date:** 2026-11-03, read-only, `origin/devel`
- **Question:** what is repeated for each confidential Keycloak client of an experience (UnifAI, Open WebUI, OpenClaw per
  persona), and what would it take to declare each client once?

## What exists, per client

| Piece | Where | UnifAI | Open WebUI | OpenClaw (per persona) |
|---|---|---|---|---|
| Client definition (redirects, mappers, secret `${vault.<name>_client_secret}`) | `gitops/charts/keycloak/files/realm-zuno.json`, re-applied by the client-reconcile Job | hand-written | hand-written | hand-written, one block per persona |
| Keycloak-side ExternalSecret `<name>-client-secret` (wave -20, key `keycloak/<name>`) | `gitops/charts/keycloak/templates/externalsecret-*.yaml` | own file | own file | one file with a `range list "consultant-02" "sale-01"` |
| KC_VAULT secret volume item (file `zuno_<name with _ doubled>__client__secret`) | `gitops/charts/keycloak/templates/keycloak.yaml` L98-135 | hand-written | hand-written | hand-written, one item per persona |
| Vault seed of `keycloak/<name>` (generated 32-char secret, create-if-missing) | `ansible/roles/vault/tasks/install.yml` L470-505 | own task | own task (also in `ansible/roles/open_webui/tasks/seed_vault.yml`) | one looped task over `["consultant-02", "sale-01"]` |
| Experience-side ExternalSecret reading the same Vault path | the experience's chart | inside the UnifaiStack (operator) | `gitops/charts/open-webui/templates/externalsecrets.yaml` | `gitops/charts/openclaw/templates/externalsecrets.yaml`, `range` over `personas` |
| Live group or claim steps outside the realm file | role tasks | none | `keycloak_admin_group.yml` (group `openwebui_admin`) | `keycloak_sa_groups.yml`, `keycloak_sa_groups_persona.yml` |

## Findings

1. **Adding or renaming a persona touches five places by hand:** the realm client block (and its `persona` mapper), the
   `range` list of the Keycloak ExternalSecret, the KC_VAULT item of `keycloak.yaml`, the Vault seed loop and the OpenClaw
   chart's `personas` list. A missing one fails quietly: an absent KC_VAULT item leaves `${vault.<name>_client_secret}`
   unresolved at client creation, an absent ExternalSecret leaves the Secret missing (the volume item is `optional: true`).
2. **The KC_VAULT file-name rule is implicit** (`_` doubled in the client name, then `__client__secret`) and was learned from
   a failure on Open WebUI (`zuno_open__webui__client__secret`). It is written nowhere but in comments.
3. **Open WebUI seeds `keycloak/open-webui` twice** (vault role and its own role, "whichever runs first wins"). Harmless
   because the seed is create-only, but it is two sources of truth for one path.
4. **The experience-side shapes differ for no reason:** the secret store comes from `.Values.externalSecrets.secretStore` in
   Open WebUI and is fixed in the Keycloak chart; OpenClaw ranges over personas; UnifAI is inside an operator CR.
5. **Checks differ in shape:** Open WebUI probes the chain from its pod (`precheck.yml`), OpenClaw has `check.yml` and
   `check_persona.yml`, UnifAI has `check.yml` plus image verification.

## Smallest safe unification (proposal)

- **4a, declare the experience clients once** in `gitops/charts/keycloak/values.yaml` as a list (`name`, `vaultKey`, and a
  computed volume file name) and render from it: the per-client ExternalSecrets, and the KC_VAULT items of `keycloak.yaml`.
  The Vault seed loop reads the same list through the cluster variables file. The realm client blocks stay as they are: they
  carry per-client redirects and mappers that differ.
- **Safety:** render the Keycloak chart before and after in a temporary copy without the remote `operator` dependency and
  require the rendered ExternalSecrets and the KC_VAULT items to be identical (no change on the cluster, only a refactor).
- **4b, one precheck skeleton** (state detection, running pod, in-pod probes, Route, running-image digest) shared by Open
  WebUI and OpenClaw; UnifAI keeps its operator-specific checks.
- **Not proposed:** one chart for the three experiences (their lifecycles differ: operator, per-persona namespaces, plain
  Deployment), or moving the realm client blocks into templates (the realm import is create-only and the reconcile Job reads
  the file).

## Risk

A change under `gitops/charts/keycloak` is synced from `devel` by `zuno-keycloak-d1`; a refactor that renders identically
produces no change on the cluster, but a mistake in an ExternalSecret reaches Keycloak's secret volume. The first push of an
experience's client (WP-181) froze the Keycloak sync once because the Vault path was not yet seeded.
