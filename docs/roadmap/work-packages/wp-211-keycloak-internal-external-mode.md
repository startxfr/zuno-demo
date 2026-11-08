# WP-211: Keycloak internal/external mode

- **State:** Repo work in review (2026-11-07: lots A and B built and tested locally; lot A is pushed, lot B is committed locally and waits for the end of the demo freeze; lot C, the live there-and-back, needs a window with the user)
- **ADRs:** [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md), [ADR-0530](../../adr/0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md) (the reconcile mechanics reused)
- **Depends on:** WP-143
- **Related:** [WP-143](wp-143-mariadb-internal-external-pilot.md) (the pilot, whose pattern this follows), [WP-216](wp-216-external-secrets-internal-external-mode.md) and [WP-217](wp-217-cert-manager-internal-external-mode.md) (mode-key mechanics: `mode.yml`, symmetric gating), [ADR-0557](../../adr/0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md), [ADR-0595](../../adr/0595-set-demo-passwords-from-one-shared-value-through-one-variable-per-component.md) (persona passwords)
- **Target:** v0.16
- **Estimated files touched:** ~45 (inventory below): the keycloak role and chart, one new endpoint-resolution task, ~14 consumer charts, ~12 Ansible roles/tasks, `ansible/confidential.example.yml`, the three gateways' code defaults

> Why: ADR-0352 clause 9 lands the internal/external mode contract one component per work package. MariaDB is done (WP-143), and so are the two Tier A-operator components (WP-216, WP-217). Keycloak is the first hard one and the highest value: it exercises CA supply, mandatory admin-credential provisioning, the OAuth integration and the widest seam set. An external Keycloak stops using our PostgreSQL entirely (its chart's database block is dead configuration whatever PostgreSQL's mode is, clause 11). Every UnifAI stack, the gateways, Open WebUI, Dify, kagent, OpenClaw, MaaS, RHTAS and AAP sign in through it.

## Goal

`zuno_keycloak_mode: internal | external` works end to end: internal mode renders and behaves bit for bit as today,
external mode runs every consumer unchanged against a Keycloak the platform does not own, with the realm created and
reconciled by the platform, and the switch is proven live with a simulated external instance and a full there-and-back.

## The contract for Keycloak (ADR-0352)

- **Payload (clause 2), in `ansible/confidential.yml`:** `zuno_keycloak_mode`, `zuno_keycloak_external_url`
  (e.g. `https://sso.corp.example.com`, no realm path), `zuno_keycloak_external_realm` (default `zuno`),
  `zuno_keycloak_external_ca_bundle` (PEM, `""` = publicly or cluster trusted), `zuno_keycloak_external_admin_username`
  and `_password` (required in external mode). Any required key left at `"xxxxxx"` fails fast before any apply.
- **Install (clause 4):** skip both `zuno-keycloak-d0` (RHBK operator) and the built-in instance of `zuno-keycloak-d1`;
  assert the endpoint is reachable and TLS-verifiable against the supplied CA, assert the admin credentials work; seed
  the admin credentials into Vault KV `zuno/keycloak/admin`; build the consumer-side `keycloak-serving-ca` from the
  supplied bundle; then create the realm if missing and reconcile it (clause 7).
- **Check:** endpoint, admin login, realm and each expected client present. Never asserts Application or CR state.
- **Uninstall:** strict no-op against the external instance; only consumer-side artifacts this installer created are
  removed (the CA ConfigMap, the Vault seeds stay).
- **Clause 7:** the platform creates the realm and reconciles its full configuration over the Admin REST API, reusing
  ADR-0530's reconcile-not-import mechanics. The file-vault SPI (`${vault.*}` placeholders resolved by our pod) stays
  internal-only. The realm-export runbook is a documentation annex, not the contract.
- **Clause 11:** no consumer reads `zuno_keycloak_mode`; each receives an endpoint value or a Secret.

Clauses 5 and 6 of the ADR still name agent-runtime, the six agent charts and the aiagent-operator, all retired with
ADR-0561. The consumer list below replaces that list for this WP.

## Consumer inventory (2026-11-07, origin/devel 4ac206e7)

