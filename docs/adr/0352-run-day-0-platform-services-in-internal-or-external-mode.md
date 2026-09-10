# ADR-0352: Run day-0 platform services in internal or external mode

- **Status:** Proposed
- **Target:** v0.9
- **Date:** 2026-08-17
- **Amended:** 2026-09-10 (re-derived against the post-ADR-0421 component
  lists; AAP added as a vital Tier-A component; Day-1 externalization
  narrowed to redis and mariadb; external Vault widened to full setup;
  Keycloak/AAP external admin credentials made mandatory; remote-ArgoCD
  mechanism delegated to ADR-0557; vital-gate and dependency-abstraction
  clauses added. Never implemented, so corrected in place — see
  `CHANGELOG.md`.)
- **Decision owners:** Zuno Demo architecture team

## Context

Real target environments increasingly arrive with a Keycloak, a Vault, a
Prometheus or a managed PostgreSQL the project is required to use; today
the platform can only deploy its own. The repo's current shape makes that
assumption structural, not incidental:

- **Every day-0 component is the same tuple** (ADR-0056): an Ansible role
  (`tasks/{install,precheck,uninstall}.yml`), an ArgoCD Application pair
  `gitops/apps/<c>/application-d{0,1}.yaml`, and a Helm chart
  `gitops/charts/<c>` whose values all default to `false`. Applications
  are Ansible-applied, never git-synced (ADR-0311); ordering is the
  `day0_components` list order in `ansible/playbooks/day0_install.yml`
  (13 entries since ADR-0421 moved `postgresql`, `keycloak`, `aap` and
  `aap_config` into Day 0; `day1_components` carries 23 more) — the
  Day-0 list has drifted from the Makefile's `DAY0_COMPONENTS`
  (12 entries; `image_mirrors` is missing there).
- **`ansible/confidential.yml` is the sole per-environment entry point**:
  gitignored, flat `zuno_<vendor>_<field>` namespace, sentinel `"xxxxxx"`
  = not configured, template `ansible/confidential.example.yml`. Only
  Ansible reads it: the vault role hard-requires it and seeds every value
  into Vault KV `zuno/<component>/<item>`; keycloak, smtp, postgresql and
  mariadb soft-read it (stat + include_vars). Beyond this file, an
  internal install assumes only a cluster-admin kubeconfig and the apps
  domain discovered from `Ingress.config.openshift.io/cluster`.
- **Consumer seams hardcode in-cluster endpoints.** Three cluster-scoped
  objects bake `http://{{ .Values.vaultServiceName }}.zuno-vault.svc:8200`
  into their templates (the `vault-backend` ClusterSecretStore, the
  `vault-issuer` and `vault-issuer-istio` ClusterIssuers) — only the
  Service *name* is a value; scheme, namespace, port, KV mount, PKI
  paths, auth mount and role names are fixed, and no template emits a
  `caBundle`. Keycloak consumers carry a split-brain default: the issuer
  falls back to the Route (`https://keycloak.<domain>/realms/zuno`) while
  JWKS defaults to the in-cluster Service
  (`http://zuno-service.zuno-auth.svc:8080/...`) across nine charts —
  and the aiagent-operator chart exposes no `KEYCLOAK_JWKS_URL` value at
  all (Go code default only). Kiali hardcodes
  `http://mesh-monitoring-prometheus.<ns>.svc:9090`; ~8 charts carry
  postgres host values, 6 carry redis addresses (plus 2 code defaults),
  and the four Python services default `OTEL_EXPORTER_OTLP_ENDPOINT` in
  code with no chart value anywhere.
- **`make d0 check` semantics are internal-only**: prechecks assert the
  two Applications Synced+Healthy plus CR readiness (keycloak requires
  `Keycloak/zuno` Ready and `KeycloakRealmImport/zuno-realm` Done) —
  assertions that are meaningless for a service this repo does not
  deploy.
- **CA trust is derived, not supplied**:
  `ansible/roles/openshift_oauth/tasks/install.yml` builds the
  `keycloak-serving-ca` ConfigMap by reading the built-in Keycloak
  Ingress and its TLS Secret, and hard-fails if that Ingress is absent.
