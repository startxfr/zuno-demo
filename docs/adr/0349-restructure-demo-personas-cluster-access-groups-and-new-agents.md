# ADR-0349: Restructure demo personas, ocp-* cluster-access groups and two new agents

- **Status:** Partially implemented (realm restructure, ocp-* RBAC, ArgoCD policy, soursage/cognos and evaluation renames merged; realm re-apply + live RBAC/ArgoCD/login verification pending)
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Context

The `zuno` realm (`gitops/charts/keycloak/files/realm-zuno.json`) currently defines 17 synthetic users with `@zuno-demo.internal` emails, no `firstName`/`lastName`, and a single shared password resolved through Keycloak's file-mode vault SPI (`${vault.demo_personas_password}`, ADR-0041). Identity is organized in three orthogonal group dimensions: `agent_<name>` entitlement groups (ADR-0040), business-role groups with RAG ACL subgroups (`sales`, `consultant`, `adv`, `finance`, `board`, ADR-0330), and the ADR-0320 platform groups (`admin`, `zuno-admin`, `aidev`, `aiops`) bound to OpenShift RBAC through OAuth login-time group sync.

A review of the realm against the demo's actual needs surfaced several gaps: personas cannot receive real mail (SMTP flows and password-reset cannot be demonstrated), users carry no human-readable names, the platform-access group names do not communicate their scope, there is no PaaS-operator/PaaS-developer distinction, no persona covers recruiting, and two new agent ideas (soursage, cognos) have no identity footprint. This ADR redefines the persona set, the cluster-access dimension, the agent-membership matrix and the initial-credential policy in one coherent decision.

## Decision

### 1. Persona set

The realm is rebuilt around 14 named personas plus the two ADR-0040 negative-test fixtures — 16 users total.

Naming conventions: emails use plus-addressing on a real mailbox (`dev+zuno-<user>@startx.fr`) so every persona can receive mail while remaining non-nominative (ADR-0041 stays intact — these are role names, not people). `firstName` carries the persona label; `lastName` encodes the organizational tier (`FrontOffice`, `MiddleOffice`, `BackOffice`).

| username | email | firstName / lastName | groups |
|---|---|---|---|
| `adv-01` | dev+zuno-adv01@startx.fr | ADV1 / MiddleOffice | `/adv`, `/agent_advantage` |
| `adv-02` | dev+zuno-adv02@startx.fr | ADV2 / MiddleOffice | `/adv`, `/agent_advantage` |
| `ai-dev-01` | dev+zuno-aidev01@startx.fr | AI_Dev / BackOffice | `/ocp-ai-dev`, `/agent_tekos` |
| `ai-ops-01` | dev+zuno-aiops01@startx.fr | AI_Ops / BackOffice | `/ocp-ai-ops`, `/agent_tekos` |
| `paas-dev-01` | dev+zuno-paasdev01@startx.fr | PaaS_Dev / BackOffice | `/ocp-paas-dev`, `/agent_tekos` |
| `paas-ops-01` | dev+zuno-paasops01@startx.fr | PaaS_Ops / BackOffice | `/ocp-paas-ops`, `/agent_tekos` |
| `board-01` | dev+zuno-board01@startx.fr | Board1 / BackOffice | `/board`, `/agent_advantage`, `/agent_finage`, `/agent_cognos` |
| `board-02` | dev+zuno-board02@startx.fr | Board2 / BackOffice | `/board`, `/agent_advantage`, `/agent_finage`, `/agent_cognos` |
| `consultant-01` | dev+zuno-consultant01@startx.fr | Consultant01 / FrontOffice | `/consultant`, `/agent_comage`, `/agent_tekos`, `/agent_arkos`, `confluence-build-satellite`, `confluence-run-satellite`, all 4 `confluence-archi-*` |
| `consultant-02` | dev+zuno-consultant02@startx.fr | Consultant02 / FrontOffice | `/consultant`, `/agent_tekos`, `/agent_arkos`, `confluence-build-openshift`, `confluence-build-openshift-ai`, all 4 `confluence-archi-*` |
| `consultant-03` | dev+zuno-consultant03@startx.fr | Consultant03 / FrontOffice | `/consultant`, `/agent_tekos`, `confluence-run-openshift`, `confluence-run-keycloak` |
| `sale-01` | dev+zuno-sale01@startx.fr | Sale01 / FrontOffice | `/sales`, `/agent_comage`, `/agent_finage` |
| `sale-02` | dev+zuno-sale02@startx.fr | Sale02 / FrontOffice | `/sales`, `/agent_comage`, `/agent_soursage` |
| `recrut-01` | dev+zuno-recrut01@startx.fr | Recrut01 / BackOffice | `/recrut`, `/agent_comage`, `/agent_soursage` |
| `tekos-entitlement-only-user-01` | unchanged | — | `/agent_tekos` (ADR-0040 fixture) |
| `consultant-role-only-user-01` | unchanged | — | `/consultant` (ADR-0040 fixture) |