How the domain gets in today: `cluster_base_domain` is resolved by `ansible/tasks/resolve_cluster_base_domain.yml`, and
`ansible/tasks/apply_gitops_app.yml` substitutes the token `apps.mycluster.example.com` in the Application manifests.
Almost every endpoint is therefore `https://keycloak.<domain>/realms/zuno`, with the host prefix and the realm written
into each template.

**Already a Helm value or env var** (default still derived from `keycloak.<domain>`; only the value must be passed):
ai-gateway, mcp-gateway, a2a-gateway (`keycloakIssuer`, `keycloakJwksUrl`); zuno-token-proxy (`tokenUrl`);
trustyai-config (`ragasEval.keycloakTokenUrl`); connectivity-link (`quotaEnforcement.keycloakIssuerUrl`); rhtas
(`fulcio.oidc.issuerUrl`); rhtas-config (`certIdentityIssuer`, set by `ansible/roles/rhtas_config`); mlops
(`acceptanceGate.keycloakUrl`); keycloak (`clientReconcile.serverUrl`); openshift-oauth (`oauth.realm`,
`oauth.openidCaConfigMap`); openclaw and unifai (realm); dify and kagent roles (`*_keycloak_realm` defaults); the
supply-chain scripts and `ragas_eval.py` (env, no default).

**Hard-coded literal, needs a new seam:**

| Consumer | Where | Today |
|---|---|---|
| dify, kagent front doors | `gitops/charts/{dify,kagent}/templates/front-door.yaml` | `--oidc-issuer-url=https://keycloak.<d>/realms/zuno` |
| openclaw | `gitops/charts/openclaw/templates/_helpers.tpl` (host), `front-door.yaml`, `operator.yaml` | host literal |
| open-webui | `gitops/charts/open-webui/values.yaml` (`OPENID_PROVIDER_URL`) | literal in a tpl string |
| unifai | `gitops/charts/unifai/templates/unifaistack.yaml` (JWKS for `DIRECTORY_OIDC_JWKS_URL`, `external.url`) | host literal |
| models / MaaS | `gitops/charts/models/templates/maas.yaml` (`issuerUrl`, twice) | literal |
| openshift-oauth | `gitops/charts/openshift-oauth/templates/oauth.yaml` (issuer host) | host literal |
| EgressFirewalls | `gitops/charts/{namespaces,dify,kagent,open-webui,unifai}/templates/egressfirewall*.yaml`, openclaw `operator.yaml` | `dnsName: keycloak.<d>` |
| aap_config SSO | `ansible/roles/aap_config/tasks/install.yml` (realm key, `AUTHORIZATION_URL`, `ACCESS_TOKEN_URL` on `zuno-service.zuno-auth.svc`) | literals, in-cluster URL |
| SA-group tasks | `ansible/roles/{dify,kagent,openclaw}/tasks/keycloak_sa_groups*.yml` | admin API on `keycloak.<d>` |
| open_webui admin group | `ansible/roles/open_webui/tasks/keycloak_admin_group.yml` | `k8s_exec` into pod `zuno-0`, `kcadm --server http://localhost:8080`: **needs the built-in pod** |
| checks | `ansible/roles/open_webui/tasks/precheck.yml`, `ansible/roles/openclaw/tasks/check_persona.yml` | literal |
| jobs | `ansible/roles/agents/tasks/run_acceptance_gate.yml`, `ansible/roles/day3/tasks/stresstest_job_*.yml`, `ansible/tasks/run_image_signing_job.yml`, `ansible/tasks/verify_image_signatures.yml`, `ansible/playbooks/day3_release.yml` | `KEYCLOAK_URL` / issuer / token URL literals |
| gateways' in-cluster JWKS default | ai-, mcp-, a2a-gateway `values.yaml` | `http://zuno-service.zuno-auth.svc:8080/...` |
| code fallbacks | `components/{ai-gateway,mcp-gateway,a2a-gateway}/app/auth.py` | stale `keycloak-zuno.apps.mycluster.example.com` |
| demo_check | `ansible/playbooks/demo_check.yml` | reads the Keycloak CR in `zuno-auth` |

