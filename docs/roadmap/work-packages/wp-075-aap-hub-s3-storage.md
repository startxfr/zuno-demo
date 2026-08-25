# WP-075: Move AAP Hub content storage from file (RWO EBS) to S3

- **State:** Code committed 2026-08-25, pending live rollout/verification.
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
`worker`) was the pod that got stranded this time. Rather than patch the
affinity gap for `api` too, the decision was to remove the failure class
entirely by moving Hub's storage backend to S3.

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
  old `file_storage_*` fields. The `worker.affinity.podAffinity` block
  (WP-072's partial fix) is now conditional on `storageType != s3` -
  vestigial once content/worker no longer share a PVC.
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

## Rollout (manual, not yet executed)

1. Create the S3 bucket + a dedicated bucket-scoped IAM user/access key
   out-of-band (no Terraform in this repo); fill the four
   `zuno_aap_hub_s3_*` vars into the real (gitignored) `ansible/confidential.yml`.
2. Run the ansible vault role to seed `zuno/aap/hub-s3`.
3. `make day1 uninstall aap` then `make day1 install aap` (full
   uninstall/reinstall, not an in-place reconcile - the existing instance
   is already stuck, and Controller/EDA/Gateway/MetricsService come down
   and back up together with Hub since they share one CR/Application).
4. Manually `oc delete pvc aap-hub-file-storage -n zuno-aap` once the
   reinstalled Hub is confirmed healthy against S3 - a deliberate one-off
   cleanup command, not codified into ansible/gitops.
5. Verify per the checklist below.

## Verification checklist

- `oc get pods -n zuno-aap` - all `aap-*` pods `Running`/`Ready`.
- `oc get externalsecret aap-hub-s3-credentials -n zuno-aap` -
  `SecretSynced`/`Ready: True`, all four `s3-*` keys populated.
- Hub's migration init container completes (not stuck in
  `PodInitializing`/`CrashLoopBackOff`).
- Hub actually serves content against S3 through its web UI/route, not
  just green pod status.
