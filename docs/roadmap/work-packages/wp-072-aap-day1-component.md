# WP-072: Install Ansible Automation Platform as a Day 1 component

- **State:** Done (live-verified 2026-08-25) - role, chart, apps, four
  dedicated Crunchy databases, Vault seeds, Keycloak OIDC client
  registration, Makefile/playbook wiring all committed. **CRD inventory
  complete** (step 10, done live against `demo222` before any code was
  written): subscribed the operator (`ansible-automation-platform-
  operator`, default channel `stable-2.7`, catalog `redhat-operators`,
  `InstallModes` `OwnNamespace`/`SingleNamespace`/`MultiNamespace` only),
  ran `oc explain` against the real CRDs, then deliberately deleted the
  Subscription/OperatorGroup/namespace again before creating any
  `AnsibleAutomationPlatform` CR - no Gateway/Controller/Hub/EDA pod was
  ever started. Findings (see `ansible/roles/aap/README.md` for the full
  writeup):
  - **The unified CR does NOT take one shared external-database secret**
    (this ADR-0354 clause 5's original open question) - Gateway
    (`spec.database.database_secret`) and EDA
    (`spec.eda.database.database_secret`) use one field name; Controller
    (`spec.controller.postgres_configuration_secret`) and Hub
    (`spec.hub.postgres_configuration_secret`) use another. Resolved by
    repeating the ADR-0315 dedicated-database pattern four times rather
    than switching mechanisms, per the WP's own pre-authorized fallback.
  - `automationhub.spec.file_storage_access_mode` accepts `ReadWriteOnce`
    (not RWX-only) - Hub is configured `storage_type: file` +
    `ReadWriteOnce`, matching this repository's `gp3-csi`-everywhere
    convention with no new storage class or S3 dependency.
    **Superseded by WP-075 (2026-08-25):** the shared RWO PVC across
    api/content/worker deadlocked live when `api` landed on a different
    node than content/worker (this WP's `podAffinity` only covered
    worker->content) - Hub moved to `storage_type: s3` to remove the
    failure class.
  - Confirmed live replica-count field names for non-HA sizing:
    `spec.api.replicas` (Gateway); `spec.controller.replicas`/
    `web_replicas`/`task_replicas`; `spec.hub.{api,web,worker}.replicas`;
    `spec.eda.{api,default_worker,activation_worker,ui}.replicas`
    (`default_worker`/`activation_worker` default to 2, trimmed to 1).
  - A CR-level `spec.bundle_cacert_secret` field exists (Gateway's own
    outbound-HTTPS CA trust bundle) - left unset in this WP, deferred to
    WP-073 alongside the OIDC authenticator wiring it would actually
    serve.
  - **Not verified**: the exact key set each `postgres_configuration_secret`/
    `database_secret` Secret requires (no `alm-examples` were published on
    this channel to confirm against; the chart follows the documented
    upstream awx-operator convention, unverified end to end), and whether
    EDA's `automation_server_url` (required on the standalone `EDA` CRD)
    is auto-wired by the unified CR or needs setting explicitly - both
    open until the first real `make d1 install aap`.
  - **Path A confirmed for WP-073**: the same operator bundle already
    installs Kubernetes CRDs for `AnsibleProject`, `JobTemplate`,
    `AnsibleCredential`, `AnsibleInventory`, `AnsibleJob`, `AnsibleSchedule`,
    `AnsibleWorkflow`, `WorkflowTemplate` (group `tower.ansible.com/
    v1alpha1`) - no second Subscription and no `infra.aap_configuration`
    collection are needed. WP-073 can proceed directly with Path A.

  **Live install verified (2026-08-24/25)**: `make d1 install aap` run for
  real on `demo222`; Gateway, Controller, Hub and EDA all Running healthy,
  `make day1 check aap` reports installed. Three real platform bugs were
  found and fixed along the way (none specific to `aap` - two were already
  silently breaking Keycloak): a NetworkPolicy regression blocking
  cross-namespace direct-to-primary Postgres (commit `fd45ff8`), the
  PGO/pg15+ public-schema CREATE grant gap (commit `c76c668` - note its
  Sync-hook Job inherits this chart's known hook-not-firing ArgoCD issue,
  so the grants were also applied manually per the existing runbook), and
  Hub's RWO-volume Multi-Attach on a no-RWX cluster (commit `99b0f40`,
  podAffinity pinning worker to content's node - applied to the
  `AutomationHub` sub-CR directly, since the unified CR does not forward
  `hub.worker.affinity`; a re-reconcile of the parent CR may revert it,
  re-check after any operator upgrade). Remaining cosmetic issue:
  `aap-automationmetricsservice-web` restarts intermittently on its
  `/health/` probe (secondary telemetry component, not blocking).

  **Addendum (2026-08-25) - Red Hat subscription activation**: on user
  request, `tasks/install.yml` gained a final step attaching the
  operator's own Red Hat account entitlement (`zuno_aap_enabled`/
  `zuno_aap_rhn_username`/`zuno_aap_rhn_password` in
  `ansible/confidential.yml`), hard-failing the install when enabled but
  broken. Endpoint/semantics confirmed live: single `POST
  /api/controller/v2/config/` with `subscriptions_username`/`password`
  attaches directly on 2.7 (no Tower-style pool_id two-step); a fresh
  install already carries an ambient auto-attached Developer
  subscription, so idempotency keys on `subscription_id` (which account),
  not on compliance alone. See `ansible/roles/aap/README.md`.