**Reads that assume the built-in namespace `zuno-auth`:** `ansible/tasks/read_keycloak_automation_credentials.yml`
(automation/admin Secrets), aap_config (`aap-client-secret`), mlops (`demo-personas-password`,
`zuno-evaluations-client-secret` copied into `zuno-mlops`), the acceptance gate and day3 stresstest Jobs, the persona and
failover probes (`demo-personas-password`). In external mode those Secrets do not exist; clause 8 says the values come
from Vault.

**Client secrets.** `ansible/roles/vault/tasks/install.yml` generates them under `zuno/keycloak/<client>` (the six
experience clients of `keycloak.experienceClients`, openshift, aap, zuno-admin-api, zuno-signer, zuno-evaluations,
zuno-stresstest, demo-personas). Consumers already read them from Vault through their own ExternalSecrets (open-webui,
dify, kagent, openclaw, unifai, zuno-token-proxy, openshift-oauth, rhtas-config, trustyai-config). Only Keycloak itself
receives them through the file-vault SPI: `files/realm-zuno.json` holds `"secret": "${vault.<key>}"`.

**CA trust.** `openshift-config/keycloak-serving-ca` is built by `ansible/roles/openshift_oauth/tasks/install.yml` from
the `zuno-auth` Ingress TLS Secret plus the router CA, and read by openshift-oauth, the acceptance gate, the day3
stresstest, both probes and mlops (copied to `zuno-mlops/acceptance-gate-ca`). `rhtas-keycloak-ca` is published by
`ansible/tasks/publish_keycloak_ca_configmap.yml` from the same Ingress Secret. Both derivations hard-fail without the
built-in Ingress.

## Design

**One resolution, one value flow.** A new `ansible/tasks/resolve_keycloak_endpoint.yml` (the WP-143
`resolve_mariadb_endpoint.yml` pattern) sets, in both modes, `zuno_keycloak_base_url`, `zuno_keycloak_realm`,
`zuno_keycloak_issuer_url` (`<base>/realms/<realm>`), `zuno_keycloak_jwks_url`, `zuno_keycloak_token_url`,
`zuno_keycloak_host` (for the EgressFirewalls) and `zuno_keycloak_ca_pem`. Internal values reproduce today's strings
exactly, so internal mode renders bit-identical output. Every consumer role passes the values it needs through
`gitops_app_extra_helm_values`; every chart grows a value whose default is today's literal. No chart and no role other
than `keycloak` reads the mode key.

**The gateways keep the in-cluster JWKS in internal mode.** `http://zuno-service.zuno-auth.svc:8080` stays the
internal default (it avoids the router); external mode passes the external JWKS URL. The issuer is always the public
one.

**External realm provisioning reuses the ADR-0530 Job.** `job-client-reconcile.yaml` already runs `kcadm.sh` against
`KC_SERVER` with admin credentials. In external mode the keycloak chart renders no Keycloak CR, no Ingress, no
`KeycloakRealmImport` and no PostgreSQL ExternalSecret (chart guard `keycloak.builtIn: false`), and the Job:
1. points `KC_SERVER` at `zuno_keycloak_external_url`, trusts the supplied CA (mounted from a ConfigMap), and reads the
   admin credentials from the ExternalSecret of `zuno/keycloak/admin`;
2. creates the realm from `files/realm-zuno.json` when it is missing (the part the import does internally);
3. **materializes the client secrets**: replaces each `${vault.<key>}` with the value of the mounted Secret before the
   merge, because no file-vault SPI exists on a Keycloak we do not run. The secrets therefore live in Keycloak's own
   store in external mode, set by the platform, still sourced from Vault;
4. reconciles clients, realm settings, the agent groups, and the items D2 decides.

`job-eval-personas.yaml` already takes `KC_SERVER`; it follows the same switch.

**The one task that needs the pod.** `open_webui/tasks/keycloak_admin_group.yml` is rewritten on the Admin REST API
(the dify/kagent `keycloak_sa_groups.yml` pattern), in both modes, so nothing reads pod `zuno-0` any more.

