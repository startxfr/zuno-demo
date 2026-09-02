# ADR-0352: Run day-0 platform services in internal or external mode

- **Status:** Proposed
- **Target:** v0.9
- **Date:** 2026-08-17
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
  (28 entries, snake_case) — which has drifted from the Makefile's
  `DAY0_COMPONENTS` (27 entries; `image_mirrors` is missing there).
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
   trusted by the system/cluster CA set). There is deliberately **no**
   `insecure`/skip-verify key anywhere in the schema. Validation:
   `mode: external` with any required key left at the `"xxxxxx"`
   sentinel fails fast in the role, before any apply; `mode: internal`
   ignores every `_external_*` key. Non-secret values (URLs, CA bundles,
   mount names) flow to charts as Helm values; secret values flow only
   confidential.yml → Vault KV → ExternalSecrets (clause 8). The schema
   destined for `confidential.example.yml` at implementation time:

   ```yaml
   # --- Day-0 component modes (ADR-0352) ------------------------------
   # Each Tier-A component: internal (default, this repo deploys it) |
   # external (a pre-existing instance is used; the built-in is not
   # deployed). Absent keys mean internal.

   # Keycloak (identity provider)
   zuno_keycloak_mode: internal
   zuno_keycloak_external_url: "xxxxxx"        # e.g. https://sso.corp.example.com
   zuno_keycloak_external_realm: "zuno"        # realm expected on the external instance
   zuno_keycloak_external_ca_bundle: ""        # PEM; "" = publicly/cluster trusted
   zuno_keycloak_external_admin_username: "xxxxxx"  # optional; sentinel = verify-only,
   zuno_keycloak_external_admin_password: "xxxxxx"  # set = platform may provision realm/clients

   # Vault (secrets; PKI stays unsupported externally - see clause 7)
   zuno_vault_mode: internal
   zuno_vault_external_url: "xxxxxx"           # e.g. https://vault.corp.example.com:8200
   zuno_vault_external_ca_bundle: ""
   zuno_vault_external_kv_mount: "zuno"        # KV v2 mount granted to the platform
   zuno_vault_external_auth_mount: "kubernetes" # k8s auth mount configured for THIS cluster
   zuno_vault_external_token: "xxxxxx"         # short-lived; seeding + verification only

   # PostgreSQL - one pre-created role per platform database. Databases:
   # zuno, keycloak, rag-tech, maas, agent-checkpoints, ogx, rag-sales,
   # rag-sxa-legacy, rag-adv, rag-project (from the PGO spec.users list).
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

   # MariaDB - databases: mlpipeline (rag-ingestion + mlops pipeline store)
   zuno_mariadb_mode: internal
   zuno_mariadb_external_host: "xxxxxx"
   zuno_mariadb_external_port: "3306"
   zuno_mariadb_external_ca_bundle: ""
   zuno_mariadb_external_db_mlpipeline_username: "xxxxxx"
   zuno_mariadb_external_db_mlpipeline_password: "xxxxxx"

   # Redis
   zuno_redis_mode: internal
   zuno_redis_external_host: "xxxxxx"
   zuno_redis_external_port: "6379"
   zuno_redis_external_password: "xxxxxx"      # sentinel = no AUTH
   zuno_redis_external_ca_bundle: ""           # "" + port 6379 = plaintext

   # Tempo (trace backend; the endpoint is the OTLP receiver)
   zuno_tempo_mode: internal
   zuno_tempo_external_otlp_endpoint: "xxxxxx" # e.g. https://tempo.corp.example.com:4317
   zuno_tempo_external_ca_bundle: ""

   # Metrics backend. The mode key rides on mesh_monitoring - the
   # component that deploys the only Prometheus this platform owns;
   # kiali is re-pointed to the external query API.
   zuno_mesh_monitoring_mode: internal
   zuno_mesh_monitoring_external_prometheus_url: "xxxxxx"
   zuno_mesh_monitoring_external_ca_bundle: ""

   # ArgoCD (external = a pre-existing IN-CLUSTER ArgoCD carries our
   # Applications; an off-cluster ArgoCD is out of scope - clause 7)
   zuno_argocd_mode: internal
   zuno_argocd_external_namespace: "xxxxxx"    # namespace of the existing instance
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

3. **All 28 playbook components are classified into three tiers.** Mode
   keys attach to the component that deploys the service in internal
   mode — which is why the metrics key rides on `mesh_monitoring`
   rather than a nonexistent "prometheus" component, an accepted naming
   awkwardness.

   | Tier | Meaning | Components |
   |---|---|---|
   | A — external-endpoint capable | A running instance can be supplied; full clause-2 schema, clause-4 lifecycle, clause-7 prerequisites | keycloak, vault, postgresql, mariadb, redis, tempo, mesh_monitoring, argocd, smtp (grandfathered, always-external) |
   | B — pre-installed-operator capable | "External" means the operator Subscription/CSV already exists (installed by the cluster team); our `-d0` Application is skipped, the `-d1` operand config still applies where it is ours to own | cert_manager, external_secrets, observability, service_mesh, nfd, nvidia_gpu, connectivity_link, lws, custom_metrics_autoscaler, jobset, kueue, openshift_ai |
   | C — always internal | Cluster-topology glue where "external" is meaningless | admin_context, namespaces, image_mirrors, openshift_rbac_groups, openshift_oauth, machines, kiali |

   Tier B gets the same `zuno_<c>_mode` key but a slimmer contract: no
   URL/CA; the external check asserts CSV/CRD presence instead of
   endpoint reachability; its detailed schema is deferred to the
   per-component work — this ADR fixes only the vocabulary and check
   semantics. Kiali is Tier C but is a first-class *consumer*
   re-pointed by clause 5. (Tempo also has a Tier-B reading — the
   operator pre-installed — noted, not elaborated.)

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
   - **Keycloak**: the realm `zuno_keycloak_external_realm` exists and
     carries the expected clients, scopes and mappers (enumerated at
     implementation from the inline `KeycloakRealmImport`). The
     file-vault SPI (projected client-secret Secrets) requires owning
     the pod and is internal-only. Default provisioning path: a runbook
     (realm export) handed to the external Keycloak admin; opt-in: an
     Admin-REST provisioning job when the
     `zuno_keycloak_external_admin_*` credentials are set. The keycloak
     chart's embedded PostgreSQL block becomes dead config.
   - **Vault**: init/unseal is skipped. Assert instead: the KV v2
     mount is writable with the supplied token, the kubernetes auth
     mount is configured for *this* cluster, and the named
     policies/roles bound to our ServiceAccounts (`eso-reader`,
     `cert-manager-issuer`, `istio-issuer`) exist. **External Vault
     PKI is unsupported initially**: certificate consumers cut over
     via the existing `acme.consumers.*` staged flip instead, keeping
     the external-Vault prerequisite list to KV + k8s-auth. Seeding of
     confidential values into KV still happens (via the short-lived
     supplied token), keeping `confidential.yml` the single entry
     point.
   - **Prometheus** (`mesh_monitoring` external): the external
     instance scrapes the mesh targets (equivalents of our
     ServiceMonitors/MonitoringStack), hosts equivalents of our
     PrometheusRules, and answers a probe query at the supplied URL —
     the same query Kiali depends on.
   - **PostgreSQL / MariaDB**: databases and roles are pre-created by
     the DBA (PGO's `spec.users[]` has no external equivalent);
     credentials from `confidential.yml` are seeded into Vault and
     delivered by ExternalSecret templates that reproduce the exact
     Secret shapes consumers already mount (the pguser shape for
     postgres, the `rag-pipeline-db` shape for mariadb).
   - **Redis**: reachable; AUTH succeeds when a password is supplied.
   - **ArgoCD**: the existing in-cluster instance carries the `zuno`
     AppProject, the Subscription-health Lua customization, and RBAC
     allowing our Applications — asserted before any Application is
     applied into `zuno_argocd_external_namespace`. An off-cluster
     ArgoCD is explicitly out of scope (Applications are
     Ansible-applied to the local cluster, ADR-0311).

8. **External mode changes who runs a service, not how config flows.**
   Charts remain the only source of rendered config; Applications
   remain Ansible-applied (ADR-0311/0312); secrets flow only
   confidential.yml → Vault KV → ExternalSecrets — external credentials
   never appear in chart values, git, or Application specs; only
   non-secret URLs and CA bundles ride the Helm-values path. Ansible
   remains a thin bootstrapper whose external-mode job is assert +
   seed, never manage. No new config file or entry point is introduced.

9. **MariaDB pilots the contract; Keycloak is the first hard one.**
   MariaDB's only two consumers (rag-ingestion, mlops) already
   implement `metadataDatabase.mode: externalMySQL` end-to-end, so the
   pilot exercises the whole contract — mode key, symmetric gating,
   external check assertions, Vault seeding, ExternalSecret shape —
   with zero consumer-seam surgery and the smallest possible blast
   radius. Then keycloak (highest value; exercises CA supply, realm
   prerequisites, the oauth integration and the widest seam set), then
   vault, then mesh_monitoring, redis, postgresql, tempo, argocd; Tier
   B components follow per environment need. Implementation lands one
   component per work package mapped to this clause; roadmap briefs
   live under `docs/roadmap/`, not in this ADR.

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
- External mode narrows the demo surface: the file-vault SPI, PGO
  backups/pgBackRest and MonitoringStack ownership don't apply — each
  component's runbook must carry an honest feature-parity note.
- Known dead-config surfaces (the keycloak chart's PostgreSQL block,
  `allowedFromNamespaces` entries for externalized services) are
  accepted as inert rather than templated away.

## Security considerations

External credentials enter through the same gitignored file as every
other secret and land only in Vault KV; the external-Vault bootstrap
token is short-lived and used only for seeding and verification. CA
bundles are explicit inputs; there is deliberately no skip-verify knob
anywhere in the schema, and postgres defaults to `verify-full`. The
trust boundary widens: platform JWTs and tokens transit to endpoints
outside the cluster over currently-unrestricted egress — recorded and
accepted for the demo, flagged as first-class input for any future
egress-policy work. Keycloak admin credentials are optional and
verify-only by default; provisioning against the external instance is
opt-in. A compromised external service becomes shared fate with the
platform; internal mode remains the isolation-maximizing default.

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
  classifying all 28 playbook components.
- The `## version 0.3` index table in `docs/adr/README.md` has the
  ADR-0352 row and its status string matches the body's `Proposed`.
- No implementation surface has changed: `zuno_*_mode` keys appear
  nowhere under `ansible/` or `gitops/`.
- The external-mode lifecycle contract covers all four verbs
  (install/check/reconcile/uninstall), including symmetric precheck
  gating.
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
