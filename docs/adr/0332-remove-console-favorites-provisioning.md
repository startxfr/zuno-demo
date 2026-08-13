# ADR-0332: Remove Console favorites provisioning

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md) for the Console favorites provisioning component

## Decision

Remove `console_favorites_provisioning` in its entirety: the Ansible role
(`ansible/roles/console_favorites_provisioning`), its GitOps Application
pair (`gitops/apps/console-favorites-provisioning`), its Helm chart
(`gitops/charts/console-favorites-provisioning` - the CronJob, RBAC,
ServiceAccount, ExternalSecret, script/template ConfigMaps and reconciler
source), the Day 0 sequencing entries in `ansible/playbooks/day0_install.yml`,
`day0_uninstall.yml`, `day0_check.yml` and the Makefile's `DAY0_COMPONENTS`
list, its dedicated Keycloak service-account client
(`console-favorites-provisioner`, realm-zuno.json) and service-account user,
its `ExternalSecret`/volume-mount wiring in `gitops/charts/keycloak`, and its
Vault secret-seeding step in `ansible/roles/vault/tasks/install.yml`.

This was a test/experimental component: a periodic reconciler pre-creating
OpenShift `User` objects and seeding OpenShift Console "favorite namespaces"
for Keycloak-authenticated platform/cluster operators. The experiment is
concluded and the component is being fully withdrawn, not paused or
disabled - no toggle, flag, or dormant code path is left behind.

**What is unaffected:** ADR-0320 bundled four things together, and only
Console favorites provisioning is reverted here. The other three stay in
effect exactly as ADR-0320 defined them:

- The Keycloak realm changes (`admin`/`zuno-admin`/`aidev`/`aiops` groups,
  the `openshift` OIDC client, the four new demo personas).
- OpenShift OAuth configuration (`ansible/roles/openshift_oauth`,
  `gitops/charts/openshift-oauth`) - the cluster `OAuth`/`cluster` singleton
  and `mappingMethod: add` remain unchanged. `mappingMethod: add` is kept
  as-is (it is still correct behavior on its own merits - it prevents
  duplicate `User` objects if one already exists for any reason - even
  though the specific reason ADR-0320 originally cited, the CronJob
  pre-creating `User`s, no longer applies); only the stale comments citing
  the now-removed CronJob as the rationale were reworded.
- The static RBAC bindings (`ansible/roles/openshift_rbac_groups`,
  `gitops/charts/openshift-rbac-groups`) - untouched.

## Consequences

OpenShift Console "favorite namespaces" are no longer pre-seeded for any
user; a newly-provisioned platform/cluster operator now pins their own
namespaces manually on first Console visit, the same as any OpenShift
cluster without this component. This is a pure UI-convenience regression,
not a security or access-control one - as ADR-0320 itself noted, favorites
were always UI-only preferences, never an authorization mechanism, so their
absence changes nothing about what any user can actually do.

This repository no longer has a `CronJob` anywhere in `gitops/` (ADR-0320
introduced the first one); the "first `CronJob`, sets the pattern for future
recurring jobs" precedent ADR-0320 established no longer has a live example
to point to.

## Related ADRs

- [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md) - superseded by this ADR for Console favorites provisioning; its Keycloak realm, OpenShift OAuth and static RBAC bindings decisions remain in effect