**Reads from `zuno-auth` move to Vault.** `read_keycloak_automation_credentials.yml` and the job/probe tasks read the
same values from Vault KV (`zuno/keycloak/automation`, `zuno/keycloak/demo-personas`, `zuno/keycloak/zuno-evaluations`,
`zuno/keycloak/aap-client`), in both modes; the copies into `zuno-mlops` come from Vault too.

**CA supplied, never derived (clause 6).** In external mode `keycloak-serving-ca` and `rhtas-keycloak-ca` are built
from `zuno_keycloak_external_ca_bundle` (or the system bundle when `""`). The derivation from the `zuno-auth` Ingress
stays the internal path only.

**Egress.** EgressFirewalls now exist (WP-224), so clause 6's mandate applies: every `dnsName: keycloak.<d>` becomes
`zuno_keycloak_host`. An external host outside the apps domain must be reachable from zuno-ai-run, zuno-unifai,
zuno-openwebui, zuno-dify, zuno-kagent and the claw namespaces.

**Ownership.** The `OAuth/cluster` object stays ours (openshift-oauth chart); only its issuer and CA change. Nothing is
selfHeal-managed on the external Keycloak itself: the realm is reconciled by the Job on each sync, not by ArgoCD.

## Lots

| Lot | Content | Live risk | Can ship alone |
|---|---|---|---|
| **A: seams, internal unchanged** | `resolve_keycloak_endpoint.yml`; every literal above becomes a value with today's default; code fallbacks fixed | none: proven by a rendered-manifest diff (`helm template` of every touched chart, before and after, with the live values) and `make d1 check` | yes |
| **B: external mode** | mode key and payload, `mode.yml`-style resolution in `resolve_keycloak_endpoint.yml`, the external install, check and uninstall of the keycloak role, a chart guard `keycloak.builtIn`, the external reconcile Job, supplied-CA publication, the Keycloak seams merged into every consumer (done 2026-11-07, see below) | none in internal mode (rendering identical), but the Open WebUI admin group now runs on the Admin REST API in both modes | yes, after the demo |
| **C: live there-and-back** | rehearsal below | SSO outage for the whole platform during the flips | needs a window and the user's go |

## Live rehearsal (lot C, demo333, after the 2026-11-09 demo)

Data reality: the realm is not disposable. UnifAI, Open WebUI, Dify and the gateways key ownership, sessions and audit
on the user's `sub`; a re-created user gets a new id. The migration must keep the ids, which the Keycloak export does.

1. Simulated external Keycloak in a dedicated namespace not managed by any Application (`zuno-auth-ext`): the RHBK
   image from one-shot manifests kept out of the repo charts, its own database, its own Route and certificate, its own
   admin account. It simulates a service the platform does not own.
2. Export from the built-in instance with users and ids (`kc.sh export --realm zuno --users realm_file`, run as a
   one-shot Job against the built-in database), import into the simulated one. Compare user, group, client counts and a
   sample of ids.
3. ✋ Flip: `zuno_keycloak_mode: external`, payload pointing at the simulated instance, then `make d0 install keycloak`
   (asserts, seeds, CA, realm reconcile) and the consumer roles (openshift-oauth, the gateways, unifai, open-webui,
   dify, kagent, openclaw, models, rhtas, rhtas-config, connectivity-link, trustyai-config, mlops, aap-config, namespaces).
4. Proofs: OpenShift console login through the IdP; one persona login in each experience; a gateway call with a fresh
   token; `make d2 check agents` (acceptance gate through UnifAI); `make d2 check supply-chain` (Fulcio issuer);
   `make d1 check` green.
5. ✋ Back: export the simulated realm with users, flip to `internal`, `make d0 install keycloak` and the same consumer
   roles, compare counts and ids, the same proofs, then delete `zuno-auth-ext`.

Expected outage: each flip re-points every login; plan about 2 h with the user available for the console and
experience logins.

## Decisions (settled with the user, 2026-11-07)

