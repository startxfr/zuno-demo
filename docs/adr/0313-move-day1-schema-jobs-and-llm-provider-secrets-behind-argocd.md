# ADR-0313: Move Day 1 schema Jobs and LLM provider secret seeding behind ArgoCD/Vault

- **Status:** Implemented - Incident 2026-08-14: moving the credentials ExternalSecrets into the charts as plain Sync-phase resources deadlocked the first fresh install of `zuno-mcp-sales-db-d0` - the schema-apply Job is a PreSync hook consuming the Secret via `secretKeyRef`, and ArgoCD only starts the Sync phase after every PreSync hook succeeds, so the ExternalSecret was never applied and the hook pod sat in `CreateContainerConfigError` forever (`backoffLimit` never triggers on that state, and the Job had no `activeDeadlineSeconds`). Fixed by moving the Job to a `Sync`-phase hook one wave after the ExternalSecret (sql-schema: ES wave 0 → Job wave 10; rag-service: ES wave 40 → Job wave 41, Deployment 45), keeping the ExternalSecret a plain tracked resource, in both `gitops/charts/sql-schema` and `gitops/charts/rag-service` (same latent shape there, dormant only because its Secret predated this migration), plus `activeDeadlineSeconds: 300` on both Jobs so a future stall fails the sync visibly. An intermediate attempt (ES as PreSync hook, wave -1) was reverted the same day, confirmed live: an app whose every resource is a hook is trivially Synced, so ArgoCD automated sync never starts an operation and a fresh install silently skips the schema.
- **Target:** v0
- **Date:** 2026-08-09
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0312 closed the operator-install exception bucket (`openshift_ai`,
`nfd`, `nvidia_gpu`, `external_secrets`, later extended to `postgresql`/
`keycloak`) so that every installed component is owned by exactly one
ArgoCD `Application`, with Ansible limited to resolving runtime values and
registering `Application`s (`ansible/tasks/apply_gitops_app.yml`). Two
Day 1 gaps were found still outside that pattern, on inspection prompted
by an explicit operator request to audit every Day 1 role against it:

