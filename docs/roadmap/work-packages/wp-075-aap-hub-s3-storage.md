# WP-075: Move AAP Hub content storage from file (RWO EBS) to S3

- **State:** Done (live-verified 2026-08-25).
- **Supersedes:** WP-072's storage decision ("Hub is configured
  `storage_type: file` ... avoiding ... an external S3 dependency this
  repository doesn't otherwise carry in-cluster") and the matching note in
  `ansible/roles/aap/README.md`'s "Storage: Hub stays ReadWriteOnce, no S3
  dependency" section.
- **Depends on:** WP-072 (`aap` chart/role already live).

## Why

Live diagnosis of `zuno-aap` on 2026-08-25 found `aap-hub-api`,
`aap-hub-content`, `aap-hub-worker` deadlocked: all three mount the same
`ReadWriteOnce` EBS PVC (`aap-hub-file-storage`, gp3-csi), and EBS RWO
volumes attach to only one node at a time. `aap-hub-content`/
`aap-hub-worker` landed on the same node and shared the PVC fine, but
`aap-hub-api` landed on a different node and could never attach it - its
`run-migrations` init container was stuck in `PodInitializing`
indefinitely, so migrations never ran, cascading into `CrashLoopBackOff`
on content/worker and constant readiness/liveness failures on both
`aap-hub-web` replicas.

WP-072 had already added a `podAffinity` forcing `aap-hub-worker` onto
whichever node `aap-hub-content` lands on, precisely to avoid this - but
that affinity was never applied to `aap-hub-api`, which is why `api` (not
`worker`) was the pod that got stranded this time.

**Important correction found during live verification**: moving Django's
storage backend to S3 does **not** remove the shared RWO PVC. The
automation-hub-operator provisions and mounts `aap-hub-file-storage` into
`api`/`content`/`worker` as local scratch space unconditionally,
regardless of `storage_type` - confirmed live by inspecting the
`aap-hub-api` Deployment's volumes after the S3 migration completed. So
S3 alone does not eliminate the Multi-Attach failure class; the actual
fix is extending WP-072's `podAffinity` to cover `api` as well as
`worker`, applied unconditionally in both `file` and `s3` mode. This WP
does both: moves Hub's actual content storage to S3 (the original goal)
*and* fixes the affinity gap that caused the live incident.

## What changed

Confirmed live (`oc explain automationhub.spec` against the cluster): the
underlying `AutomationHub` CR (`automationhub.ansible.com/v1beta1`)
supports `storage_type: S3` + `object_storage_s3_secret: <secret-name>`.
Secret key shape (`s3-access-key-id`/`s3-secret-access-key`/
`s3-bucket-name`/`s3-region`) confirmed via Pulp Operator docs (the
automation-hub-operator is pulp-operator-based).

- `gitops/charts/aap/values.yaml`: `hub.storageType` flipped to `s3`,
  new `hub.s3` block (secret name + ExternalSecret field mapping).
  `file_storage_access_mode`/`file_storage_size` kept for rollback.
- `gitops/charts/aap/templates/aap.yaml`: `spec.hub` now branches on
  `storageType` - `s3` sets `object_storage_s3_secret`, `file` keeps the
  old `file_storage_*` fields. The `podAffinity` (pinning to
  `content-server`'s node) is now applied **unconditionally to both `api`
  and `worker`** - not gated on storage type (that gate was wrong, see
  above), and now also covers `api`, closing the actual gap that caused
  the live incident.
- `gitops/charts/aap/templates/externalsecret-hub-s3.yaml` (new): pulls
  all four fields (bucket name, region, access key id, secret access
  key) from Vault (`zuno/aap/hub-s3`) and materializes the
  `aap-hub-s3-credentials` Secret with the exact keys the operator
  expects. Unlike this repo's other S3 buckets (`rag/s3`,
  `sxa-corpus/s3`, which keep bucket/region as plain committed chart
  values), bucket name and region are also sourced from Vault here - by
  explicit request, not architectural necessity.
- `ansible/confidential.example.yml` / `ansible/roles/vault/tasks/install.yml`:
  new `zuno_aap_hub_s3_bucket_name`/`_region`/`_access_key_id`/
  `_secret_access_key` vars, seeded to Vault as a single gated task.

