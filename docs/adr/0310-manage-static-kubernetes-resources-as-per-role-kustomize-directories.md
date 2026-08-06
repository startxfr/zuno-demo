# ADR-0310: Manage static Kubernetes resources as per-role kustomize directories

- **Status:** Proposed
- **Target:** v0
- **Date:** 2026-08-06
- **Decision owners:** Zuno Demo architecture team

## Context

Fourteen roles under `ansible/roles/` embed raw Kubernetes resources directly
in task files via `kubernetes.core.k8s: definition: {apiVersion, kind,
metadata, spec...}` blocks (Namespaces, OperatorGroups, Subscriptions,
PriorityClasses, ClusterRoleBindings, ClusterPolicies, ResourceQuotas,
ClusterSecretStores, and similar). Most of these definitions never change
between runs or clusters - `admin_context`'s two PriorityClasses are
literally duplicated verbatim between `tasks/prepare.yml` and
`tasks/configure.yml` today, with a comment explaining they're "idempotent -
same definitions as prepare.yml" rather than a single source of truth.
Reviewing a resource's actual desired state requires reading Ansible task
YAML rather than a plain Kubernetes manifest, and there is no way to
`kustomize build` / diff a role's static resources independently of running
the playbook.

Not every embedded resource is static, though. Some task files copy `data:`
out of a live Secret at run time (`agents/tasks/run_acceptance_gate.yml`'s
`acceptance-gate-credentials`), or define one-shot Jobs that are deleted and
recreated every run (`rag/tasks/configure.yml`,
`agents/tasks/run_acceptance_gate.yml`), or need one or two values resolved
by a prior discovery step (`keycloak/tasks/prepare.yml`'s Subscription
channel/catalogSource, discovered from a live `PackageManifest` lookup).
Treating all embedded resources identically would either leave the dynamic
ones behind or force real orchestration logic into static manifests it
cannot represent.

## Decision

Introduce a `kustomize/<group>/` directory per role for resources whose
desired state does not depend on data discovered during that Ansible run,
and a shared task, `ansible/tasks/apply_kustomize.yml`, that runs
`kustomize build` on a given directory and applies each resulting resource
through `kubernetes.core.k8s` (preserving check-mode and per-resource
idempotency reporting, rather than shelling out to `kubectl apply -k`
directly). Group subdirectories follow the existing sequencing a role
already needs (e.g. an `operator/` group applied before a CRD-established
wait, a `cr/` group applied after) - a kustomize directory does not need to
hold everything a role touches, only the resources applied at one point in
that role's sequence.

Resources are classified into three tiers, and only the first two move:

1. **Fully static** (no runtime values) - moves to `kustomize/`, applied via
   `apply_kustomize.yml`. The majority of today's embedded `definition:`
   blocks fall here.
2. **Static shape, one or two values resolved at run time** (e.g. an
   operator channel discovered from a `PackageManifest`, `cluster_base_domain`) -
   also moves to `kustomize/`, using a placeholder token substituted by
   `apply_kustomize.yml` before parsing, the same string-substitution
   convention `ansible/tasks/apply_gitops_app.yml` already uses for
   `__CLUSTER_BASE_DOMAIN__`. ConfigMaps built purely from file contents
   (`lookup('ansible.builtin.file', ...)`) belong here too, via kustomize's
   native `configMapGenerator: files:` - no placeholder needed.
3. **Genuinely dynamic per-run orchestration** (one-shot Jobs recreated every
   run, Secrets whose `data:` is copied from another live Secret) - stays as
   an inline `kubernetes.core.k8s` task. Forcing these into kustomize would
   relocate the `kind:` without removing any complexity, since the actual
   values only exist during that Ansible run.

`kubernetes.core` 3.3.1 (the version pinned in `ansible/requirements.yml`)
has no native kustomize support in its `src:` parameter - it only reads a
plain YAML/JSON manifest file. `apply_kustomize.yml` bridges this by
shelling out to the `kustomize` binary and feeding the parsed multi-document
output back through `kubernetes.core.k8s` per resource.

