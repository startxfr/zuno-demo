# mariadb

Applies the `gitops/apps/mariadb` ArgoCD Applications, whose chart
(`gitops/charts/mariadb`) installs the MariaDB Enterprise Operator (OLM
`Subscription`, package `mariadb-enterprise-operator`, `certified-operators`
catalog) and a single-node `MariaDB` CR (`enterprise.mariadb.com/v1alpha1`)
with a Vault-backed root password, plus (once real S3 credentials exist) a
scheduled `PhysicalBackup`. Ordered right after `postgresql` in
`day0_components` - the other data-tier operator sharing the `zuno-data`
namespace (already created by the `namespaces` role).

- `precheck.yml` - state detection, never fails: reports whether the
  `zuno-mariadb-d0`/`zuno-mariadb-d1` Applications and the `mariadb`
  `MariaDB` CR are actually Synced+Healthy/Ready, setting
  `mariadb_state_installed` and a line in the shared `/tmp` state report.
- `install.yml` - looks up the `mariadb-enterprise-operator`
  `PackageManifest` directly by name (ADR-0048: channel/catalog are still
  discovered from the live cluster, not hardcoded, same as
  `ansible/roles/jobset`), preferring a `stable` channel and falling back
  to `defaultChannel`, then applies `gitops/apps/mariadb/application-d0.yaml`
  with that selection injected via `gitops_app_extra_helm_values`. Once
  `-d0` is Synced+Healthy, soft-reads `ansible/confidential.yml` for
  `zuno_mariadb_backup_s3_{bucket,endpoint,region,access_key_id,secret_access_key}`
  (same optional shape as `ansible/roles/postgresql`'s S3 repo2) and applies
  `application-d1.yaml`, then waits for the `MariaDB` CR to report Ready.

## Namespace and OperatorGroup

Unlike most other Day 0 operators in this repo (`jobset`/`lws`/`kueue`,
each with their own dedicated namespace), `mariadb` is subscribed straight
into the pre-existing `zuno-data` namespace with a namespace-scoped
`OperatorGroup` (`targetNamespaces: [zuno-data]`) rather than a dedicated
namespace or the shared `openshift-operators` global one `postgresql` uses.
This matches the manifest originally supplied for this component. **Not yet
verified against a live cluster's `PackageManifest` install modes** - if
`mariadb-enterprise-operator`'s CSV turns out to require `AllNamespaces`
only, `gitops/charts/mariadb/values.yaml`'s `operator.operatorGroup.target`
needs to become `"all-ns"` instead (see that file's comment, and
`gitops/charts/kueue/values.yaml` for the shape that would take).

## What's unverified against a real cluster

This environment has no network path to a real OpenShift cluster, so the
following were written from the MariaDB Enterprise Operator's general CRD
shape but not exercised end to end:

- The exact OLM package name/channel/catalog this cluster actually
  publishes the operator under (`install.yml` looks up
  `mariadb-enterprise-operator` by exact name - update
  `mariadb_package_name` if the real catalog uses a different one).
- Whether the namespace-scoped `OperatorGroup` (see above) is actually
  compatible with this operator's supported install modes.
- The `MariaDB` CR's ready-condition shape (`install.yml`/`precheck.yml`
  assume a `status.conditions[]` entry of `type: Ready`, the common
  kubebuilder convention) - confirm with
  `oc get mariadb mariadb -n zuno-data -o yaml` against the target cluster.
- The `PhysicalBackup` CR's `spec.storage.s3` field shape
  (`gitops/charts/mariadb/templates/physicalbackup.yaml`) - reconstructed
  from the manifest originally supplied for this component, not confirmed
  against the installed CRD.

Run `make d0 check mariadb` → `make d0 install mariadb` against the real
cluster and adjust any of the above that turns out to be wrong.

## Credentials

`ansible/roles/vault/tasks/install.yml` seeds `zuno/mariadb/root`
(auto-generated `password`, unless `zuno_admin_mariadb_root_password` is
set) and, only once `ansible/confidential.yml` provides real values,
`zuno/mariadb/s3` (`accessKeyId`/`secretAccessKey` - note the camelCase
property names, matching `gitops/charts/mariadb/templates/externalsecret-backup-s3.yaml`'s
`remoteRef.property`, unlike `postgresql`'s snake_case `access_key`/
`secret_key`).