| | Decision |
|---|---|
| D1 | Full flip there-and-back on demo333 in a window after the 2026-11-09 demo, user ids kept (export with users), private CA for the simulated instance. |
| D2 | External mode creates, when missing: the 14 clients, the 24 groups (and subgroups), the 5 service-account users; merges only the realm settings of `realm-settings.json`. Demo personas only with `zuno_keycloak_external_seed_personas: true` (off by default). The credential is a user scoped to the realm `zuno` (the platform creates the realm only if the credential may). |
| D3 | The Google identity provider is never provisioned in external mode (federation is the external owner's). |
| D4 | The Keycloak database and role of the postgresql chart are kept untouched (they are also the back path of the migration, and PostgreSQL must not read the Keycloak mode, clause 11). |
| D5 | AAP's SSO uses the external public URL for authorization and token. Only the realm `zuno` is supported. |
| Other | The platform writes the client secrets into the external Keycloak from Vault (Vault stays the single source). The migration is a documented hand-run runbook, no scripted helper. |

## What NOT to touch

- The Keycloak realm content (`files/realm-zuno.json`) beyond the placeholders the Job materializes.
- ADR-0530's boundary: what is create-only stays create-only in internal mode.
- Vault paths and the client-secret generation in the vault role.
- The UnifAI fork: it receives the URLs as values (`unifaistack.yaml`), no fork change.

## Tests / verification checklist

- Lot A: `helm template` diff of every touched chart, before and after, with the live Application values: empty.
  `ansible-playbook --syntax-check` of day0/day1/day2. `make d1 check` green. `check_docs.py` green.
- Lot B: a unit-style render of the keycloak chart with `builtIn: false` (no CR, Ingress, import, PostgreSQL secret;
  the Job carries the external URL and CA); the reconcile script run against a local Keycloak container with the
  realm file, before and after, idempotent on a second run; the negative paths (sentinel payload, unreachable URL,
  bad CA, wrong admin password) fail fast with clear messages.
- Lot C: the rehearsal proofs above.

## Status updates (then re-run check_docs.py)

- After lot A: WP-211 `In progress`; nothing changes in ADR-0352.
- After lot C: WP-211 `Done`; ADR-0352 keeps `Partially implemented` (Vault, PostgreSQL, Redis, AAP, ArgoCD remain)
  with a dated clause-9 note; ADR-0352 clauses 5 and 6 amended to replace the retired consumers with the list above.

## Out of scope

- Federation details beyond D3, any change to the external Keycloak's own configuration outside the `zuno` realm.
- The clause-10 Day-1 vital gate (not built for any component yet).
- Vault external mode (WP-212), which this WP's Vault reads do not depend on.

## Acceptance

- Internal mode renders and behaves exactly as before (empty rendered diff, `make d1 check` green).
- External mode runs every consumer above against the external endpoint, with users, ids and group memberships intact
  both ways, and `make d1 check`, `make d2 check agents` and `make d2 check supply-chain` green in both modes.

## Lot A delivered (2026-11-07)

- `ansible/tasks/resolve_keycloak_endpoint.yml` sets `zuno_keycloak_url`, `_realm`, `_issuer_url`, `_token_url`,
  `_auth_url` and `_internal_url` (built-in values only). It is an include, not `group_vars`: the AAP Controller
  inventory has no `group_vars` (see `gitops/charts/aap-config/templates/ansibleinventory.yaml`), so a group variable
  would be undefined in AAP-launched jobs. It is included right before each consumer task, after
  `cluster_base_domain` is resolved: aap_config (SSO authenticator), agents (acceptance gate), day3 (stresstest create
  and run), dify, kagent and openclaw (SA groups), open_webui (precheck probe), rhtas_config (ClusterImagePolicy
  issuer), `run_image_signing_job.yml`, `verify_image_signatures.yml`, `day3_release.yml`. No Keycloak literal is left
  in `ansible/` outside that file.
- Chart seams, empty by default, with today's literal as the fallback: dify, kagent, open-webui
  `global.zuno.keycloakIssuerUrl` and `keycloakHost` (global because the Open WebUI env is evaluated by `tpl` inside
  the subchart); openclaw `keycloak.host`; unifai `stack.identity.keycloakUrl` and `keycloakHost`; models
  `keycloakIssuerUrl`; openshift-oauth `oauth.keycloakUrl`; namespaces `keycloakHost`.
- The three gateways' code fallback is `https://keycloak.apps.mycluster.example.com/realms/zuno` (was the stale
  `keycloak-zuno.` host; the deployments always set `KEYCLOAK_ISSUER`).

