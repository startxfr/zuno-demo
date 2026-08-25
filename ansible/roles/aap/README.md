# Ansible role: aap

Applies the `gitops/apps/aap` ArgoCD Application pair (ADR-0354). The
`-d0` half installs the Ansible Automation Platform operator (OLM
`Subscription` + `OperatorGroup`, package `ansible-automation-platform-
operator`) into `zuno-aap` (a Day 0 namespace, `gitops/charts/namespaces` -
this role does not create it). The `-d1` half renders a single
`AnsibleAutomationPlatform` CR (`aap.ansible.com/v1alpha1`) provisioning
Gateway, Controller, Hub and EDA together, non-HA.

Runs in `day1_components`, immediately after `openshift_oauth`: by that
point PostgreSQL, Vault/External Secrets (Day 0) and Keycloak +
`openshift_oauth` (Day 1, earlier in the same list) are already
Synced+Healthy - all three are prerequisites (dedicated databases, Vault-
seeded credentials, the Keycloak OIDC client registered by
`ansible/roles/keycloak`).

## Operator package/channel discovery

Confirmed live against this repository's own cluster (`demo222`,
2026-08-24, WP-072's CRD-inventory checkpoint): the package is named
`ansible-automation-platform-operator`, default channel `stable-2.7`
(other published channels at the time: `stable-2.6`,
`stable-2.6-cluster-scoped`, `stable-2.7-cluster-scoped`), catalog
`redhat-operators`. `tasks/install.yml` still discovers channel/catalog
at runtime (ADR-0048) rather than hardcoding them, same pattern as every
other operator-backed role - this cluster's specific channel string is
recorded here for context, not relied on as a default.

`InstallModes`: `OwnNamespace`/`SingleNamespace`/`MultiNamespace` only,
**not** `AllNamespaces` - same reasoning as `keycloak`'s `rhbk-operator`,
subscribed into its own namespace (`zuno-aap`) with its own
`OperatorGroup` rather than the shared `openshift-operators` namespace.

## Per-component external database (not a single shared secret)

**Confirmed live via `oc explain` against the real CRD on 2026-08-24 -
this corrects ADR-0354's original open question in clause 5.** The
unified `AnsibleAutomationPlatform` CR does **not** take one external-
database secret for the whole platform; each sub-component owns its own
database configuration, with two different field-naming conventions:

| Component | CR path | Field name |
|---|---|---|
| Gateway | `spec.database` | `database_secret` |
| Controller | `spec.controller` | `postgres_configuration_secret` |
| Hub | `spec.hub` | `postgres_configuration_secret` |
| EDA | `spec.eda.database` | `database_secret` |

Each of the four gets its own dedicated Crunchy database/role on the
shared `zuno-postgresql` cluster (`gitops/charts/postgresql`), following
the exact ADR-0315 pattern already used for `keycloak`: `aap` (owner
`aapgateway`), `aapcontroller`, `aaphub`, `aapeda`. See
`gitops/charts/postgresql/README.md` and this chart's
`templates/externalsecret-*.yaml` files.

**Secret key contract - not verified against a live reconcile.** No
`alm-examples` were published on this channel and the CRD's OpenAPI
schema carries no field-level detail beyond the name, so the expected
key set (`host`, `port`, `database`, `username`, `password`, `sslmode`,
`type`) follows the documented upstream awx-operator/AAP-operator
external-database Secret convention, not a live-confirmed one. If a
component's postgres connection fails after `make d1 install aap`,
check that pod's logs for the exact missing/unexpected key before
assuming the chart is otherwise broken.

## Storage: Hub moved to S3 (WP-075, supersedes this section's original call)

Originally: `automationhub.spec.file_storage_access_mode` accepts
`ReadWriteOnce` (confirmed live via `oc explain` - not only
`ReadWriteMany`, which this repository's storage classes don't provide),
so Hub was configured `storage_type: file` with
`file_storage_access_mode: ReadWriteOnce`, avoiding both an RWX storage
class this cluster doesn't have and an external S3 dependency.

That RWO choice turned out fragile: `aap-hub-api`/`aap-hub-content`/
`aap-hub-worker` all mount the same RWO EBS PVC, which only attaches to
one node at a time. WP-072's `podAffinity` fix forced `worker` onto
`content`'s node, but never covered `api` - when `api` landed on a
different node (confirmed live 2026-08-25), it deadlocked indefinitely
on `FailedAttachVolume`/`Multi-Attach`, blocking Hub's migrations and
cascading into CrashLoopBackOff everywhere downstream. See WP-075: Hub
now uses `storage_type: s3` (`gitops/charts/aap/values.yaml`'s `hub.s3`
block), removing the shared-PVC failure class entirely.

## Non-HA sizing

