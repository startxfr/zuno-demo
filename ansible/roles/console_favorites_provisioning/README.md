# console_favorites_provisioning

Applies the `gitops/apps/console-favorites-provisioning` ArgoCD
Application pair (ADR-0320), whose chart
(`gitops/charts/console-favorites-provisioning`) deploys this
repository's first `CronJob` - every existing Job here
(`gitops/charts/sql-schema/templates/job-schema-apply.yaml`) is one-shot.
A Day 0 component (ADR-0056), ordered after `keycloak` (the
`console-favorites-provisioner` service-account client and its
Vault-seeded secret) and `openshift_oauth` (`mappingMethod: add`, so a
real login attaches to a User this CronJob pre-created instead of
duplicating it): `-d0` applies the `ServiceAccount`/RBAC/`ExternalSecret`/
script `ConfigMap`s; `-d1` applies the `CronJob` itself.

## Why this genuinely needs an active reconciliation loop

Unlike `ansible/roles/openshift_rbac_groups` (static bindings, no
reconciliation needed - OpenShift OAuth already syncs `Group` membership
on every login), Console favorites require knowing a user's OpenShift
`User` object UID *before* their first Console visit, which requires
pre-creating that `User`. A new Keycloak user can join `admin`/
`zuno-admin`/`aidev`/`aiops` at any time, not only at deployment - a
one-shot provisioner would only cover users that already existed in
Keycloak when it ran (ADR-0320's Alternatives considered explicitly
rejects that for this reason). The CronJob polls `KEYCLOAK_URL` every
`gitops/charts/console-favorites-provisioning/values.yaml`'s `schedule`
(default every 10 minutes) and closes that gap.

## Idempotency - the one hard requirement this reconciler must get right

Because this runs repeatedly, `files/reconciler.py` must only set
`console.favorites` when it *creates* the `user-settings-<uid>`
`ConfigMap`, never on a later reconciliation pass - a one-shot
provisioner has no way to clobber a user's own later Console
customization; a periodic one does, and ADR-0320's Security
considerations calls a failure to enforce this "a recurring data-loss
bug for any user who customizes their own favorites." The script
implements this via a plain `create` (never `patch`/`replace`) against
the Kubernetes API, treating a 409 Conflict as "already seeded, leave it
alone" rather than an error.

## Manual operator step required: capturing each profile's `console.favorites` template

**The four template files under `gitops/charts/console-favorites-
provisioning/files/favorites-template-*.json` are UNVERIFIED
PLACEHOLDERS as checked in** - no live OpenShift Console session was
available while writing this role to capture the real ConfigMap
key/format Console actually uses for pinned/favorite namespaces (it is
not documented and may vary by OpenShift version). Same "operator action
required" pattern `ansible/roles/keycloak/README.md` already documents
for the Google OAuth client secret (`ansible/confidential.yml`):

1. Log into the real OpenShift Web Console as each of the four template
   accounts (`template-admin`, `template-zuno-admin`, `template-aidev`,
   `template-aiops` - create these once, following the same anonymized-
   persona convention ADR-0041 established, or reuse the four ADR-0320
   demo personas `platform-admin-01`/`zuno-admin-01`/`ai-dev-01`/
   `ai-ops-01` for this one-time capture).
2. Pin the namespaces that profile should see by default, using the
   Console's own favorite/pin UI - `zuno-admin`'s should follow the
   `zuno.io/managed=true` namespace set `gitops/charts/openshift-rbac-
   groups` already binds RBAC against (same source of truth, kept in
   sync by convention, not by shared code); `aidev`/`aiops` should follow
   the `zuno-ai-build`/`zuno-ai-run` namespaces those groups get `edit`
   on.
3. Read back the real `openshift-console-user-settings/user-settings-
   <uid>` `ConfigMap` created for that login, and replace the matching
   `favorites-template-<profile>.json` file's content with the real key
   and value verbatim - `files/reconciler.py` deliberately does not
   interpret or compute this format itself (ADR-0320's Decision:
   "`console.favorites`'s internal format stays out of this reconciler's
   own logic"), so whatever is checked in there is seeded exactly as-is.

Until this step is done, the CronJob will create `User` objects and
scoping `Role`/`RoleBinding`s correctly, but will seed each new
ConfigMap with the placeholder JSON above, not real favorites - a
functional gap, not a crash; re-run after replacing the template files
and any *not-yet-created* ConfigMap will pick up the real content on its
next reconciliation (already-created ones will not, by the same
idempotency rule above - delete them manually if a re-seed is needed
after fixing the templates).

## Security considerations

The `ServiceAccount`'s `ClusterRole` is deliberately narrow - `create`/
`get`/`patch`/`list` on `users.user.openshift.io` and `get`/`list` on
`namespaces` only; no write access outside `openshift-console-user-
settings`, and nothing resembling `cluster-admin`, even though the
`admin` group it provisions favorites for does have that grant elsewhere
(`gitops/charts/openshift-rbac-groups`). Favorites remain UI-only
preferences, never an authorization mechanism.