Proof: `helm template` of the 12 Applications of the touched charts with their live values, before and after:
identical byte for byte (dify, kagent and open-webui rendered without their subcharts); models also identical with
the `ModelsAsService` API enabled; the Open WebUI `OPENID_PROVIDER_URL` evaluated through `tpl` is unchanged.
Positive tests: setting each new value changes the rendered issuer or host. An assertion playbook shows that every
resolved string equals the literal it replaced. `--syntax-check` of the day0 to day3 playbooks is green. The
ai-gateway and mcp-gateway suites show the same failures as origin/devel, none new. Live and read-only:
`day2_check open-webui` (its probe runs through the new include) reports installed, and `day2_check supply-chain`
reports "PASS - all 12 image(s) verified".

## Lot B delivered (2026-11-07, local commit, not pushed: demo freeze)

- **Mode and payload**: `zuno_keycloak_mode` and the `zuno_keycloak_external_*` keys (`ansible/confidential.example.yml`).
  `resolve_keycloak_endpoint.yml` loads `confidential.yml`, fails fast on an unknown mode, a sentinel, a non-https URL
  or a realm other than `zuno`, and sets the same facts in both modes (plus `zuno_keycloak_external_mode`,
  `_admin_realm`, `_admin_token_url`, `_jwks_url`, `_host`, `_ca_pem`).
- **Role** `ansible/roles/keycloak`: `install_external.yml` (assert the endpoint over TLS with the supplied CA and the
  admin sign-in, seed `zuno/keycloak/admin`, refresh the ExternalSecret, publish `zuno-auth/keycloak-external-ca`),
  `assert_external.yml` (shared with the precheck, record only there), install, precheck and uninstall branches. In
  external mode no operator, no Keycloak CR, no import is deployed or removed.
- **Chart** `gitops/charts/keycloak`: `keycloak.builtIn` guards the Keycloak CR, Ingress, realm import and database
  secret; `keycloakExternal.*` carries the external values. The file-vault projected sources moved to a shared helper
  (`templates/_helpers.tpl`). New `job-client-reconcile-external.yaml`; `job-eval-personas.yaml` follows the switch;
  `configmap-clients.yaml` adds `realm-groups.txt` and the persona files in external mode only.
- **Consumers**: `ansible/tasks/keycloak_seam_values.yml`, included by `apply_gitops_app.yml` only in external mode,
  merges the Keycloak seams into the Application values of the 16 consumer components (the gateways, the token
  proxies, dify, kagent, open-webui, openclaw, unifai, models, openshift-oauth, namespaces, connectivity-link, rhtas,
  trustyai-config, mlops). The credential reader, the dify/kagent/openclaw service-account tasks (admin token URL),
  `openshift_oauth` (serving CA from the supplied bundle, appended to the cluster-wide trust) and
  `publish_keycloak_ca_configmap.yml` (RHTAS) have an external branch. The Open WebUI admin group is on the Admin REST API.
- The `zuno-auth` Secrets (client secrets, automation and admin credentials, personas password) stay produced by
  the ExternalSecrets in both modes, so the roles that read them (aap_config, mlops, the gate, the probes) needed no
  move to Vault.

Proof, all local or read-only live:

- Internal rendering: `helm template` of the keycloak chart with the live d0 and d1 values, before and after, is
  byte-identical (refactor, guards, new files, Job edits); the 12 consumer Applications of lot A are still identical
  on the new base; the lot A string assertions still pass.
- The external reconcile Job script, extracted from the rendered chart and run in the upstream Keycloak 26.0 image
  against a real server: realm created from a master-realm admin; 14 clients with their real secrets (no
  placeholder left, a client-credentials grant with the materialized secret works); 37 groups (24 top level) with
  subgroups; 27 personas with their group memberships and a working password containing `&`; a second run creates
  nothing; the same with a credential scoped to the realm on an EMPTY realm created by the owner; a rejected password
  and an unknown sign-in realm fail at once with the cause; a missing secret skips that client, still processes the
  others, and fails the Job; over HTTPS with a private CA, a 2-certificate bundle builds the truststore and the whole
  run succeeds, and without the bundle it fails with the PKIX error. The adapted eval-personas script ran too (10
  created, 56 memberships).