## Rollout as actually executed

The originally-planned full `uninstall`/`install` cycle uncovered a
second, unrelated live bug that's worth recording for future reinstalls
of this CR:

1. Bucket (`zuno-aap-hub`, `eu-west-2`) + dedicated IAM user created
   manually; `ansible/confidential.yml` filled in; `zuno/aap/hub-s3`
   seeded to Vault via `make d0 install vault`.
2. `make d1 uninstall aap` + `make d1 install aap` were run **before**
   this WP's chart changes were committed/pushed - the reinstall
   deployed the old `file`-storage config from git `main`, which is
   otherwise a mistake to avoid (verify `git log` matches the ArgoCD
   Application's synced revision before relying on a reinstall to pick
   up local changes).
3. **Gateway DB/encryption-key bug** (unrelated to this WP, discovered
   while reinstalling): the umbrella CR owns
   `aap-db-fields-encryption-secret` (Gateway's Fernet key), so deleting
   the CR during uninstall cascaded via Kubernetes ownerReference
   garbage collection and deleted it too. Reinstall generated a **new**
   random key, but Gateway's external Postgres database (`aap`, role
   `aapgateway`) wasn't touched by uninstall and still had rows
   encrypted under the old, now-gone key -> `cryptography.fernet.InvalidToken`
   during migration. Fix: drop + recreate the `aap` database (`DROP
   DATABASE aap; CREATE DATABASE aap OWNER aapgateway;` - zero
   connections, safe, nothing of value in default preferences data).
4. **Same bug recurred on EDA**: `aap-eda-db-fields-encryption-secret` is
   owned by the `EDA` CR, same regeneration-on-reinstall problem, same
   `InvalidToken` on EDA's `create_initial_data` init container. Fix
   needed one extra step versus Gateway: EDA's `aap-eda` database has
   *active* connections from `default-worker`/`activation-worker`/
   `event-stream` that keep reconnecting, so a plain `DROP DATABASE`
   raced with reconnects - `DROP DATABASE "aap-eda" WITH (FORCE)` (PG13+)
   settled it atomically. The recreated database also needed
   `GRANT USAGE, CREATE ON SCHEMA public TO aapeda;` (PG15+ no longer
   grants schema-level `CREATE` to non-owners by default) - copied from
   the working `aap-controller` database's schema ACL
   (`aapcontroller=UC/pg_database_owner` via `\dn+ public`) since EDA's
   database is owned by `postgres` with `aapeda` merely granted
   database-level privileges, not schema-level ones.
5. WP-075's actual chart changes were committed/pushed only after the
   above; ArgoCD (`automated: {prune: true, selfHeal: true}` on
   `zuno-aap-d1`) picked them up via `argocd.argoproj.io/refresh: hard`
   + auto-sync, no second uninstall/reinstall needed - the operator
   reconfigured the already-running Hub in place once the CR's
   `spec.hub.storage_type` changed to `s3`.
6. `oc delete pvc aap-hub-file-storage -n zuno-aap` intentionally
   **not** run - see caveat above: the operator still actively mounts
   this PVC into api/content/worker even in S3 mode, so it isn't
   orphaned.

## Verification (live, 2026-08-25)

- All `zuno-aap` pods `Running`/`Ready`, including `aap-hub-api`/
  `-content`/`-worker`/`-web` on their new S3-backed ReplicaSets.
- `oc get externalsecret aap-hub-s3-credentials -n zuno-aap` ->
  `SecretSynced`/`Ready: True`.
- `aap-hub-server` Secret's `settings.py` confirmed:
  `STORAGES["default"]["BACKEND"] = "storages.backends.s3boto3.S3Boto3Storage"`,
  `AWS_STORAGE_BUCKET_NAME = "zuno-aap-hub"`, `AWS_S3_REGION_NAME = "eu-west-2"`.
- `https://aap.<domain>/api/` -> HTTP 200.
- `api`/`content`/`worker` all landed on the same node
  (`ip-10-18-16-201`) this time; the unconditional `podAffinity` now
  guarantees that regardless of scheduling luck.