Renames: `adv-user-0N`→`adv-0N`, `consultant-user-0N`→`consultant-0N`, `board-user-0N`→`board-0N`; the per-user `confluence-build/run-*` ACL memberships of the former `consultant-user-0N` carry over 1:1.

Removed: `sales-user-01/02` (replaced by `sale-01/02`), `finance-user-01/02` (`agent_finage` is now carried by board and `sale-01`), `platform-admin-01` and `zuno-admin-01` (superseded by `paas-ops-01`; their groups disappear — see §2).

Kept deliberately: the two ADR-0040 negative-test fixtures, unchanged including their `@zuno-demo.internal` emails. `consultant-role-only-user-01` was evaluated for removal and retained because no new persona can replace it: every `consultant-0N` now holds `agent_tekos`, so no other user can exercise `business_role_without_entitlement_denied_by_bff` in `evaluations/tekos/security_checks.py`, and `tekos-entitlement-only-user-01` covers the inverse case.

### 2. Group model

**Agent entitlement dimension (ADR-0040, unchanged semantics)** grows from five to seven groups: `agent_soursage` and `agent_cognos` join, each carrying the `clientRoles` mapping to its new frontend client's `access` role. The underscore naming (`agent_<name>`) is kept: it is baked into `components/agent-bff/main.go` (which computes `"agent_" + agentName` for the 403 check), the OKF bundles' `zuno.access.groups` and the evaluation suites; renaming to hyphens was rejected as churn without benefit.

**Business-role dimension** gains `/recrut` (recruiting, gates future soursage tools in `policies/tools/tool-policy.yaml`). `/sales` absorbs the new sale personas; `/finance` survives with no members because `tool-policy.yaml` references it and future finage tools will gate on it. `/sales_admin` stays reserved as before.

The four `confluence-archi-*` RAG ACL subgroups **relocate from `/board` to `/consultant`**, and their membership moves from the board personas to the arkos-entitled consultants (`consultant-01/02`). This advances ADR-0340's requirement that `board` consistently mean Direction rather than serving as the ADR-0330 architect container. The full group path therefore changes (`/board/confluence-archi-*` → `/consultant/confluence-archi-*`): `gitops/charts/rag-ingestion/values.yaml` `requiredGroups` and any already-ingested `document_embeddings.metadata.acl_groups` values must follow at implementation time.

