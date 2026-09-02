# mariadb

Applies the `gitops/apps/mariadb` ArgoCD Applications, whose chart
(`gitops/charts/mariadb`) installs the open-source `mariadb-operator` (OLM
`Subscription`, package `mariadb-operator`, `community-operators` catalog,
Apache-2.0 - **not** the paid `mariadb-enterprise-operator` certified
listing, see "Why not the Enterprise operator" below), its `MariadbOperator`
activation CR, and a single-node `MariaDB` CR (`k8s.mariadb.com/v1alpha1`)
with a Vault-backed root password, plus (once real S3 credentials exist) a
scheduled `PhysicalBackup`. Ordered right after `postgresql` in
`day0_components` - the other data-tier operator sharing the `zuno-data`
namespace (already created by the `namespaces` role).

- `precheck.yml` - state detection, never fails: reports whether the
  `zuno-mariadb-d0`/`zuno-mariadb-d1` Applications and the `mariadb`
  `MariaDB` CR are actually Synced+Healthy/Ready, setting
  `mariadb_state_installed` and a line in the shared `/tmp` state report.
- `install.yml` - looks up the `mariadb-operator` `PackageManifest`
  directly by name (channel/catalog are discovered from the live
  cluster, not hardcoded, same as `ansible/roles/jobset`), preferring a
  `stable` channel and falling back to `defaultChannel` (this package
  only ever publishes `alpha`, so it always falls back), then applies
  `gitops/apps/mariadb/application-d0.yaml` with that selection injected
  via `gitops_app_extra_helm_values`. Once `-d0` is Synced+Healthy,
  soft-reads `ansible/confidential.yml` for
  `zuno_mariadb_backup_s3_{bucket,endpoint,region,access_key_id,secret_access_key}`
  (same optional shape as `ansible/roles/postgresql`'s S3 repo2) and
  applies `application-d1.yaml`, then waits for the `mariadb-operator`
  controller-manager Deployment to become Available (started only once the
  `MariadbOperator` activation CR that Application renders is reconciled -
  see "Why an activation CR" below) before waiting for the `MariaDB` CR to
  report Ready.

## Why not the Enterprise operator

This component uses the open-source `mariadb-operator` community listing,
not the paid `mariadb-enterprise-operator` certified listing: its CSV
requires `operators.openshift.io/valid-subscription: ["MariaDB
Enterprise"]` and pulls from MariaDB Corporation's own authenticated
registry (`docker.mariadb.com/mariadb-enterprise-operator@...`), which
fails `ImagePullBackOff` without a paid credential. The community
listing is the same upstream project - `MariaDB`/`PhysicalBackup` CRD
shapes are identical between both packages' `alm-examples`, just under
`k8s.mariadb.com` instead of `enterprise.mariadb.com` - with a public
image (`ghcr.io/mariadb-operator/mariadb-operator-helm`) and no
subscription requirement.

## Namespace and OperatorGroup

Unlike `jobset`/`lws`/`kueue` (each with their own dedicated namespace),
`mariadb-operator` is subscribed into the shared `openshift-operators`
namespace with no dedicated `OperatorGroup` - same Pattern B shape as
`ansible/roles/postgresql`. This package's CSV supports every install
mode (`OwnNamespace`/`SingleNamespace`/`MultiNamespace`/`AllNamespaces`
all `true`), so `AllNamespaces` via the shared namespace's default
global `OperatorGroup` is safe. If a stray `OperatorGroup` already
exists in `zuno-data` (e.g. left over from a manual console install), it
can conflict with `MultipleOperatorGroupsFound` - not something this
role manages, delete it manually with `oc delete operatorgroup <name>
-n zuno-data` once confirmed unneeded.

## Why an activation CR

`mariadb-operator` ships as an operator-sdk **Helm-operator**: its CSV's
own Deployment is a thin controller that only runs its embedded Helm chart
- and so only starts the real `mariadb-operator` controller-manager that
reconciles `MariaDB` CRs - once a `MariadbOperator` CR
(`helm.mariadb.mmontes.io/v1alpha1`) exists. `-d1`'s chart renders this CR
(`templates/mariadboperator.yaml`, sync-wave ordered ahead of the `MariaDB`
CR) alongside the actual `MariaDB` CR - same "operator needs an
activation/config singleton CR" shape `gitops/charts/jobset`'s
`JobSetOperator` and `gitops/charts/kueue`'s `Kueue` CR already use in this
repo.

## Operand status once installed

- The `mariadb-operator` controller-manager Deployment is named
  `mariadb-operator` in `zuno-data`. The `MariadbOperator` activation CR
  also brings up `mariadb-operator-cert-controller` and
  `mariadb-operator-webhook` - `MariaDB` CR reconciliation blocks on the
  webhook via a validating webhook call, so `install.yml`'s "wait for
  controller-manager Available, then wait for MariaDB Ready" order is
  sufficient.
- The `MariaDB` CR reports `status.conditions[]` with `type: Ready`
  (`status: "True"` once healthy), plus `status.currentPrimary`/
  `status.tls.*` (`mariadb-0` as primary, an auto-generated
  CA/server/client cert chain) - not currently read by this role.
- The `PhysicalBackup` CR's `spec.storage.s3` shape is unexercised
  without real S3 credentials in `ansible/confidential.yml`.

## Vault must be (re-)seeded before the first install

`ExternalSecret`s only resolve once their Vault path actually exists.
`zuno/mariadb/root` is seeded by `ansible/roles/vault/tasks/install.yml`,
which only runs via `make d0 install vault` (or `all`) - a targeted
`make d0 install mariadb` on a cluster where `vault` hasn't been re-run
since this component was added will hang retrying
`gitops | wait for zuno-mariadb-d1 to become Synced and Healthy` forever,
because the `mariadb-root-password` `ExternalSecret` can never sync. The fix
is simply to re-run `make d0 install vault`.

**Corrected 2026-09-02 (WP-118 step 4).** This paragraph used to say the
opposite - that `vault`'s per-secret password generation is not idempotent
(`lookup('ansible.builtin.password', '/dev/null', ...)` can't read back a
prior value), so a re-run regenerates *every* secret it seeds, and that you
should therefore `vault kv put` the single path by hand instead. That was
true when written on 2026-08-12, and stopped being true the next day:
ADR-0345 introduced `ansible/tasks/vault_seed_if_missing.yml`, a check-first
guard that all 44 generated Vault paths now go through, after an unguarded
re-run rotated `zuno/maas/postgresql-app` and CrashLoopBackOff'd `maas-api`
live. A re-run now writes only the paths that are *missing*, which makes it
the correct way to add a newly-introduced one. The stale warning survived a
year of re-reads and actively discouraged a safe operation.

Real residual risks of a `make d0 install vault` re-run, which are not about
secret rotation: `ansible/roles/vault/tasks/install.yml:335-341` runs
`git add` + `git commit` in the operator's working tree when the live Transit
public key differs from `agents/zuno-platform-signer.pub` - on a repository
several sessions share, that is the one to watch. It also deletes and
recreates the `vault-unseal-configure` Job on every run (idempotent, but it
re-runs the whole PKI/policy configuration), and hard-fails if
`ansible/confidential.yml` is absent.

Separately: if ArgoCD's automated sync already exhausted its retry
budget (5 attempts), a plain `argocd.argoproj.io/refresh=hard`
annotation does not by itself trigger a new sync attempt - fixing the
underlying cause (e.g. the Vault seed above) needs a fresh sync
operation triggered explicitly (`oc patch application <name> -n
openshift-gitops --type merge -p
'{"operation":{"sync":{"revision":"HEAD","prune":true}}}'`, what the
`argocd` CLI's `app sync` does under the hood).

Run `make d0 check mariadb` → `make d0 install mariadb` again after any of
the above to pick up wherever it left off.

## Credentials

`ansible/roles/vault/tasks/install.yml` seeds `zuno/mariadb/root`
(auto-generated `password`, unless `zuno_admin_mariadb_root_password` is
set) and, only once `ansible/confidential.yml` provides real values,
`zuno/mariadb/s3` (`accessKeyId`/`secretAccessKey` - note the camelCase
property names, matching `gitops/charts/mariadb/templates/externalsecret-backup-s3.yaml`'s
`remoteRef.property`, unlike `postgresql`'s snake_case `access_key`/
`secret_key`). No registry/image-pull credentials are needed - unlike the
Enterprise operator, `mariadb-operator`'s image is public.
