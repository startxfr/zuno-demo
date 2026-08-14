# openshift_rbac_groups

Applies the `gitops/apps/openshift-rbac-groups` ArgoCD Application pair,
whose chart (`gitops/charts/openshift-rbac-groups`) renders static RBAC
bindings for the four platform/cluster-operator Keycloak groups (`admin`,
`zuno-admin`, `aidev`, `aiops`). A Day 0 component, ordered after
`namespaces` (the `zuno-admin` `RoleBinding`s need
`gitops/charts/namespaces`' `zuno.io/managed=true` namespaces to already
exist and be labeled): `-d0` applies the cluster-wide `ClusterRoleBinding`
(`admin` -> `cluster-admin`, no namespace dependency); `-d1` applies the
namespace-scoped `RoleBinding`s.

## Why this needs no active reconciliation

OpenShift OAuth already synchronizes `Group` membership from the ID
token's `groups` claim on every login (`mappingMethod: add`,
`ansible/roles/openshift_oauth`) - a `RoleBinding` targeting a `Group` by
name works the moment both the `Group` and the binding (this role) exist;
GitOps already re-applies the binding set whenever the namespace/group
set changes.

## Discovering the managed-namespace list, not duplicating it

`tasks/install.yml` queries the live cluster for `Namespace` objects
labeled `zuno.io/managed=true` and passes the resulting name list into the
chart's `zunoManagedNamespaces` value. This keeps
`gitops/charts/namespaces/values.yaml` as the single place a namespace
opts into `zuno-admin` RBAC; a future `zuno-*` namespace only needs that
one label to inherit RBAC on its next `openshift_rbac_groups` run - no
chart/values edit here.

## Security considerations

The `admin` -> `cluster-admin` binding is a deliberate, explicit grant of
unrestricted cluster access - review it if this profile's real-world
membership ever grows beyond a small trusted set. `aidev`/`aiops` also
get `edit` on `zuno-ai-build`/`zuno-ai-run` (the platform's real CI
pipeline and shared multi-agent runtime, not dedicated sandboxes).

## Not yet verified against a live cluster

The RBAC `Group` subject names (`admin`, `zuno-admin`, `aidev`, `aiops`)
assume the "openshift" Keycloak client's groups protocol mapper delivers
bare group names, not full paths - `gitops/charts/keycloak/files/
realm-zuno.json`'s `openshift` client sets `full.path: "false"` on that
mapper (every other client in that file uses `full.path: "true"`, for
agent entitlement checks that need the full `/agent_<name>` path). If a
real cluster's OAuth `Group` sync produces `/admin` instead of `admin`,
these RBAC subjects must be updated to match.
