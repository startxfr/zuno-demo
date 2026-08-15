# openshift_rbac_groups

Applies the `gitops/apps/openshift-rbac-groups` ArgoCD Application pair,
whose chart (`gitops/charts/openshift-rbac-groups`) renders static RBAC
bindings for the four ADR-0349 cluster-access Keycloak groups
(`ocp-paas-ops`, `ocp-paas-dev`, `ocp-ai-dev`, `ocp-ai-ops` - replacing
ADR-0320's `admin`/`zuno-admin`/`aidev`/`aiops`). A Day 0 component,
ordered after `namespaces` (the AI-profile `RoleBinding`s need
`gitops/charts/namespaces`' `zuno.io/managed=true` namespaces to already
exist and be labeled): `-d0` applies the cluster-wide
`ClusterRoleBinding`s (`ocp-paas-ops` -> `cluster-admin`,
`ocp-paas-dev` -> `cluster-reader`, no namespace dependency); `-d1`
applies the namespace-scoped `RoleBinding`s (`ocp-ai-dev` -> `edit`,
`ocp-ai-ops` -> `admin`, ranged over the discovered namespace set).

ArgoCD-side access for the same groups (`role:admin` for `ocp-paas-ops`,
a get/sync `zuno-paas-dev` role for `ocp-paas-dev`) is configured in
`ansible/roles/argocd/kustomize/argocd/argocd.yaml`, not here.

## Why this needs no active reconciliation

OpenShift OAuth already synchronizes `Group` membership from the ID
token's `groups` claim on every login (`mappingMethod: add`,
`ansible/roles/openshift_oauth`) - a `RoleBinding` targeting a `Group` by
name works the moment both the `Group` and the binding (this role) exist;
GitOps already re-applies the binding set whenever the namespace/group
set changes.

Renaming the groups leaves stale `Group` objects (`admin`, `zuno-admin`,
`aidev`, `aiops`) on a cluster where the old personas already logged in;
they carry no RBAC after this change but should be cleaned up manually
once (`oc delete group admin zuno-admin aidev aiops` - ADR-0349's own
Operational considerations).

## Discovering the managed-namespace list, not duplicating it

`tasks/install.yml` queries the live cluster for `Namespace` objects
labeled `zuno.io/managed=true` and passes the resulting name list into the
chart's `zunoManagedNamespaces` value. This keeps
`gitops/charts/namespaces/values.yaml` as the single place a namespace
opts into AI-profile RBAC; a future `zuno-*` namespace only needs that
one label to inherit RBAC on its next `openshift_rbac_groups` run - no
chart/values edit here.