- Ansible: the resolution in internal and external mode and every invalid payload; the 16-component seam merge; the
  Open WebUI admin group task on the REST API (create, add, idempotent); the keycloak precheck live in internal mode
  (installed) and in external mode pointed at the built-in with a fake credential (NOT installed, no crash); the
  openshift-oauth precheck live (see the finding below); `--syntax-check` of the day0 to day3 playbooks.

Findings:

- `keycloak-serving-ca` is reported STALE by `make d1 check openshift-oauth` on demo333, on origin/devel too (not caused
  by this work): the snapshot differs from the chain Keycloak serves. Fix: `make d1 reconcile openshift-oauth`.
- `kcadm config credentials --truststore` does not keep the truststore for the next commands; `kcadm config truststore`
  does (the Job uses it). `kcadm get groups/<id>/children` returns 10 by default: pass `-q max=...`.
- A partial import (`/partialImport`) of groups with subgroups answers 500 (Keycloak NPE): groups come from the Job, not from an import.
- Jinja: `helm['values']` on a manifest without a `values` key returns the dict METHOD, not an empty value; use `.get`.

Not proven yet (lot C): the Job inside the cluster (RHBK 26.6 image, read-only root, `keytool` present), the gateways
fetching a JWKS over TLS from a private CA (their trust, through the cluster-wide bundle, is untested), AAP's trust of
a private CA, the OAuth operator and Fulcio against the external issuer, `kc.sh export` on the built-in database.

## Migration runbook (lot C, by hand, in the window)

Why this order: a partial import keeps the user ids and skips users that already exist, so the users must be imported
BEFORE anything creates them with new ids (the demo personas of the Job), and only AFTER the groups exist (the import
attaches the group paths it is given, but fails on groups with subgroups).

Internal to external:

1. Announce the window to the sessions; Vault, ESO, cert-manager and the mesh healthy; `make d1 check` green.
2. Export the realm with users from the built-in Keycloak: a one-shot Job (kept out of the repo) with the RHBK image and
   the database settings of `oc -n zuno-auth get keycloak zuno -o yaml` (`spec.db`), running
   `kc.sh export --realm zuno --users realm_file --file /tmp/zuno-realm.json`; copy the file out.
3. The simulated external Keycloak (`zuno-auth-ext`): RHBK from one-shot manifests with its own database, a Route and a
   certificate from the Vault PKI (private CA). Create the empty realm `zuno` and a user `zuno-platform` (first name,
   last name, email) with `realm-management/realm-admin`.
4. In `ansible/confidential.yml`: `zuno_keycloak_mode: external`, the URL, the CA bundle, the credential,
   `zuno_keycloak_external_seed_personas: false`. Run `make d0 install keycloak`: the Job creates clients, groups,
   service accounts.
5. Import the users with their ids: the `users` of the export (credentials included) through
   `POST /admin/realms/zuno/partialImport` with `ifResourceExists: SKIP`. Compare counts and a sample of ids.
6. Re-run the consumer roles in this order: `openshift-oauth`, the three gateways, `unifai`, `open-webui`, `dify`,
   `kagent`, `openclaw`, `models`, `connectivity-link`, `rhtas`, `rhtas-config`, `trustyai-config`, `mlops`,
   `aap-config`, `namespaces`. Restart the pods that read the issuer at start.
7. Proofs: console login through the IdP, one persona per experience, a fresh token on each gateway,
   `make d2 check agents`, `make d2 check supply-chain`, `make d1 check`.

External to internal: export the simulated realm the same way, set `zuno_keycloak_mode: internal`, run
`make d0 install keycloak` (the built-in instance and its database are still there, D4), import the users with their
ids into it (`SKIP`), re-run the consumer roles, same proofs, then delete `zuno-auth-ext`.

The data stays on the side it was last written on until the flip back: users created while external are lost unless
they are exported.