- **ADRs:** ADR-0354 (Add Ansible Automation Platform as a new Day 1
  component)
- **Depends on:** `postgresql`, `vault`, `external_secrets`, `keycloak`,
  `openshift_oauth` already installed and Synced+Healthy on the target
  cluster (all pre-existing Day 0/Day 1 components).
- **Unblocks:** WP-073 (`aap-config` - the Project/Job Template that runs
  on top of this component), WP-074/ADR-0355 (`mcp-aap`).
- **Estimated files touched:** ~20 (role: 3, chart: ~8, apps: 2,
  postgresql chart additions: 3, keycloak chart additions: 3, vault role:
  1, namespaces chart: 1, Makefile/playbooks: 4, docs: ~4).

> Execute this brief as a standalone task from the repository root. Read
> ADR-0354 in full (all 8 Decision clauses, including the 2026-08-24
> amendment) before editing - it is the source of truth for every decision
> below. This WP ends with a live CRD inventory step; stop and report its
> findings before starting WP-073, do not guess ahead of them.

## Goal

Install AAP (Gateway, Controller, Hub, EDA - AAP 2.5+, `aap.ansible.com/
v1alpha1`) as a new Day 1 component `aap`, non-HA, in its own namespace
`zuno-aap` with a default-deny `NetworkPolicy` baseline, following the
exact role+chart+Application-pair shape every other operator-backed
component in this repository already uses. No new deployment mechanism is
introduced.

## ADR references

Primary: [docs/adr/0354-add-ansible-automation-platform-as-a-day-1-component.md](../../adr/0354-add-ansible-automation-platform-as-a-day-1-component.md) -
read all 8 Decision clauses, the amendment note at the top, and the
Security/Operational considerations sections.