Every sub-component's replica knobs are set to their minimum (confirmed
field names live): `spec.api.replicas` (Gateway), `spec.controller.
replicas`/`web_replicas`/`task_replicas` (Controller), `spec.hub.{api,
web,worker}.replicas` (Hub), `spec.eda.{api,default_worker,
activation_worker,ui}.replicas` (EDA - `default_worker`/
`activation_worker` default to 2, trimmed to 1 here). Resource
requests/limits are left at the operator's own defaults - unlike other
charts in this repository that hand-tune CPU/memory from measured usage,
no live measurement exists yet for AAP; trim `values.yaml`'s
`resourceRequirements` blocks once real usage is observed.

## Red Hat subscription activation (`zuno_aap_enabled`)

When `ansible/confidential.yml` sets `zuno_aap_enabled: true` (plus
`zuno_aap_rhn_username`/`zuno_aap_rhn_password`, see
`ansible/confidential.example.yml`), `tasks/install.yml` ends by
attaching that Red Hat account's AAP entitlement to the freshly started
platform - the Gateway/Controller "Subscription" screen equivalent, fully
automated.

Confirmed live against this cluster's Gateway (2026-08-25):

- The endpoint is `/api/controller/v2/config/` (the AWX/Tower-inherited
  path, proxied under the 2.5+ unified gateway's `/api/controller/`
  prefix; `GET /api/` lists all five sub-APIs).
- On AAP 2.7 a **single** authenticated `POST` with
  `subscriptions_username`/`subscriptions_password` validates the account
  against Red Hat and attaches its matching entitlement in one call
  (HTTP 200, returns the applied `license_info`) - not the older Tower
  two-step list-pools-then-attach-`pool_id` flow.
- A fresh install comes up with an ambient "Developer Subscription for
  Individuals" already attached and compliant (inherited from the
  cluster's own Red Hat account/pull secret, without any action from
  this role). The task's idempotency is therefore keyed on *which*
  subscription is attached (`subscription_id` before vs after), not on
  "some valid subscription exists" - the configured account always wins.

Failure behavior is deliberately **blocking**: bad RHN credentials,
placeholder values with the flag enabled, or an unreachable Gateway API
fail the whole `make d1 install aap` - `aap` precedes
`connectivity-link`/`lws`/`jobset`/`kueue`/`openshift-ai`/
`aiagent-operator` in Day 1, so a subscription problem stops the sequence
until resolved (explicit user decision over warn-and-continue). Admin
authentication reuses the `aap-admin` Kubernetes Secret directly (the
same one the CR's `admin_password_secret` consumes); the ArgoCD
Synced/Healthy gate on `zuno-aap-d1` is NOT trusted as "Gateway API up"
(no custom health check exists for the CRD - observed Healthy while the
gateway pod was still crash-looping), so the task polls `GET /api/`
first.

## Deferred to WP-073, not this role

- **`spec.bundle_cacert_secret`** (confirmed live: a Secret naming the
  CA bundle the Gateway trusts for its own outbound HTTPS calls) is left
  unset. It would matter once a Keycloak OIDC authenticator depends on
  verifying a Vault-PKI-signed Keycloak Route; reconciling the CR itself
  needs no Keycloak trust. `ansible/tasks/sync_keycloak_serving_ca.yml`
  produces a ConfigMap, not a Secret, so wiring this field also needs a
  ConfigMap-to-Secret conversion step this role deliberately does not add
  yet - see WP-073.
- The AAP-side Keycloak OIDC authenticator itself (Gateway API/UI
  configuration in AAP 2.7, not a CR field) - WP-073's own CRD-inventory
  decision (Project/JobTemplate CRDs vs `infra.aap_configuration`) covers
  the same ground.
- The `zuno-demo` Project and `zuno-day0-check` Job Template - WP-073.

## What's unverified against a full live reconcile

WP-072's CRD inventory (2026-08-24) confirmed field *names* by
subscribing the operator and running `oc explain` against the real CRDs
on `demo222`, then deliberately tore that subscription back down before
ever creating an `AnsibleAutomationPlatform` CR - the full
Gateway+Controller+Hub+EDA install is a heavy, deliberate action, done
once via `make d1 install aap` rather than as a side effect of schema
discovery. So the following are informed by the confirmed field names
above but not proven end to end:

- The exact key set each `postgres_configuration_secret`/
  `database_secret` Secret needs (see "Per-component external database"
  above).
- Whether `file_storage_access_mode: ReadWriteOnce` is fully supported
  in practice for Hub's actual content-storage workload, or only
  accepted by the schema.
- Whether the trimmed non-HA replica counts leave every sub-component
  actually `Ready`, or whether some minimum (e.g. EDA's workers) turns
  out to require more than 1 in practice.

Run `make d1 check aap` → `make d1 install aap` against the real cluster
and adjust any of the above that turns out to be wrong.