**Cluster-access dimension (replaces ADR-0320's groups entirely):** `admin`, `zuno-admin`, `aidev`, `aiops` are removed and replaced by four `ocp-*` groups whose names state their scope: `ocp-paas-ops`, `ocp-paas-dev`, `ocp-ai-dev`, `ocp-ai-ops`. `zuno-admin` has no successor — its per-namespace admin role is covered by the combination of `ocp-paas-ops` (full cluster) and `ocp-ai-ops` (admin on the AI namespaces).

### 3. Initial credentials

The initial password for all personas is `secretdemerde`, provisioned through the existing mechanism: the realm keeps the single `${vault.demo_personas_password}` placeholder resolved by Keycloak's file-mode vault SPI, and the seeded default value in Vault changes to `secretdemerde`. Concretely, `zuno_admin_demo_personas_root_password` in `ansible/inventories/demo/group_vars/all/auto.yml` is decoupled from `zuno_admin_password` and defaults to `secretdemerde`. No literal password enters Git (ADR-0041 intact) and no per-user Vault keys are created.

Individual passwords are stored **only in Keycloak**: `KeycloakRealmImport` applies the credential once, after which each user's password lives in Keycloak's dedicated PostgreSQL database (ADR-0315) and can be changed per user through Keycloak (`resetPasswordAllowed: true` is already set). Vault holds only the initialization default, never the live value. A Vault-as-credential-backend integration was evaluated and rejected: Keycloak's vault SPI is a read-only configuration lookup, and no supported integration exists that would let Keycloak generate and store per-user passwords in Vault.

### 4. OpenShift access

The OAuth OpenID identity provider, the confidential `openshift` client and the login-time group sync established by ADR-0320 are unchanged. `gitops/charts/openshift-rbac-groups` is rewired to the new groups:

- `ocp-paas-ops` → `cluster-admin` (ClusterRoleBinding, replaces the `admin` binding) — full cluster and Console access;
- `ocp-paas-dev` → `cluster-reader` (new ClusterRoleBinding) — read everything cluster-wide, write nothing;
- `ocp-ai-dev` → `edit` and `ocp-ai-ops` → `admin`, as RoleBindings ranged over the live-discovered `zuno.io/managed=true` namespace set (the existing mechanism in `ansible/roles/openshift_rbac_groups/tasks/install.yml`), which covers the `zuno-*`, `redhat-ods-*` and `rhoai-*` platform namespaces. Neither AI group receives any ClusterRole;
- the `zuno-admin` per-namespace RoleBindings are removed.

All other personas (adv, board, consultant, sale, recrut) have no group with RBAC attached and therefore no effective OpenShift access, even though their groups sync as inert `Group` objects.

### 5. ArgoCD access

`ansible/roles/argocd/kustomize/argocd/argocd.yaml` `rbac.policy` gains a custom role so `ocp-paas-dev` can operate deployments read-only:

```text
p, role:zuno-paas-dev, applications, get, zuno/*, allow
p, role:zuno-paas-dev, applications, sync, zuno/*, allow
g, ocp-paas-dev, role:zuno-paas-dev
g, ocp-paas-ops, role:admin
```

The `g, ocp-paas-ops, role:admin` line is required, not redundant: today only `system:cluster-admins`/`cluster-admins` map to `role:admin`, and Keycloak-derived groups never matched either name. Groups reach ArgoCD through the existing Dex `openShiftOAuth` delegation with `scopes: '[groups]'` — no ArgoCD OIDC client is added to the realm.

### 6. New agents: soursage and cognos

Two new placeholder agents join the catalog, following the existing placeholder pattern (comage/advantage/finage/arkos: realm client + entitlement group + OKF bundle, no runtime):

- **soursage** — recruiting assistant. Interacts with Workday and LinkedIn to source new consultant candidates and to find, among existing consultants, the best profile for a mission. Audience: recruiting (`recrut`) and sales (`sale-02`). Suggested classification: C2. Future tools gate on `recrut`/`sales` business roles and on the ADR-0340 Workday capability scopes (`workday.profile.any.read` — read-only).
- **cognos** — board-only financial and strategic assistant. Answers Direction-level financial and strategic questions with access to a large tool set (RAG, MCP) explicitly excluding technical tools and the technical RAG corpora. Audience: `board` only. Suggested classification: C3.

Scope of this decision: Keycloak groups `agent_soursage`/`agent_cognos`, public clients `soursage-frontend`/`cognos-frontend` (comage pattern, including the `oidc-group-membership-mapper` with `full.path: "true"`), OKF placeholder bundles `agents/soursage/` and `agents/cognos/`, and `docs/agents/` stubs. No deployment chart, no tool-policy entries yet.

### 7. Group propagation contract

A single validated `groups` JWT claim remains the only propagation vehicle for identity across the platform: agent BFF entitlement (`components/agent-bff/main.go`), the MCP Gateway policy intersection (`components/mcp-gateway/app/policy.py` against `policies/tools/tool-policy.yaml`), RAG ACL filtering (`acl_groups`), and OpenShift `Group` objects (bare-path mapper on the `openshift` client). The same claim is the designated hook for future connectivity-link (Kuadrant `AuthPolicy`), MaaS and API-gateway enforcement — none of which exists yet in this repo (`gitops/charts/connectivity-link/templates/kuadrant.yaml` renders an empty spec); when those policies are authored, they must consume this claim rather than introduce a parallel identity store (consistent with ADR-0202/0340).

## Alternatives considered

- **Hyphen-renaming the `agent_*` groups** to match the requested `agent-<name>` spelling — rejected: coordinated churn across the BFF, five OKF bundles, tool-policy, rag-ingestion ACLs and both evaluation suites for zero functional gain.
- **Literal `secretdemerde` in `realm-zuno.json`** — rejected: reverses ADR-0041's no-static-passwords-in-Git rule for no benefit over the Vault-seeded default.
- **Per-user Vault seeds** (one key per persona plus per-user vault-SPI files) — rejected: fifteen keys of machinery for the same effective result, since live passwords diverge in Keycloak's database regardless of the init path.
- **Keeping `zuno-admin`/old platform groups alongside the new `ocp-*` groups** — rejected: two overlapping naming schemes for one dimension.
- **A group-sync operator or static `Group` CRs** — rejected: OAuth login-time sync (`mappingMethod: add`, `claims.groups`) already maintains membership.

## Consequences

This ADR supersedes ADR-0320's persona and platform-group model (`admin`, `zuno-admin`, `aidev`, `aiops` and the four ADR-0320 demo personas); ADR-0320's OAuth identity-provider configuration, confidential `openshift` client and static-RBAC mechanism remain in effect and are only re-targeted. It advances one element of ADR-0340 ahead of its v0.3 target (board stops being the architect container) without touching that ADR's `cdp` or capability-scope decisions.

Documented limitation: `ai-dev-01`, `ai-ops-01`, `paas-dev-01` and `paas-ops-01` hold `agent_tekos` but no business role. They can open Tekos and chat (BFF entitlement passes), but consultant/board-gated tools deny with 403 and ACL-scoped RAG returns nothing — the same shape ADR-0040's `tekos-entitlement-only-user-01` fixture tests. This is intended for now and revisited when `tool-policy.yaml` learns about the new groups.

Implementation lands as follow-up work packages touching: `gitops/charts/keycloak/files/realm-zuno.json` (users, groups, two clients); `gitops/charts/openshift-rbac-groups/templates/{clusterrolebinding,rolebindings}.yaml`; `ansible/roles/argocd/kustomize/argocd/argocd.yaml`; `ansible/inventories/demo/group_vars/all/auto.yml`; `agents/{soursage,cognos}/` OKF bundles and `docs/agents/` stubs; `evaluations/tekos/{scenarios.yaml,run_scenarios.py,security_checks.py}` (renamed usernames); `gitops/charts/rag-ingestion/values.yaml` (archi group paths); and the doc-count drift already present in `ansible/roles/keycloak/README.md`, `gitops/charts/keycloak/templates/externalsecret-demo-personas.yaml`, `platform/identity/README.md` and `MEMORY.md`.

## Security considerations

Two cluster-admin paths exist after this change: the `ocp-paas-ops` group and the ArgoCD application-controller ServiceAccount — both deliberate and reviewable. `cluster-reader` for `ocp-paas-dev` exposes cluster-wide read (including nodes, operators and most CRs) and is an accepted, explicit grant. `secretdemerde` is a demo-grade initialization value: it must be treated as compromised from day one, each persona's password should be changed in Keycloak, and no password value ever lands in Git (ADR-0041) or bypasses Vault seeding (ADR-0024). The negative-test fixtures and their two security checks are preserved so the entitlement/business-role boundary keeps regression coverage.

## Operational considerations

`KeycloakRealmImport` is create-only: on a cluster where the `zuno` realm already exists, these changes require re-provisioning the realm (or applying them manually via the Keycloak admin API); a fresh `make d0` deployment picks them up automatically. Vault seeding is idempotent (ADR-0345), so an existing install keeps the old demo-personas password until the operator deletes `zuno/keycloak/demo-personas` and re-runs the seed. Renaming groups leaves stale OpenShift `Group` objects (`admin`, `zuno-admin`, `aidev`, `aiops`) from prior logins; they carry no RBAC after this change but should be cleaned up manually once.

## Implementation state

This ADR records an agreed architectural change from the 2026-08-14 persona review. No implementation is claimed by this ADR. The status remains `Proposed` until the realm, RBAC, ArgoCD, Vault-seed, OKF and evaluation changes land through follow-up work packages and `make check` demonstrates the behavior described here.

### Implementation note (2026-08-15)

The repo side is merged, in two commits (soursage/cognos first, then the persona/RBAC restructure). Because this ADR was written on 2026-08-14 — before WP-33 through WP-42 landed — four deliberate, documented deviations reconcile it with what the repository had become by implementation time; none changes the ADR's direction:

1. **`finance-01`/`finance-02` are kept** (renamed from `finance-user-0N`, still `/finance` + `/agent_finage`). The ADR removed them when Finage was a placeholder; WP-36 then made Finage a real agent whose tools gate on the `finance` role and whose 20-scenario suite authenticates finance personas — removing every `finance` member would have orphaned a working slice. The ADR's own reasoning ("/finance survives because tool-policy references it") extends naturally to keeping the members that exercise it.
2. **All 11 ADR-0040 negative-test fixtures are kept**, not just the two the ADR names — WP-31/33/35/36/41 each added an entitlement-only (and most a role-only) fixture that its agent's own `security_checks.py` authenticates. Same "no other persona can exercise this check" logic the ADR itself applied to `consultant-role-only-user-01`.
3. **`consultant-01` additionally holds `/agent_naveo` and the persona/client model covers naveo/soursage/cognos** — Naveo (WP-41) postdates the ADR's matrix; the two new agents' clients follow the original public-SPA placeholder pattern the ADR describes via "comage pattern" (comage has since become confidential, as every built agent's frontend must be).
4. **Arkos's audience followed the archi-tier move**: with the `confluence-archi-*` subgroups under `/consultant` and `agent_arkos` carried by `consultant-01/02` (this ADR's own matrix gives `board-01/02` no `agent_arkos`), Arkos's business role is now `consultant` — its bundle/chart/CR-sample prose and its evaluation suite moved accordingly, and the advantage/finage "tile disabled for a board persona" negative scenarios were repointed at genuinely non-entitled personas since `board-01` now legitimately holds `agent_advantage`/`agent_finage`. The `/board`→`/consultant` archi-group migration itself had already landed via WP-32.

Also merged: the four `ocp-*` groups + `/recrut` (old `admin`/`zuno-admin`/`aidev`/`aiops` groups and `platform-admin-01`/`zuno-admin-01` removed), the `openshift-rbac-groups` chart rewiring (`ocp-paas-ops`→cluster-admin, `ocp-paas-dev`→cluster-reader, `ocp-ai-dev`→edit and `ocp-ai-ops`→admin ranged over the discovered namespace set), the ArgoCD `rbac.policy` block from §5, `zuno_admin_demo_personas_root_password: "secretdemerde"` decoupled in `auto.yml`, the 107 persona-reference renames across all six evaluation suites, and the doc-count refresh (`ansible/roles/keycloak/README.md`, `externalsecret-demo-personas.yaml`, `platform/identity/README.md`, `MEMORY.md`).

Remaining to close (live): realm re-apply (`KeycloakRealmImport` is create-only — re-provision or apply via the admin API on an existing cluster), delete the stale `admin`/`zuno-admin`/`aidev`/`aiops` `Group` objects, delete + re-seed `zuno/keycloak/demo-personas` for the new init password, then verify: an `ocp-paas-ops` login reaches cluster-admin + ArgoCD `role:admin`, `ocp-paas-dev` reads cluster-wide + syncs zuno apps, the AI profiles get their namespace-scoped roles, a renamed persona receives mail at its plus-address, and `make check` passes with the renamed personas.

See [Standard clauses](README.md#standard-clauses) for Acceptance criteria, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0012](0012-use-keycloak-as-the-central-identity-provider.md) (the identity provider this decision builds on)
- [ADR-0024](0024-use-vault-for-application-secrets.md) (the Vault-only credential convention the initial password follows)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md) (the two-dimension group model whose membership matrix this ADR redefines)
- [ADR-0041](0041-remove-nominative-demo-identities-and-static-passwords-from-git.md) (the anonymized-persona/no-static-password convention preserved here)
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md) (the database where live per-user passwords reside)
- [ADR-0320](0320-pre-provision-openshift-users-rbac-and-console-favorites-via-keycloak.md) (the platform-group/persona model this ADR supersedes; its OAuth/RBAC mechanisms remain)
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md) (the persona-scoped Confluence ACL subgroups whose archi tier moves to consultants)
- [ADR-0332](0332-remove-console-favorites-provisioning.md) (the earlier partial supersession of ADR-0320)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md) (the board-de-architecting direction this ADR advances; `cdp` and capability scopes stay at v0.3)
- [ADR-0345](0345-make-self-generated-vault-credentials-idempotent.md) (why an existing install keeps the old seeded password until reseeded)
