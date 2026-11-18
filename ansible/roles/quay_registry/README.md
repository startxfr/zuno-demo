# quay_registry

ADR-0612/WP-248. The internal Red Hat Quay in `zuno-registry`: operator (d0), `QuayRegistry` and a dedicated PGO
PostgreSQL 15 (d1), a config bundle Secret built here, blobs in the S3 bucket of `registry_bucket`.

- Prerequisite: `ansible-playbook ansible/playbooks/registry_bucket.yml -e registry_bucket_apply=true`, and
  `zuno_quay_s3_bucket` in `ansible/clusters/<cluster>.yml`.
- `make d2 install quay-registry` / `check` / `uninstall` (the bucket is never deleted).
- Clair runs the Red Hat updater set only (`zuno_quay_clair_updater_sets`); see ADR-0612 clause 4.
- Not yet rehearsed: the first run is a canary (ADR-0609) together with the S3 test.
