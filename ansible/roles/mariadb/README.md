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
  directly by name (ADR-0048: channel/catalog are still discovered from
  the live cluster, not hardcoded, same as `ansible/roles/jobset`),
  preferring a `stable` channel and falling back to `defaultChannel` (this
  package only ever publishes `alpha`, so it always falls back), then
  applies `gitops/apps/mariadb/application-d0.yaml` with that selection
  injected via `gitops_app_extra_helm_values`. Once `-d0` is
  Synced+Healthy, soft-reads `ansible/confidential.yml` for
  `zuno_mariadb_backup_s3_{bucket,endpoint,region,access_key_id,secret_access_key}`
  (same optional shape as `ansible/roles/postgresql`'s S3 repo2) and
  applies `application-d1.yaml`, then waits for the `mariadb-operator`
  controller-manager Deployment to become Available (started only once the
  `MariadbOperator` activation CR that Application renders is reconciled -
  see "Why an activation CR" below) before waiting for the `MariaDB` CR to
  report Ready.

## Why not the Enterprise operator

This component originally targeted the certified `mariadb-enterprise-operator`
listing, matching a manifest supplied for this component. Deployed against
a live cluster, its controller-manager pod failed `ImagePullBackOff`:
its CSV's `containerImage` is `docker.mariadb.com/mariadb-enterprise-operator@...`
- MariaDB Corporation's own authenticated registry - and the CSV carries
`operators.openshift.io/valid-subscription: ["MariaDB Enterprise"]`, i.e.
it requires a paid MariaDB Enterprise credential this cluster doesn't have.
The `mariadb-operator` community listing is the same upstream project
(confirmed field-for-field identical `MariaDB`/`PhysicalBackup` CRD shapes
against both packages' `alm-examples`, just under `k8s.mariadb.com` instead
of `enterprise.mariadb.com`), with a public image
(`ghcr.io/mariadb-operator/mariadb-operator-helm`) and no subscription
requirement.

## Namespace and OperatorGroup

Unlike `jobset`/`lws`/`kueue` (each with their own dedicated namespace) or
the Enterprise-operator version of this component (which used a dedicated,
namespace-scoped `OperatorGroup` in `zuno-data`), `mariadb-operator` is
subscribed into the shared `openshift-operators` namespace with no
dedicated `OperatorGroup` - same Pattern B shape as `ansible/roles/postgresql`.
Confirmed against a live cluster's `PackageManifest`: this package's CSV
supports every install mode (`OwnNamespace`/`SingleNamespace`/
`MultiNamespace`/`AllNamespaces` all `true`), so `AllNamespaces` via the
shared namespace's default global `OperatorGroup` is safe, and avoids the
`MultipleOperatorGroupsFound` conflict a dedicated OperatorGroup in
`zuno-data` previously hit on a live cluster (an unrelated, pre-existing
stray `OperatorGroup` there, most likely left over from an earlier manual
console install attempt - not something this role manages, delete manually
with `oc delete operatorgroup <name> -n zuno-data` once confirmed unneeded).

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

## What's unverified against a real cluster

This environment has no network path to a real OpenShift cluster, so the
following were written from `mariadb-operator`'s general CRD/CSV shape but
not exercised end to end:

- The `mariadb-operator` controller-manager Deployment's exact name once
  started by the `MariadbOperator` activation CR (`install.yml` assumes
  `mariadb-operator` in `zuno-data` - confirm with `oc get deployment -n
  zuno-data -l app.kubernetes.io/name=mariadb-operator` against the target
  cluster and adjust if the embedded Helm chart derives a different name).
- The `MariaDB` CR's ready-condition shape (`install.yml`/`precheck.yml`
  assume a `status.conditions[]` entry of `type: Ready`, the common
  kubebuilder convention) - confirm with
  `oc get mariadb mariadb -n zuno-data -o yaml` against the target cluster.
- The `PhysicalBackup` CR's `spec.storage.s3` field shape
  (`gitops/charts/mariadb/templates/physicalbackup.yaml`) - confirmed
  field-for-field against the community operator's own `alm-examples`, but
  not against a live `PhysicalBackup` reconciliation.

Run `make d0 check mariadb` → `make d0 install mariadb` against the real
cluster and adjust any of the above that turns out to be wrong.

## Credentials

`ansible/roles/vault/tasks/install.yml` seeds `zuno/mariadb/root`
(auto-generated `password`, unless `zuno_admin_mariadb_root_password` is
set) and, only once `ansible/confidential.yml` provides real values,
`zuno/mariadb/s3` (`accessKeyId`/`secretAccessKey` - note the camelCase
property names, matching `gitops/charts/mariadb/templates/externalsecret-backup-s3.yaml`'s
`remoteRef.property`, unlike `postgresql`'s snake_case `access_key`/
`secret_key`). No registry/image-pull credentials are needed - unlike the
Enterprise operator, `mariadb-operator`'s image is public.
