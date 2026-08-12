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

## Confirmed against a live cluster (api.demo222.startx.fr, 2026-08-12)

- The `mariadb-operator` controller-manager Deployment is indeed named
  `mariadb-operator` in `zuno-data` (`install.yml`'s wait step). The
  `MariadbOperator` activation CR also brings up two sibling Deployments,
  `mariadb-operator-cert-controller` and `mariadb-operator-webhook`, not
  waited on directly - `MariaDB` CR reconciliation itself blocks (via a
  validating webhook call) until the webhook Deployment has real endpoints,
  so `install.yml`'s existing "wait for controller-manager Available, then
  wait for MariaDB Ready" order is sufficient; the webhook race resolves on
  its own within the `MariaDB` CR wait's retry budget.
- The `MariaDB` CR does report a `status.conditions[]` entry of
  `type: Ready` (`status: "True"` once healthy) - the
  `install.yml`/`precheck.yml` assumption was correct.
- `status.currentPrimary`/`status.tls.*` are also populated
  (`mariadb-0` as primary, an auto-generated CA/server/client cert chain) -
  not currently read by this role, but available if needed later.
- The `PhysicalBackup` CR's `spec.storage.s3` shape has *not* been
  exercised live yet (no S3 credentials configured in
  `ansible/confidential.yml` on this cluster) - still only confirmed
  against the community operator's `alm-examples`.

## Vault must be (re-)seeded before the first install

`ExternalSecret`s only resolve once their Vault path actually exists.
`zuno/mariadb/root` is seeded by `ansible/roles/vault/tasks/install.yml`,
which only runs via `make d0 install vault` (or `all`) - a targeted
`make d0 install mariadb` on a cluster where `vault` hasn't been re-run
since this component was added will hang retrying
`gitops | wait for zuno-mariadb-d1 to become Synced and Healthy` forever,
because the `mariadb-root-password` `ExternalSecret` can never sync. Note
that **`vault`'s per-secret password generation is not idempotent**
(`lookup('ansible.builtin.password', '/dev/null', ...)` can't persist/read
back a prior value), so a full `make d0 install vault` re-run regenerates
*every* secret it seeds, not just this component's - risky against a
cluster with other components already relying on their current values. To
seed just the new path without touching anything else, run a scoped
`vault kv put zuno/mariadb/root password=<random>` directly against the
`zuno-vault-0` pod instead.

Separately: if ArgoCD's automated sync already exhausted its retry budget
(5 attempts) against a real failure, fixing the underlying cause (e.g. the
Vault seed above) is not by itself enough to make it retry - a plain
`argocd.argoproj.io/refresh=hard` annotation alone did not trigger a new
sync attempt either. A fresh sync operation had to be triggered explicitly
(`oc patch application <name> -n openshift-gitops --type merge -p
'{"operation":{"sync":{"revision":"HEAD","prune":true}}}'`, what the
`argocd` CLI's `app sync` does under the hood) before `-d1` proceeded.

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