1. **`llm`** (`ansible/roles/llm/tasks/install.yml`) read the root Vault
   credential (`vault-bootstrap-credentials`, a Secret `ansible/roles/
   vault/tasks/install.yml`'s own comment already flagged other consumers
   should never touch directly) and exec'd `vault kv get`/`vault kv put`
   into the Vault pod to seed placeholder API keys at
   `zuno/providers/{openai,gemini,anthropic,mistral}` - before even
   registering its own `Application`s. The declarative read side of this
   already existed and worked (`platform/ai-gateway/externalsecret-
   {openai,gemini,anthropic,mistral}.yaml`, each resolving through the
   `vault-backend` `ClusterSecretStore` ADR-0312's `external_secrets`
   conversion depends on) - only the write/seed side was imperative, in
   the one role that had no legitimate reason to be (unlike `vault`
   itself, which owns Vault's bootstrap by necessity).
2. **`sql_schema`** and **`rag`** each applied a one-shot PostgreSQL
   schema/fixtures `Job` directly via `kubernetes.core.k8s`
   (delete-then-recreate, since Jobs are immutable), documented in
   `gitops/apps/README.md` as an intentional exception alongside `vault`'s
   imperative unseal - "one-shot/imperative actions rather than standing
   installed components." Unlike `vault`'s unseal, which is a genuine
   chicken-and-egg (Vault must exist and be unsealed before anything can
   read from it), neither Job has that constraint: both consume a
   PostgreSQL already running as a standing GitOps-managed component
   (`postgresql`) and credentials already distributed via `ExternalSecret`
   from Vault. The exception had been carried over from `sql_schema`
   (ADR-0016) to `rag` (ADR-0046) for consistency, not because ArgoCD
   genuinely can't express it.

## Decision

1. **`llm` provider placeholders move into `vault`'s existing seeding
   step.** `ansible/roles/vault/tasks/install.yml` already runs a
   check-then-placeholder loop for `google-oauth/client`, `smtp/technical`
   and `confluence/technical` (seed an empty placeholder only if no value
   exists yet, never overwrite an operator-supplied one). A parallel block
   was added for `providers/{openai,gemini,anthropic,mistral}`, seeding
   `api_key=__placeholder__` (the field name each `externalsecret-*.yaml`
   resolves) rather than the generic block's own `_placeholder=true`
   marker. `ansible/roles/llm/tasks/install.yml` no longer touches Vault
   at all - it only registers the `llm`/`ai-gateway`/`agent-runtime`
   `Application`s, `-d0` then `-d1`, exactly like every other Day 1 role.
2. **`sql_schema`'s and `rag`'s schema Jobs become ArgoCD `PreSync` hooks**
   templated into the consuming chart, with
   `argocd.argoproj.io/hook-delete-policy: BeforeHookCreation` - the
   GitOps-native equivalent of the delete-then-recreate Ansible did by
   hand. ArgoCD blocks `Synced` until a `PreSync` hook succeeds, so the
   existing `apply_gitops_app.yml` Synced+Healthy wait covers Job
   completion too, with no bespoke Ansible wait task needed.
   - `rag`'s Job (`gitops/charts/rag-service/templates/
     job-schema-apply.yaml`) lives in that chart's own `-d1` Application -
     same namespace (`zuno-data`) as the Job it replaces, no new chart
     needed.
   - `sql_schema`'s Job targets `zuno-data`, but the `Application` it
     precedes (`mcp-sales-db`) deploys into `zuno-ai-run` - a namespace
     mismatch that ruled out putting the Job inside `gitops/charts/
     mcp-sales-db`. A new chart, `gitops/charts/sql-schema`, holds the Job
     plus the `sql-schema-postgresql-credentials` `ExternalSecret` it
     needs (moved from `ansible/roles/sql_schema/kustomize/prereqs/
     externalsecret.yaml`, previously applied by `ansible/tasks/
     apply_kustomize.yml`), and is registered as `mcp-sales-db`'s `-d0`
     ("prerequisites") `Application` - previously an empty `gitops/charts/
     noop` render, now real content, the first component whose `-d0` is a
     prerequisite Job rather than an operator install.
   - Both roles keep applying their SQL/fixtures `ConfigMap` via `ansible/
     tasks/apply_kustomize.yml` (`ansible/roles/{sql_schema,rag}/
     kustomize/schema/`, plain `configMapGenerator`s reading
     `data/{sxa,rag}/`) - static data, not the imperative logic this ADR
     is about; see "Alternatives considered."

`vault`'s own imperative init/unseal/secret-seeding is unaffected and
stays permanently imperative, per ADR-0312's explicit "considered and
rejected" note - it calls Vault's own API and captures generated secret
material at runtime, which no combination of ArgoCD/Helm can express.

## Alternatives considered

- **Also move the SQL/fixtures `ConfigMap` generation into each chart**
  (via Helm's `.Files.Get` on SQL files copied into the chart directory),
  closing the gap completely. Rejected for this change: it's static data
  plumbing, not business logic or a secret, so it wasn't the pattern this
  audit was about, and duplicating `data/{sxa,rag}/` into each chart (or
  restructuring `data/` into a chart-relative layout) is a larger,
  separable change with no functional benefit beyond consistency. Left as
  a documented future option, not required by this ADR.
- **Have `llm`'s own chart (`platform/ai-gateway`) seed the provider
  placeholders via a hook,** instead of moving the logic into `vault`.
  Rejected: a chart running `vault kv put` from inside a PreSync hook
  would need its own Vault-writing credential distinct from the
  `eso-reader` read-only role every `ExternalSecret` uses, reintroducing a
  second privileged Vault credential outside `vault-bootstrap-credentials`
  itself - `vault`'s role already has the root token in scope for exactly
  this kind of seeding, so extending its existing loop is strictly
  smaller and keeps Vault-write access confined to one role.

## Consequences

`ansible/roles/llm/tasks/install.yml` shrinks to Application registration
only. `ansible/roles/vault/tasks/install.yml` gains one more
check-then-placeholder block, seeding four more Vault paths on every
`vault` install/re-run (idempotent, same as its existing three).
`ansible/roles/{sql_schema,rag}/tasks/install.yml` lose their Job
delete/create/wait tasks. `gitops/charts/sql-schema` is a new chart;
`gitops/apps/mcp-sales-db/application-d0.yaml` moves from `gitops/charts/
noop` to it. `gitops/apps/README.md`'s exception list shrinks to `argocd`,
`admin_context` and `vault`'s unseal.

## Security considerations

No new privilege: the `PreSync` hook Jobs run with the same PostgreSQL
credential (via `ExternalSecret` → `vault-backend` `ClusterSecretStore`)
the Ansible-managed Jobs already used, and the `llm` provider placeholders
are seeded by `vault`'s role, which already held the root Vault token in
scope. `llm`'s role loses its own (narrower, but still root-token-reading)
Vault access entirely - a net reduction in which roles can read
`vault-bootstrap-credentials`.

## Operational considerations

On an already-bootstrapped cluster, the first `make d0 install vault`
after this change seeds the four new placeholder paths without touching
any already-populated provider key (same never-overwrite guarantee as the
existing three). The first `make d1 install rag` / `mcp-sales-db` re-syncs
their `Application`s with a hook Job instead of an ansible-created one -
the previous Ansible-managed `Job` object (`zuno-rag-schema-apply` /
`zuno-sxa-schema-apply`, labeled `zuno.io/managed-by: zuno-ansible`) is
orphaned (not ArgoCD-owned) and should be deleted manually once the new
hook Job (labeled `zuno.io/managed-by: argocd`) has run successfully.

See [Standard clauses](README.md#standard-clauses) for Migration/evolution.

## Related ADRs

- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md) (the operator-install conversion this extends to the two
  remaining Day 1 imperative-Job cases it explicitly left out of scope)
- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md) (Ansible-driven `-d0`-before-`-d1` ordering, relied on here for
  `mcp-sales-db`'s new `-d0` prerequisites Application)
- [ADR-0024](0024-use-vault-for-application-secrets.md) (Vault as the platform's single source of truth for secrets,
  the principle `llm`'s direct read violated)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md) (ModelRouter provider fail-over, unaffected - still fails over
  past any provider whose key is still the `__placeholder__` sentinel)

## Review evidence

Grounded in a direct read of `ansible/roles/{llm,vault,rag,sql_schema}/
tasks/install.yml`, `platform/ai-gateway/externalsecret-*.yaml`,
`gitops/charts/{external-secrets,rag-service,mcp-sales-db}/`, `gitops/apps/
{llm,rag,mcp-sales-db}/application-{d0,d1}.yaml`, and `gitops/apps/
README.md`'s documented exception list - confirmed via `grep -rn
vault-bootstrap-credentials` that `llm` and `vault` were the only two
consumers, and that no other Day 1 role performs a comparable direct Vault
read or ansible-managed Job. Follows an explicit operator request to audit
every Day 1 role against the day0 `Application`+chart+`ExternalSecret`
pattern and convert what could be converted without reintroducing a
chicken-and-egg Vault requires.