- **NetworkPolicies are ingress-only** (`policyTypes: [Ingress]`);
  egress to off-cluster endpoints is unrestricted today.
- **The pattern already exists in-repo, once.** MariaDB's only two
  consumers speak it natively — `gitops/charts/rag-ingestion/values.yaml`:

  ```yaml
  metadataDatabase:
    mode: externalMySQL      # embeddedMariaDB | externalMySQL
    externalMySQL:
      host: "mariadb.zuno-data.svc.cluster.local"
      port: 3306
      database: mlpipeline
      username: mlpipeline
      secretName: rag-pipeline-db
      externalSecret:
        remoteKey: "rag/pipeline-db"
        passwordProperty: password
  ```

  Other partial precedents: `zuno_smtp_enabled` gates the smtp installs
  (but not its precheck — an asymmetry); postgresql's S3 backup
  auto-enables when all five confidential values are non-sentinel;
  cert-manager's `acme.enabled` + staged `acme.consumers.*` flip is the
  repo's mature safe-cutover pattern; ADR-0211 reuses a pre-existing
  Route53 zone rather than provisioning one; ADR-0020 already chooses
  local-vs-external per LLM provider.

## Decision

1. **Every day-0 component runs in exactly one of two modes, declared in
   `ansible/confidential.yml`: `internal` (default when the key is
   absent — today's behavior, bit-for-bit) or `external` (a pre-existing
   instance is used; the built-in is not deployed).** The key is
   `zuno_<component>_mode`, an enum rather than a boolean because
   `external` carries a parameter payload — mirroring the in-repo
   `metadataDatabase.mode: embeddedMariaDB | externalMySQL` precedent.
   "External" covers both off-cluster endpoints and in-cluster instances
   managed by another team: the contract is identical (an endpoint we do
   not own). This is a different sense of "external" than ADR-0116/0117:
   those decide how agents reach third-party SaaS tool backends; this
   ADR decides who deploys the platform's own infrastructure services.
   `zuno_smtp_enabled` is grandfathered: smtp has no built-in to deploy,
   so it keeps its boolean as the degenerate always-external case and
   gains no `zuno_smtp_mode` key.

