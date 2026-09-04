# Platform Prerequisites

What must be true, and what must be decided, before the first
`make day0|d0 install` on a new cluster. Everything a Day 0/1/2 component
installs is *not* here — that is the automation's job (ADR-0056).

`make day0|d0 check` now verifies most of this and reports what is missing as
findings, and `make day0|d0 install` refuses to start when any of them would
fail or destroy something (WP-130). Run the check first; it applies nothing.

## 1. The cluster

An existing OpenShift 4.22 AWS IPI cluster, cluster-admin access, and:

- **Exactly one StorageClass annotated `storageclass.kubernetes.io/is-default-class=true`.**
  Five applies read it. PVC `storageClassName` is immutable once bound, so the
  automation refuses to guess — annotate one, or set `zuno_cluster_storage_class`.
  PostgreSQL provisions an HA cluster (1 primary + 2 replicas plus PgBouncer),
  so size the backing storage for that rather than for a single instance.
- **Installer-created worker MachineSets, one per availability zone the GPU
  fleet declares.** The AMI, security group and per-AZ subnet names are read
  from them rather than derived from a naming pattern, because the installer's
  naming has changed across OCP versions. A declared zone with no installer
  MachineSet is refused rather than guessed — inventing a subnet name renders a
  MachineSet AWS rejects at first boot, hours later. The zones and instance
  types themselves are fleet design: edit
  `gitops/charts/machines/values.yaml`'s `machineSet.list` as a reviewed change.
- **`Ingress.config.openshift.io/cluster` readable, with an apps wildcard
  domain.** Every Route, the acceptance gate's URLs and the ACME certificates
  derive from it, and the cluster's short name is derived from it too. A domain
  not starting with `apps.` is legal but changes the API-server SAN
  cert-manager renders — the check reports it.
- GPU nodes for the served models, if any model is to run locally.

## 2. `ansible/confidential.yml`

Copy `ansible/confidential.example.yml` to `ansible/confidential.yml` and fill
in what this cluster needs. **That example file is the authority** — it carries
20 blocks with per-variable prose, most of them optional, and fields left as
`xxxxxx` are treated as not configured. The `vault` role fails fast without the
file; it is gitignored and re-read on every run.

Two families are optional in the sense that nothing fails, and worth naming
because their absence degrades the platform *silently*:

- `zuno_mariadb_backup_s3_*` (five keys) — unset means `backups.s3.enabled`
  stays false, the ExternalSecret is never rendered, and **no MariaDB backup
  schedule exists at all**. This cluster ran that way unnoticed until
  2026-09-02.
- `zuno_aws_route53_access_key_id` / `_secret_access_key` — the IAM credentials
  that *write* the DNS-01 records. Without them no Let's Encrypt certificate
  ever issues, while every other check still passes. They must be scoped to the
  hosted zone `zuno_certmanager_route53_hosted_zone_id` names, or DNS-01 gets
  `AccessDenied` and nothing else does.

## 3. Decisions to make before Day 0

These are not values to look up; they are choices, and the automation
deliberately will not make them.

- **The OpenShift AI version.** The install refuses to approve an InstallPlan
  whose CSV differs from the pin, because auto-approving whatever a catalog
  publishes is how a platform stops being reproducible. A cluster provisioned
  later than the pin will legitimately be offered a different build.
  `make day1|d1 check openshift-ai` compares the pin against the channel head
  and names the exact value to set as `zuno_openshift_ai_version`.
- **Where this cluster sits in the ACME rollout.** The chart defaults are the
  safe start — ACME off, staging issuer, both consumers off — and
  `ansible/confidential.example.yml` documents the four variables that walk
  ADR-0211's staged rollout in order. Do not skip the staging rehearsal: Let's
  Encrypt production has rate limits a broken DNS-01 loop will exhaust, and the
  consumer flips point the default router certificate and the API server's named
  certificates at Secrets that must already exist.
- **This cluster's own S3 buckets.** The seven buckets are not yet namespaced by
  cluster (ADR-0546, executed by WP-131). Until that lands, a second cluster
  reusing another's `confidential.yml` writes its RAG corpus, database backups,
  traces and MLflow artifacts into the *first* cluster's buckets. Provision a
  separate set and repoint every bucket variable;
  `zuno_s3_bucket_owner_cluster` makes `make d0 check` refuse the install if
  this was forgotten.

## 4. Then

```bash
oc login https://api.mycluster.com:6443 --token=<cluster-admin token>
ansible-galaxy collection install -r ansible/requirements.yml
make d0 check      # applies nothing; reports everything above
make d0 install
```

See [installation.md](installation.md) for the full Day 0–3 sequence and verb
set.