`kubernetes.core.k8s_info` lookups (precheck reads, `until` wait conditions)
are out of scope - they are queries, not resources this repository owns the
desired state of, and moving them to kustomize has no meaning.

## Alternatives considered

- Shell out directly to `kubectl apply -k <dir>` / `oc apply -k <dir>` via
  `ansible.builtin.command`. Rejected: loses `kubernetes.core.k8s`'s
  check-mode support and structured per-resource changed/unchanged
  reporting that the rest of this repository's roles rely on for
  `ansible-playbook --check` dry runs.
- Move every embedded resource, including the dynamic ones, into kustomize
  using `configMapGenerator`/`secretGenerator`/`replacements` for all
  runtime data. Rejected for the Job and Secret-copy cases specifically:
  those values only exist during the Ansible run itself (a freshly
  discovered image, another Secret's live `data:`), so representing them as
  checked-in kustomize manifests would need a generated overlay written to
  disk on every run anyway - no different in kind from today's inline
  `definition:`, just with more indirection.
- Leave the current inline-`definition:` convention unchanged. Rejected:
  the `admin_context` duplication is a live example of the drift this
  invites, and there is no way to independently validate a role's static
  desired state without executing Ansible.

## Consequences

Static Kubernetes desired state becomes readable and diffable as plain
YAML (`kustomize build ansible/roles/<role>/kustomize/<group>`) independent
of Ansible, and can be validated with `kustomize build` / `kubeconform` in
CI without a live cluster. Roles that re-apply the same resources across
`prepare.yml` and `configure.yml` (currently only `admin_context`) collapse
to a single checked-in source referenced from both phases instead of
copy-pasted YAML. Task files shrink to `include_tasks` calls naming a
directory, matching the existing `apply_gitops_app.yml` convention. The
tradeoff is a second manifest convention in the repository (Helm charts
under `gitops/charts/` for GitOps-managed application workloads, kustomize
under `ansible/roles/*/kustomize/` for Ansible-applied bootstrap resources)
rather than one - judged acceptable since the two solve different problems
(continuously-reconciled application state vs. one-time-per-run bootstrap
objects) and already use different tools (ArgoCD vs. Ansible) today.

## Security considerations

No change in what is granted or to whom - this ADR only relocates existing
resource definitions from Ansible task YAML to kustomize-managed YAML
files; the rendered manifests `apply_kustomize.yml` sends to
`kubernetes.core.k8s` are required to be identical to what the role applied
before migration. `kustomize build` runs against directories checked into
this repository only - no remote bases are introduced.

## Operational considerations

Each migrated role's pilot must be validated by diffing
`kustomize build ansible/roles/<role>/kustomize/<group>` against the
resource(s) the replaced task previously sent to `kubernetes.core.k8s`, and
by a real `make d0 configure <component>` (or `day0`) run confirming
idempotent re-apply (`changed: false` on a second run).

## Implementation state

**Proposed.** `ansible/tasks/apply_kustomize.yml` and the pilot migration of
`admin_context` (both PriorityClasses, previously duplicated between
`prepare.yml` and `configure.yml`) and `argocd` (the static half of
`prepare.yml`: Namespace, Subscription, ClusterRoleBinding) land alongside
this ADR as the first example. The remaining Tier 1/Tier 2 roles
(`external_secrets`, `vault`, `nfd`, `observability`, `nvidia_gpu`,
`postgresql`, `sql_schema`, `openshift_ai`, `keycloak`, and the two
file-backed ConfigMaps in `rag`/`agents`) are not yet migrated.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the
  implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the
  behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an
  authorization, identity, data-classification or trust boundary (not
  applicable here - no trust boundary changes).

## Related ADRs

- ADR-0003
- ADR-0022

## Review evidence

This decision is grounded in a direct read of every `state: present` +
`definition:` block across `ansible/roles/*/tasks/*.yml` in this
repository's current `main` branch (2026-08-06), classified by whether the
resource's desired state depends on data available only during that
Ansible run.