Related: ADR-0048 (PackageManifest channel discovery), ADR-0056/ADR-0060
(Day 0-3 sequencing), ADR-0315 (dedicated Keycloak database - the pattern
this WP repeats for AAP), ADR-0320 (namespace label convention), ADR-0411
(trusting the Vault PKI root for an OIDC client's Keycloak route).

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- `oc get applications.argoproj.io -n openshift-gitops zuno-postgresql-d1 zuno-keycloak-d1 zuno-openshift-oauth-d1` all Synced/Healthy (never `oc get application` bare - it hits a decoy empty CRD).
- Read in full, as the patterns to mirror:
  - `ansible/roles/kueue/tasks/{install,precheck,uninstall}.yml` - the
    canonical PackageManifest-discovery + `apply_gitops_app.yml` +
    precheck/uninstall shape.
  - `ansible/roles/keycloak/tasks/install.yml` and
    `gitops/charts/keycloak/` (`Chart.yaml`, `values.yaml`,
    `templates/keycloak.yaml`, `templates/checks.yaml`,
    `templates/externalsecret-postgresql.yaml`) - the closest analogue:
    an operator subscribed into its own dedicated namespace, with a
    dedicated database and a Keycloak OIDC client of its own.
  - `gitops/charts/postgresql/templates/postgrescluster.yaml` and
    `values.yaml`'s `keycloakDatabase` block (~line 124), plus
    `gitops/charts/keycloak/templates/externalsecret-postgresql.yaml` -
    the exact ADR-0315 dedicated-database pattern.
  - `ansible/roles/vault/tasks/install.yml`'s `_vault_generated_secrets`
    dict (~lines 295-411) and `ansible/tasks/vault_seed_if_missing.yml`.
  - `gitops/charts/namespaces/values.yaml`'s `platformNamespaces` list
    (the `zuno-auth` entry specifically) and
    `gitops/charts/namespaces/templates/networkpolicy-platform.yaml` (the
    deny-all baseline every entry gets).
  - `ansible/tasks/apply_gitops_app.yml` (note: `gitops_app_extra_helm_values`
    **replaces**, not merges, the manifest's own `helm.values`).
  - `ansible/tasks/sync_keycloak_serving_ca.yml` (ADR-0411) and its only
    current caller, `ansible/roles/agents/tasks/install.yml:19`.

## Repo changes (step by step)

1. **Namespace `zuno-aap` (Day 0 `namespaces` component).** In
   `gitops/charts/namespaces/values.yaml`, add a `platformNamespaces`
   entry:

   ```yaml
   - name: zuno-aap
     displayName: Zuno Ansible Automation Platform
     description: >-
       Ansible Automation Platform (Gateway, Controller, Hub, EDA) - the
       platform's automation-execution surface.
     allowedFromNamespaces: []
     extraLabels:
       zuno.io/managed: "true"
   ```

   Deliberately **no** `istio-injection: enabled` (AAP stays outside the
   mesh, like other heavy operator-backed namespaces). Then add `zuno-aap`
   to the `allowedFromNamespaces` list of the existing `zuno-data` entry
   (AAP Controller reaching its dedicated PostgreSQL database) and the
   existing `zuno-auth` entry (in-cluster JWKS/token calls to Keycloak),
   each with a one-line comment matching the file's existing style (see
   the `zuno-vault`/`zuno-data` entries for the comment convention). Check
   `limitrange-namespace.yaml`/`resourcequota-namespace.yaml` in the same
   chart - AAP's non-HA sizing (step 4) may still exceed the default
   per-namespace LimitRange/quota; raise or exempt `zuno-aap` if so
   (precedent: the LimitRange cap documented for `demo222`'s ArgoCD).

2. **Ansible role `ansible/roles/aap/`.**
   - `tasks/install.yml`: `k8s_info` PackageManifest lookup for
     `ansible-automation-platform-operator` in `openshift-marketplace`
     (default channel `stable-2.5`, fall back to `defaultChannel`, fail
     with an actionable message if the package is entirely absent - copy
     kueue's exact shape). Apply `zuno-aap-d0` then `zuno-aap-d1` via
     `apply_gitops_app.yml`, waiting Synced+Healthy between them with
     generous retries (`gitops_app_wait_retries: 90`,
     `gitops_app_wait_delay: 20` - Gateway+Controller+Hub+EDA starting
     together is comparable to `openshift_ai`'s `DataScienceCluster`).
     Remember to re-supply every toggle `gitops_app_extra_helm_values`
     needs (it replaces, not merges). Include
     `ansible/tasks/sync_keycloak_serving_ca.yml` for `zuno-aap` if
     Keycloak's route uses the Vault PKI root rather than a public CA
     (check `gitops/apps/keycloak/application-d1.yaml`'s
     `ingress.acmeWildcardTLS` value live).
   - `tasks/precheck.yml`: never fail. `ansible/tasks/
     check_gitops_app_state.yml` on both Applications, `k8s_info` on the
     `AnsibleAutomationPlatform` CR's conditions with
     `ignore_errors: true`, end with `ansible/tasks/record_state.yml`.
   - `tasks/uninstall.yml`: delete `zuno-aap-d1`, then
     `ansible/tasks/remove_operator.yml`, then delete `zuno-aap-d0` (kueue's
     contract). Check the CR for finalizers before deleting - if present,
     confirm the operator is still running when the CR delete is issued.

3. **Chart `gitops/charts/aap/`.**
   - `Chart.yaml`: dependency on the vendored startx `operator` chart
     (`21.3.277`, `repository: "alias:startx"`) - **not** the `project`
     subchart (the namespace already exists, created in step 1, exactly
     like `zuno-auth` for keycloak). OperatorGroup mode: OwnNamespace,
     targeting the pre-existing `zuno-aap`.
   - `values.yaml`: `operator.enabled`/`aap.enabled` both default `false`;
     `postgresqlHost: zuno-postgresql-primary.zuno-data.svc.cluster.local`
     (direct-to-primary, matching keycloak's PgBouncer-avoidance); a
     non-HA sizing block (single replica per AAP sub-component, trimmed
     resource requests/limits - confirm the actual CR field names against
     the live CRD schema in step 6, do not guess field names into this
     file ahead of that).
   - `templates/aap.yaml`: the single `AnsibleAutomationPlatform` CR,
     gated by `.Values.aap.enabled`.
   - `templates/checks.yaml`: fail the render if a required
     discovery-time value (channel, catalog source, postgres host) is
     still empty - copy keycloak's/kueue's `checks.yaml`.
   - `templates/externalsecret-postgresql.yaml`: consumer-side database
     credential from `zuno/aap/postgresql-app` (copy `gitops/charts/
     keycloak/templates/externalsecret-postgresql.yaml`; verify the exact
     key names AAP's external-database secret contract expects against
     the operator's own documentation/CRD once installed - do not assume
     they match Keycloak's).
   - `templates/externalsecret-admin.yaml`: admin credential from
     `zuno/aap/admin`.
   - `README.md`: mirror `ansible/roles/keycloak/README.md`'s structure.

4. **ArgoCD apps `gitops/apps/aap/`.**
   - `application-d0.yaml` (sync-wave `-156`) and `application-d1.yaml`
     (sync-wave `-155`) - the free gap between `grafana` (`-158`) and
     `mcp` (`-152`). Copy keycloak's apps: `CreateNamespace: false`
     (namespace already exists), the same `ignoreDifferences` entry for
     `OperatorGroup /metadata/annotations/olm.providedAPIs`.

5. **Dedicated Crunchy database (ADR-0315 pattern).**
   - `gitops/charts/postgresql/templates/postgrescluster.yaml`: add an
     entry to `spec.users[]` for owner `aapcontroller`, database `aap`.
   - `gitops/charts/postgresql/values.yaml`: add an `aapDatabase:` block
     (copy the `keycloakDatabase` block, ~line 124).
   - `gitops/charts/postgresql/templates/externalsecret-aap.yaml`: PGO-side
     password override from `zuno/aap/postgresql-app` (copy
     `externalsecret-keycloak.yaml`).
   - **Open verification point:** AAP 2.5's unified CR may want one
     external-database credential for the whole platform, or one per
     sub-component (Gateway/Controller/Hub/EDA). Confirm which via the
     live CRD schema (step 6) before finalizing whether this is one
     `aapDatabase` entry or several. If several are needed, repeat this
     exact ADR-0315 pattern per sub-component - do not switch to an
     operator-managed internal postgres without stopping to ask first
     (that would contradict ADR-0354 clause 5, which is a settled
     decision).

6. **Vault seeds** (`ansible/roles/vault/tasks/install.yml`,
   `_vault_generated_secrets` dict): add `aap/postgresql-app` (username
   `aapcontroller`, letters+digits only) and `aap/admin` (username
   `admin`).

7. **Keycloak OIDC client (Keycloak-side only - four coordinated edits,
   copy the `tekos-frontend` client throughout):**
   - `gitops/charts/keycloak/files/realm-zuno.json`: confidential client
     `aap`, `"secret": "${vault.aap_client_secret}"`, redirect URIs on the
     literal `apps.mycluster.example.com` placeholder pointing at the AAP
     gateway route (exact host confirmed after first install - use a
     wildcard-safe placeholder now, correct it once the route exists).
   - Vault seed `keycloak/aap-client` (client_secret) - part of step 6.
   - `gitops/charts/keycloak/templates/externalsecret-aap-client.yaml`
     (sync-wave `-20`, `ClusterSecretStore: vault-backend`).
   - `gitops/charts/keycloak/templates/keycloak.yaml`: projected-volume
     entry `path: zuno_aap__client__secret` (double-underscore escaping -
     get this wrong and the lookup fails silently).

   **Do not** attempt the AAP-side authenticator configuration (pointing
   Gateway's OIDC settings at this client) in this WP - ADR-0354 clause 6
   defers that to WP-073's CRD inventory. Admin login via `zuno/aap/admin`
   is the interim path.

8. **Makefile/playbooks.**
   - `Makefile` `DAY1_RUN_COMPONENTS` (~line 21-22): insert `aap` between
     `openshift-oauth` and `connectivity-link`.
   - `ansible/playbooks/day1_install.yml` and `day1_check.yml`: insert
     `aap` in `day1_components`, same position, update the header comment.
   - `ansible/playbooks/day1_uninstall.yml`: insert `aap` in the
     **reverse-order** list, immediately *before* `openshift_oauth`.

9. **Docs.** Add `aap` rows/entries to `gitops/apps/README.md`'s
   component table, `gitops/charts/README.md`, `ansible/README.md`,
   `docs/platform/installation.md`.

10. **Live CRD inventory (do this last, on a real cluster, after the
    operator installs successfully).** Run and record the output in this
    WP's State section:

    ```bash
    oc get packagemanifest -n openshift-marketplace | grep -i ansible
    oc api-resources | grep -Ei 'ansible|aap|awx'
    oc explain ansibleautomationplatform.spec --recursive
    ```

    Also run `oc explain` on any `JobTemplate`/`AnsibleJob`/
    `AnsibleProject`-shaped type found. This inventory is what WP-073
    picks its mechanism (Path A vs Path B) from - **stop and report these
    findings before starting WP-073**, do not assume either path ahead of
    this output.

## What NOT to touch

- Do not create `aap-config`, its Project, or its Job Template in this
  WP - that is WP-073, gated on this WP's CRD inventory (step 10).
- Do not attempt the AAP-side Keycloak authenticator wiring (step 7's
  explicit deferral).
- Do not move `postgresql`, `vault`, or `keycloak` to a different day -
  ADR-0354's amendment settled this; `aap` moves, nothing else does.
- Do not add `istio-injection: enabled` to `zuno-aap`.
- Do not widen `zuno-aap`'s `allowedFromNamespaces` beyond what step 1
  specifies (v0.3's `mcp-aap` addition is ADR-0355's edit, not this WP's).
- Do not hardcode the OLM channel or catalog source name in checked-in
  chart values - discovery happens at deploy time (ADR-0048), same as
  every other operator component.

## Acceptance checks

1. `make day0 install namespaces` - `oc get networkpolicy -n zuno-aap`
   shows `zuno-default-deny-other-namespaces`.
2. `make day1 install aap` - `oc get applications.argoproj.io -n
   openshift-gitops zuno-aap-d0 zuno-aap-d1` both Synced/Healthy;
   `oc get ansibleautomationplatform -n zuno-aap -o yaml` shows Ready
   conditions on Gateway/Controller/Hub/EDA.
3. `make day1 check aap` reports installed; a second `make day1 install
   aap` is a no-op (idempotency - there is no `day1_reconcile.yml`, so
   this role must tolerate a plain repeated `install`).
4. `python3 platform/docs/check_docs.py` exits 0.
5. `oc exec` into a Crunchy pod, `\l` shows database `aap` owned by
   `aapcontroller`.
6. Browser: AAP Gateway route reachable, admin login with
   `zuno/aap/admin` succeeds.
7. `make day1 uninstall aap` removes both Applications and the operator
   cleanly; a subsequent `make day1 install aap` succeeds again.

## Operator / human follow-up

1. Deploy the GitOps change, watch the four AAP sub-components come up
   (expect this to be one of the slowest Day 1 steps in the whole
   sequence).
2. Run the step-10 CRD inventory commands and record output verbatim in
   this file's State section.
3. Confirm the Keycloak `aap` client resolves via the file-vault SPI
   (check Keycloak pod logs for a vault-lookup failure on
   `zuno_aap__client__secret`).
4. Report the CRD inventory findings before anyone starts WP-073.

## Status updates

On repository merge but before live confirmation:

- WP-072 -> `Repo work merged, live verification pending`.
- ADR-0354 -> stays `Proposed` (no change until acceptance criteria pass).

After all live acceptance checks pass and the CRD inventory is recorded:

- WP-072 -> `Done`.
- ADR-0354 -> `Partially implemented` (component `aap` live; `aap-config`
  still pending WP-073).
- Update `docs/roadmap/implementation-roadmap.md` and
  `MEMORY.md` to describe the implemented state.
- Run `python3 platform/docs/check_docs.py` again.

## Rollback

If the install causes cluster-wide resource pressure or a regression:

1. `make day1 uninstall aap` (removes the Applications and the operator
   cleanly per the role's `uninstall.yml`).
2. Revert the Git commit if the chart/role itself is at fault.
3. Do not leave `zuno-aap`'s deny-all `NetworkPolicy` removed as a
   workaround - if connectivity debugging is needed, add a scoped,
   temporary `allowedFromNamespaces` entry instead of deleting the policy.

## Out of scope / deferred

- `aap-config` (Project/Job Template registration) - WP-073.
- `mcp-aap` (agent-facing audit tools) - WP-074/ADR-0355.
- AAP-side OIDC authenticator configuration - WP-073's CRD-inventory
  decision.
- Routing `make day0|d0`/`make day1|d1` execution through any AAP Job
  Template - ADR-0418 (v0.4), explicitly deferred.
- External/customer-managed AAP mode (ADR-0352's Tier framework) -
  future ADR once ADR-0352 itself lands.