2. **All external-mode input lives in `confidential.yml`; internal mode
   requires no new key at all.** Universal keys per Tier-A component
   (clause 3): `zuno_<c>_mode`, an endpoint — `_external_url` as one
   full URL including scheme and port for HTTP services (so the
   http→https widening of the Vault seams happens in exactly one place),
   or `_external_host`/`_external_port` for TCP services, matching the
   `zuno_smtp_host`/`zuno_smtp_port` precedent — and
   `zuno_<c>_external_ca_bundle` (PEM string; `""` = the endpoint is
   trusted by the system/cluster CA set). Tier A-operator components
   (`external_secrets`, `cert_manager` — clause 3) carry only the mode
   key: their external mode supplies no endpoint, and clause 7 defines
   what it asserts instead. There is deliberately **no**
   `insecure`/skip-verify key anywhere in the schema. Validation:
   `mode: external` with any required key left at the `"xxxxxx"`
   sentinel fails fast in the role, before any apply; `mode: internal`
   ignores every `_external_*` key. Non-secret values (URLs, CA bundles,
   mount names) flow to charts as Helm values; secret values flow only
   confidential.yml → Vault KV → ExternalSecrets (clause 8). The schema
   destined for `confidential.example.yml` at implementation time:

   ```yaml
   # --- Component modes (ADR-0352) ------------------------------------
   # Each Tier-A component: internal (default, this repo deploys it) |
   # external (a pre-existing instance is used; the built-in is not
   # deployed). Absent keys mean internal.

   # ArgoCD - the number-one infrastructure piece: every other component
   # is delivered through it. external = an instance this repo does not
   # deploy carries the zuno AppProject and our Applications, either a
   # pre-existing in-cluster instance or a REMOTE one that declares this
   # cluster (mechanism study: ADR-0557).
   zuno_argocd_mode: internal
   zuno_argocd_external_url: "xxxxxx"          # API URL of the external instance
   zuno_argocd_external_namespace: "xxxxxx"    # namespace, when the instance is in-cluster
   zuno_argocd_external_token: "xxxxxx"        # account allowed to manage the zuno AppProject
   zuno_argocd_external_ca_bundle: ""

   # Vault - secrets plus every engine the internal install provisions.
   # The token must carry enough policy for the platform to perform the
   # FULL setup itself - KV v2, PKI, transit, kubernetes auth, policies
   # and roles - idempotently (ADR-0345 semantics; see clause 7).
   zuno_vault_mode: internal
   zuno_vault_external_url: "xxxxxx"           # e.g. https://vault.corp.example.com:8200
   zuno_vault_external_ca_bundle: ""
   zuno_vault_external_kv_mount: "zuno"        # KV v2 mount granted to the platform
   zuno_vault_external_auth_mount: "kubernetes" # k8s auth mount for THIS cluster
   zuno_vault_external_token: "xxxxxx"         # setup token: mount/policy/role provisioning

   # External Secrets Operator (Tier A-operator: external = the operator
   # is installed outside this installer; the ClusterSecretStore and all
   # operand config stay ours in BOTH modes - see clause 7)
   zuno_external_secrets_mode: internal

   # cert-manager (Tier A-operator: same contract - the operator may be
   # unmanaged, ClusterIssuers/Certificates stay ours in both modes)
   zuno_cert_manager_mode: internal

   # Keycloak - identity provider. Admin credentials are REQUIRED in
   # external mode: the platform creates and reconciles the realm and
   # its full configuration (clause 7).
   zuno_keycloak_mode: internal
   zuno_keycloak_external_url: "xxxxxx"        # e.g. https://sso.corp.example.com
   zuno_keycloak_external_realm: "zuno"        # realm the platform creates/reconciles
   zuno_keycloak_external_ca_bundle: ""        # PEM; "" = publicly/cluster trusted
   zuno_keycloak_external_admin_username: "xxxxxx"  # REQUIRED in external mode
   zuno_keycloak_external_admin_password: "xxxxxx"

   # PostgreSQL - one pre-created role per platform database. Databases:
   # the PGO spec.users list (zuno, keycloak, rag-tech, maas,
   # agent-checkpoints, ogx, rag-sales, rag-sxa-legacy, rag-adv,
   # rag-project) plus the five AAP databases (gateway, controller, hub,
   # eda, metrics) that internal AAP provisions on this instance.
   zuno_postgresql_mode: internal
   zuno_postgresql_external_host: "xxxxxx"
   zuno_postgresql_external_port: "5432"
   zuno_postgresql_external_sslmode: "verify-full"
   zuno_postgresql_external_ca_bundle: ""
   zuno_postgresql_external_db_zuno_username: "xxxxxx"
   zuno_postgresql_external_db_zuno_password: "xxxxxx"
   zuno_postgresql_external_db_keycloak_username: "xxxxxx"
   zuno_postgresql_external_db_keycloak_password: "xxxxxx"
   # ... one _username/_password pair per remaining database ...

   # AAP - Ansible Automation Platform. Admin credentials are REQUIRED
   # in external mode: the platform provisions org, project, inventory,
   # credentials, job and workflow templates over REST (clause 7).
   # aap_config follows this mode key and has none of its own.
   zuno_aap_mode: internal
   zuno_aap_external_url: "xxxxxx"             # Gateway URL, e.g. https://aap.corp.example.com
   zuno_aap_external_ca_bundle: ""
   zuno_aap_external_admin_username: "xxxxxx"  # REQUIRED in external mode
   zuno_aap_external_admin_password: "xxxxxx"

   # --- Day-1 components: internal-only, except the two below ---------

   # Redis - external = an endpoint to consume; how it is deployed is
   # the provider's concern. Consumer inventory drives sizing: clause 7.
   zuno_redis_mode: internal
   zuno_redis_external_host: "xxxxxx"
   zuno_redis_external_port: "6379"
   zuno_redis_external_password: "xxxxxx"      # sentinel = no AUTH
   zuno_redis_external_ca_bundle: ""           # "" + port 6379 = plaintext

   # MariaDB - one credential pair per database. Databases today:
   # mlpipeline (rag-ingestion), mlops (mlops DSPA), trillian (RHTAS).
   # The database inventory drives consumer configuration: clause 7.
   zuno_mariadb_mode: internal
   zuno_mariadb_external_host: "xxxxxx"
   zuno_mariadb_external_port: "3306"
   zuno_mariadb_external_ca_bundle: ""
   zuno_mariadb_external_db_mlpipeline_username: "xxxxxx"
   zuno_mariadb_external_db_mlpipeline_password: "xxxxxx"
   zuno_mariadb_external_db_mlops_username: "xxxxxx"
   zuno_mariadb_external_db_mlops_password: "xxxxxx"
   zuno_mariadb_external_db_trillian_username: "xxxxxx"
   zuno_mariadb_external_db_trillian_password: "xxxxxx"
   ```

   `zuno_keycloak_external_realm: "zuno"` is a real default, a stated
   exception to the sentinel rule (the realm name is a convention, not a
   credential). **Internal-mode sufficiency**: in internal mode,
   `confidential.yml` plus a cluster-admin kubeconfig is sufficient —
   asserted as a property this ADR's contract must preserve — with five
   named gaps to close during implementation: (a) smtp's precheck is not
   gated by `zuno_smtp_enabled` while its install is; (b) the OTLP
   endpoint lives only as a Python code default, not a chart value;
   (c) the aiagent-operator chart exposes no `KEYCLOAK_JWKS_URL` value;
   (d) the keycloak issuer-vs-JWKS split-brain default; (e) the
   Makefile/playbook component-list drift.

