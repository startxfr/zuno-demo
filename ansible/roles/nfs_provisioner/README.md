# nfs_provisioner

Applies the `gitops/apps/nfs-provisioner` ArgoCD Application pair. Its chart
(`gitops/charts/nfs-provisioner`) installs the NFS Provisioner operator
(`nfs-provisioner-operator` from `community-operators`, channel `alpha`) into
the `nfs-provisioner` namespace with an `OwnNamespace` OperatorGroup, and an
`NFSProvisioner` operand that runs an NFS server on a `gp3-csi` volume and
creates the `nfs` StorageClass (provisioner `example.com/nfs`). A Day 1
component with `check`, `install` and `uninstall`, built like
`ansible/roles/jobset`.

## Why

`gitops/charts/unifai/values.yaml` sets `stack.sharedStorageClass: nfs`: the
UnifaiStack's shared volumes (`unifai-logging-volume`,
`unifai-multiagent-shared-storage`, `unifai-rag-shared-storage` in
`zuno-unifai`) are ReadWriteMany volumes of that class, and no OpenShift
cluster ships it. Until this role, the operator ran on demo333 without any
declaration, so a cluster rebuilt from the repository had no `nfs` class
(ADR-0608 clauses 1 and 2, WP-241 step 1). The UnifAI role now fails its
precheck, with the missing name, when the class does not exist.

## What each verb does

- `check` (`tasks/precheck.yml`): both Applications Synced and Healthy, the
  `NFSProvisioner` exists and the StorageClass exists. Never fails.
- `install` (`tasks/install.yml`): resolves the package and channel
  (ADR-0048), refuses a channel that does not serve the pinned CSV, applies
  `-d0` (Namespace, OperatorGroup, Subscription), approves only the pinned
  InstallPlan (`tasks/approve_installplan.yml`), waits for `-d0` to be
  Healthy, applies `-d1` (the `NFSProvisioner`) and waits for the StorageClass.
- `uninstall` (`tasks/uninstall.yml`): refuses while any PersistentVolumeClaim
  or PersistentVolume uses the StorageClass, because deleting the provisioner
  deletes the NFS server and its backing volume, and with it UnifAI's shared
  data. Then deletes `-d1`, the operator (`ansible/tasks/remove_operator.yml`)
  and `-d0`. The namespace stays.

Names, the pin and the class name are read from the chart's `values.yaml`
(`tasks/load_values.yml`); nothing is duplicated in the role.

## The pin (ADR-0607)

The operator is pre-GA (`alpha`) and its catalog is not pinned by digest, so
the Subscription is `installPlanApproval: Manual` with
`startingCSV: nfs-provisioner-operator.v0.0.9` (`subscription.version` and
`operator.csv` in the chart's values). The role approves only an InstallPlan
that installs exactly that CSV. When the pinned CSV already runs, nothing is
approved; an upgrade InstallPlan the catalog offers later stays pending and is
reported. Moving the pin is a commit that names the release and the owner's
go (`docs/platform/pre-ga-upgrade.md`).

## Adoption on demo333

The operator, its OperatorGroup and the `NFSProvisioner` were installed by
hand on demo333 on 2026-10-15. The chart uses the same names, namespace and
operand spec, so the first `make d1 install nfs-provisioner` adopts them in
place and must be a no-op for the workload: the NFS server Deployment, its
`nfs-server` volume, the StorageClass and UnifAI's volumes are not touched.
The known differences, all metadata or Subscription settings, are:

- Subscription: `installPlanApproval` goes from `Automatic` to `Manual` and
  `startingCSV` is added (the ADR-0607 pin; OLM ignores `startingCSV` once a
  CSV is installed); startx labels, `openshift.io/generated-by` and the
  ArgoCD sync-wave and tracking annotations are added.
- OperatorGroup: the same labels and annotations; `olm.providedAPIs` keeps the
  value OLM wrote.
- Namespace: the startx `project` chart's PreSync hook adds labels (including
  `openshift.io/cluster-monitoring: "true"`) and the display-name,
  description and requester annotations. It is applied over the existing
  namespace, never recreated or renamed, and never pruned.
- NFSProvisioner: the label `zuno.io/managed-by: argocd` and the sync-wave and
  `Prune=false` annotations; the spec is identical.

Before that first run, in this order and only with the user's go (none of it
is done by the commit that adds this role):

1. `make d0 install argocd`, so that the `zuno-platform` AppProject admits the
   `nfs-provisioner` namespace.
2. `make d0 install aap-config` when `make` routes through AAP, so that the
   Day 1 Job and Workflow Templates offer the new component.
3. Check that the installed CSV is still the pin
   (`oc get subscription nfs-provisioner-operator -n nfs-provisioner -o
   jsonpath='{.status.installedCSV}'`): the hand-made Subscription is
   `Automatic` until it is adopted, so OLM can move it to a newer release;
   the role then refuses, and the pin has to move first.