3. **All 36 playbook components (13 Day 0 + 23 Day 1, post-ADR-0421)
   are classified into three tiers.** Mode keys attach to the component
   that deploys the service in internal mode. Day 1 is internal-only
   with exactly two exceptions, redis and mariadb (plus smtp, which has
   no built-in): the platform's own workload plane stays ours to run,
   only shared middleware may be handed over.

   | Tier | Meaning | Components |
   |---|---|---|
   | A-endpoint, Day 0 — **vital** | A running instance can be supplied; full clause-2 schema, clause-4 lifecycle, clause-7 prerequisites; gates Day 1 per clause 10 | argocd, vault, postgresql, keycloak, aap (`aap_config` follows `aap`'s mode key) |
   | A-operator, Day 0 — **vital** | "External" means the operator is installed outside this installer (unmanaged); our `-d0` Application is skipped, our `-d1` operand config (ClusterSecretStore, ClusterIssuers) is applied by us via ArgoCD in **both** modes | external_secrets, cert_manager |
   | A-endpoint, Day 1 | Same endpoint contract as Day-0 A-endpoint; the only Day-1 components that may be external | redis, mariadb, smtp (grandfathered, always-external) |
   | C — always internal | Cluster-topology glue, the observability/mesh/GPU stack and the workload plane | Day 0: admin_context, namespaces, image_mirrors, openshift_rbac_groups, machines. Day 1: nfd, nvidia_gpu, custom_metrics_autoscaler, observability, service_mesh, mesh_monitoring, kiali, grafana, perses, tempo, openshift_oauth, connectivity_link, lws, jobset, kueue, openshift_ai, lightspeed, rhtas, rhtas_config, aiagent_operator |

   Dated narrowing (2026-09-10): the 2026-08-17 draft classified tempo
   and mesh_monitoring as external-endpoint capable and carried a
   "Tier B" of twelve pre-installed-operator candidates. Both are
   withdrawn — Day-1 externalization is redis and mariadb only, and the
   operator-externalization contract survives solely as the Tier
   A-operator row (external_secrets, cert_manager), where it is vital
   rather than optional. A future ADR may re-open Tier B for the Day-1
   operator stack; this one no longer claims it. Kiali remains a
   first-class *consumer* re-pointed by clause 5.

4. **In external mode a role stops deploying and starts asserting, and
   the gating is symmetric across all four verbs.**
   - `install`: skip applying both ArgoCD Applications; instead
     (1) assert the endpoint is reachable and TLS-verifiable against
     the supplied CA bundle, (2) assert the clause-7 required config
     exists, (3) seed the external credentials into Vault KV
     `zuno/<c>/...` so consumers receive them through the existing
     ExternalSecrets path unchanged, (4) apply only the consumer-side
     artifacts the platform still owns (e.g. the supplied-CA ConfigMap
     replacing the derived `keycloak-serving-ca`).
   - `check`: gated on the **same** mode key — precheck gating becomes
     mandatory wherever install gating exists, fixing the smtp
     asymmetry. External-mode check never asserts Application
     Synced/Healthy or CR readiness; it asserts endpoint reachability,
     auth validity, and each clause-7 item, keeping the existing
     record-state, never-fail precheck semantics.
   - `reconcile` (ADR-0344): re-run of the idempotent install; missing
     external prerequisites become `blocked_findings` entries (a new
     finding class, "external prerequisite missing"), not hard
     failures.
   - `uninstall`: strict no-op against the external instance — the
     platform never deletes, mutates or de-provisions a service it does
     not own; only consumer-side artifacts it created are removed.
   - Mode flips (either direction) are **migration events, not
     reconciles**: flipping requires an explicit uninstall of the
     built-in instance first; data migration is out of scope here.

5. **One value flow, no second channel: confidential.yml → role vars →
   `gitops_app_extra_helm_values` → chart values → templates.** Every
   consumer chart value that today encodes an in-cluster endpoint
   becomes a full-URL (or host/port) value whose default preserves the
   current internal endpoint — internal mode renders bit-identical
   output. The seams: `keycloakIssuer`/`keycloakJwksUrl` in ai-gateway,
   agent-runtime and mcp-gateway; `keycloak.issuerUrl`/`jwksUrl` in the
   six agent charts' `_helpers.tpl`; the openshift-oauth issuer
   derivation; a **new** `KEYCLOAK_JWKS_URL` value in the
   aiagent-operator chart; the acceptance-gate tasks switching from
   reading Secrets in `zuno-auth` to Vault-sourced values; Kiali's
   Prometheus URL; the ~8 postgres host values; the 6 redis address
   values plus lifting the 2 code defaults into env vars; a new
   `OTEL_EXPORTER_OTLP_ENDPOINT` chart value for the four Python
   services. The Vault seam widens the three cluster-scoped objects
   from `http://<svc>.zuno-vault.svc:8200` to a full-URL value plus an
   optional `caBundle` — and the ClusterSecretStore **keeps the name
   `vault-backend`**: 43 references (~20 hardcoded in templates) make a
   rename a zero-benefit 43-touch change; only the provider config
   swaps. In external mode the built-in Route/Ingress is not created
   (chart guard) and no consumer may reference the internal Route
   hostname. Contract rule for the known footgun:
   `ansible/tasks/apply_gitops_app.yml` replaces
   `spec.source.helm.values` wholesale when
   `gitops_app_extra_helm_values` is set, so any role using it must
   compose the full values document, `clusterBaseDomain` included.

6. **Trust is supplied, never derived; egress and ownership posture are
   recorded explicitly.** The CA chain inverts: internal mode derives
   `keycloak-serving-ca` from the built-in Ingress (hard-failing if
   absent); external mode builds the same ConfigMap from
   `zuno_keycloak_external_ca_bundle` — the same supplied-CA pattern
   applies to the Vault `caBundle` and every Tier-A
   `_external_ca_bundle`. Egress: NetworkPolicies are ingress-only
   today, so external endpoints are reachable without change — recorded
   as the accepted posture, with the mandate that if egress policies
   ever arrive, `_external_*` endpoints are first-class allowlist
   inputs. `allowedFromNamespaces` entries for `zuno-auth`/`zuno-vault`
   become inert (not erroneous) in external mode. Ownership rule: never
   selfHeal-manage objects owned by the external service's operator —
   the `OAuth/cluster` fight between this repo's openshift-oauth chart
   and the startx cluster-auth app (ADR-0346) is the named failure
   mode; in external monitoring mode the openshift-ai chart must not
   apply `cluster-monitoring-config` (it belongs to the customer's
   monitoring team). The aiagent-operator's `RuntimeBindingReady` is a
   Service-presence check that breaks when an in-cluster Service
   disappears in external mode — a named gap for the keycloak/redis
   externalization work.

7. **Everything the built-in self-provisions becomes, for external
   mode, a documented prerequisite that `check` asserts — verify, don't
   assume.** Per service:
   - **ArgoCD**: the external instance — in-cluster in another team's
     namespace, or **remote** — carries the `zuno` AppProject, the
     Subscription-health Lua customization, and RBAC allowing our
     Applications; a remote instance must additionally have this
     cluster declared as a destination. All of it is asserted before
     any Application is applied. This widens the 2026-08-17 draft,
     which ruled the off-cluster case out of scope: the *mechanism* for
     the remote case (native ArgoCD cluster registration vs RHACM) is
     studied and decided in ADR-0557; this clause only fixes what
     external mode must assert, whichever mechanism wins. ADR-0311's
     "Applications are Ansible-applied to the local cluster" is read
     accordingly: they are Ansible-applied to wherever the governing
     ArgoCD lives.
   - **Vault**: init/unseal is skipped, and that is the *only* part of
     the internal setup that is. With the supplied setup token the
     platform **provisions everything else itself, idempotently**:
     the KV v2 mount, the PKI mounts and issuers behind
     `vault-issuer`/`vault-issuer-istio`, the transit engine
     (ADR-0420; release signing has since moved to RHTAS per
     ADR-0535 — the engine list is derived from what the internal
     install actually provisions at implementation time), the
     kubernetes auth mount for *this* cluster, and the named
     policies/roles bound to our ServiceAccounts (`eso-reader`,
     `cert-manager-issuer`, `istio-issuer`). Every operation is
     create-if-missing, never rewrite — the `vault_seed_if_missing`
     semantics of ADR-0345, extended from KV values to mounts,
     policies and roles, so external setup carries the same
     idempotence guarantee as internal. `check` asserts each mount,
     policy and role instead of assuming them. Seeding of confidential
     values into KV still happens through the supplied token, keeping
     `confidential.yml` the single entry point.
   - **External Secrets Operator** (Tier A-operator): external mode
     means the operator is deployed and lifecycle-managed outside this
     installer — assert the CSV/CRDs are present and the controller
     Deployment is Ready, and ship an unmanaged-install document in
     the role/chart README. The `-d1` operand config — the
     `vault-backend` ClusterSecretStore above all — is **ours in both
     modes** and is always applied via ArgoCD: the ESO↔Vault wiring
     exists whatever the mode of either side.
   - **cert-manager** (Tier A-operator): identical contract — external
     mode asserts the unmanaged operator is present and Ready (plus an
     unmanaged-install document); the ClusterIssuers, ACME
     configuration and Certificates stay ours and are always applied
     via ArgoCD.
   - **Keycloak**: admin credentials are **required** in external mode.
     The platform creates the realm `zuno_keycloak_external_realm` if
     missing and reconciles its full configuration — clients, scopes,
     mappers, enumerated at implementation from the inline
     `KeycloakRealmImport` — idempotently over the Admin REST API,
     reusing the reconcile-not-import mechanics of ADR-0530. `check`
     asserts the realm and each expected client. The realm-export
     runbook of the 2026-08-17 draft is demoted from contract to
     documentation annex, and the verify-only mode is withdrawn. The
     file-vault SPI (projected client-secret Secrets) requires owning
     the pod and stays internal-only. The keycloak chart's embedded
     PostgreSQL block becomes dead config.
   - **AAP**: admin credentials are **required** in external mode. The
     platform provisions the org, project, inventory, the two
     credentials, and every job and workflow template — the full
     `aap-config` surface — idempotently. Implementation constraint:
     the `aap-config` chart's `tower.ansible.com/v1alpha1` CRs assume
     the resource-operator runs in-cluster with the AAP operator; in
     external mode there is none, so provisioning generalizes the
     GET-then-POST REST path the `aap_config` role already uses for
     the org, the inventory host and credential attachment — REST for
     everything, zero in-cluster dependency — rather than installing a
     lone resource-operator. `check` asserts org, project and each
     template exist.
   - **PostgreSQL / MariaDB**: databases and roles are pre-created by
     the DBA (PGO's `spec.users[]` has no external equivalent) — for
     PostgreSQL that list includes the five AAP databases when AAP is
     internal; for MariaDB it is the clause-2 inventory (`mlpipeline`,
     `mlops`, `trillian`), one credential pair per database, and any
     database added later adds its pair to the schema and its consumer
     to the inventory. Credentials from `confidential.yml` are seeded
     into Vault and delivered by ExternalSecret templates that
     reproduce the exact Secret shapes consumers already mount (the
     pguser shape for postgres; the `rag-pipeline-db`/`mlops-db`/
     Trillian shapes for mariadb).
   - **Redis**: reachable; AUTH succeeds when a password is supplied;
     and the endpoint is provisioned for the platform's consumer
     inventory — seven today (ai-gateway, aiagent-operator, and the
     comage/finage/advantage/tekos session stores, plus the
     agent-frontend code default), so `check` asserts the server's
     connection budget (`maxclients` or managed-tier equivalent)
     accommodates them. A new consumer updates the inventory and the
     assertion.

8. **External mode changes who runs a service, not how config flows.**
   Charts remain the only source of rendered config; Applications
   remain Ansible-applied (ADR-0311/0312); secrets flow only
   confidential.yml → Vault KV → ExternalSecrets — external credentials
   never appear in chart values, git, or Application specs; only
   non-secret URLs and CA bundles ride the Helm-values path. Ansible
   remains a thin bootstrapper whose external-mode job is assert +
   seed, never manage. No new config file or entry point is introduced.

9. **MariaDB pilots the contract; Keycloak is the first hard one.**
   MariaDB's three consumers (rag-ingestion and mlops already implement
   `metadataDatabase.mode: externalMySQL` end-to-end; rhtas/Trillian is
   the third — correction 2026-09-10, the original draft counted two)
   all resolve their credentials from Vault independently of the
   mariadb chart, so the pilot exercises the whole contract — mode key,
   symmetric gating, external check assertions, Vault seeding,
   ExternalSecret shape — with minimal consumer-seam surgery (the
   endpoint hosts are chart literals to parameterize, and the rhtas
   Trillian schema load must stop exec-ing into the built-in pod) and
   the smallest possible blast radius. WP-143 carries this pilot. Then keycloak (highest value; exercises CA supply, mandatory
   admin-credential provisioning, the oauth integration and the widest
   seam set), then vault (the full-setup contract), then postgresql,
   redis, aap, and the two Tier A-operator components
   (external_secrets, cert_manager — mostly documentation plus check
   surgery); argocd lands last, once ADR-0557 has picked its
   mechanism. Implementation lands one component per work package
   mapped to this clause; roadmap briefs live under `docs/roadmap/`,
   not in this ADR.

10. **The seven Day-0 Tier-A components are vital: Day 1 does not
    start until each is functional, whatever its mode.** argocd,
    vault, external_secrets, cert_manager, postgresql, keycloak and
    aap (with aap_config) must pass their functional assertion —
    internal: Applications Synced/Healthy plus CR readiness, as today;
    external: the clause-7 assertions — before `make d1 install`
    proceeds. This is a **hard gate on the Day-1 entry point**,
    distinct from the record-state, never-fail precheck contract:
    prechecks keep recording, the gate blocks. It rides the
    `check_cluster_readiness` probe mechanism (WP-130/ADR-0547), which
    already blocks `make d0 install` on would-fail findings; this
    clause extends the same pattern to the d1 boundary.

11. **Perfect dependency abstraction: no component ever reads another
    component's mode key.** Every cross-component dependency is
    consumed through the clause-5/clause-8 seam — Vault KV +
    ExternalSecrets for secrets, Helm values for non-secrets — and
    that seam must render all four internal/external combinations of
    any dependent pair indistinguishable to the consumer. Normative
    examples: external Keycloak stops using our PostgreSQL entirely
    (its chart's DB block is dead config, whatever postgresql's mode);
    internal AAP against external PostgreSQL means the five AAP
    databases are pre-created by the DBA and delivered in the exact
    Secret shapes the aap chart's ExternalSecrets already mount; ESO
    bridges Vault to consumers identically whether Vault, ESO, or both
    are external. A role or chart that branches on another component's
    `zuno_<c>_mode` key is a contract violation — the information a
    consumer needs must arrive as an endpoint value or a Secret, never
    as a mode.

## Consequences

- `confidential.example.yml` grows one mode block per Tier-A component
  (~9 blocks) but stays the single per-environment interface; absent
  keys keep every existing environment on `internal`, unchanged.
- Every consumer endpoint default becomes an overridable value; the
  internal-mode rendered output is bit-identical — a diffable claim
  each seam change must uphold.
- Tier-A prechecks gain a second personality (assert-external),
  roughly doubling their task surface.
- Mode flips are migrations, not toggles; no data-movement automation
  is promised.
- External mode narrows the demo surface: the file-vault SPI and PGO
  backups/pgBackRest don't apply — each component's runbook must carry
  an honest feature-parity note.
- Known dead-config surfaces (the keycloak chart's PostgreSQL block,
  `allowedFromNamespaces` entries for externalized services) are
  accepted as inert rather than templated away.

## Security considerations

External credentials enter through the same gitignored file as every
other secret and land only in Vault KV. The external-Vault setup token
is the widest credential in the schema — it provisions mounts, policies
and roles — so it should be scoped to exactly that by the Vault admin
and rotated after Day 0; it is never persisted outside Vault KV itself.
CA bundles are explicit inputs; there is deliberately no skip-verify
knob anywhere in the schema, and postgres defaults to `verify-full`.
The trust boundary widens: platform JWTs and tokens transit to
endpoints outside the cluster over currently-unrestricted egress —
recorded and accepted for the demo, flagged as first-class input for
any future egress-policy work. Keycloak and AAP admin credentials are
mandatory in external mode and are used by an idempotent
reconciliation, never by hand; they grant realm/organization
administration on services the platform does not own, which their
owners must accept knowingly. A compromised external service becomes
shared fate with the platform; internal mode remains the
isolation-maximizing default.

## Operational considerations

- Failure modes shift from "pod not ready" to "endpoint unreachable /
  required config missing" — check output must name the exact failed
  clause-7 assertion, per component.
- External instances are not version-pinned by this repo;
  minimum-version expectations are recorded per component at
  implementation time.
- Reconcile stays green-with-findings: missing external prerequisites
  are `blocked_findings` (ADR-0344), each carrying its runbook
  solution.
- The Makefile/playbook component-list drift (`image_mirrors`) is
  resolved alongside the first implementation, since mode gating keys
  off the component list.
- Each externalized component ships a runbook artifact for the
  external admin (realm export, Vault policy files, Prometheus scrape
  config) in its role/chart README.

## Acceptance criteria

(This ADR delivers a decision record only; implementation acceptance
lives with the clause-9 work packages.)

- `docs/adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md`
  exists, containing the clause-2 schema block and the clause-3 table
  classifying all 36 playbook components (13 Day 0 + 23 Day 1).
- The v0.9 index table in `docs/adr/README.md` has the ADR-0352 row
  and its status string matches the body's `Proposed`.
- No implementation surface has changed: `zuno_*_mode` keys appear
  nowhere under `ansible/` or `gitops/`.
- The external-mode lifecycle contract covers all four verbs
  (install/check/reconcile/uninstall), including symmetric precheck
  gating, plus the Day-1 vital gate (clause 10) and the
  dependency-abstraction rule (clause 11).
- `make check` passes (`platform/docs/check_docs.py` ADR index
  included).

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0117](0117-implement-confluence-as-the-first-real-external-mcp-integration.md)
- [ADR-0211](0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md)
- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md)
- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md)
- [ADR-0344](0344-track-blocked-resources-and-add-a-day-0-reconcile-verb.md)
- [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md)
- [ADR-0346](0346-trust-the-ingress-router-ca-and-absorb-the-startx-cluster-auth-oauth-settings.md)
- [ADR-0347](0347-trust-the-vault-pki-root-for-the-oauth-openid-idp.md)
- [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md)
- [ADR-0354](0354-add-ansible-automation-platform-as-a-day-1-component.md)
- [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md)
- [ADR-0421](0421-reshape-day-0-day-1-boundaries-around-always-on-infra.md)
- [ADR-0530](0530-reconcile-keycloak-clients-instead-of-relying-on-a-create-only-realm-import.md)
- [ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md)
- [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md)
- [ADR-0556](0556-introduce-a-zuno-operator-with-foundation-infra-and-stack-crds.md)
- [ADR-0557](0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md)
