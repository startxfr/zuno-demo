# ADR-0603: Close the medium-severity security gaps found in the 2026-11-06 review

- **Status:** Accepted
- **Target:** v0.16 (retargeted from v0.15 on 2026-11-07, with ADR-0602: v0.15 became the demo-ready band of ADR-0605)
- **Date:** 2026-11-06
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md), [ADR-0052](0052-harden-all-workloads-for-openshift-restricted-security-and-secnumcloud-objectives.md), [ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [ADR-0595](0595-set-demo-passwords-from-one-shared-value-through-one-variable-per-component.md)

## Context

ADR-0602 holds the findings of the 2026-11-06 review that break a trust boundary. This ADR holds the rest: defects that
need a second weakness, a privileged position or a configuration mistake before they hurt a customer, plus the supply
chain and hygiene gaps. The review's limits are the same: code and charts were read, nothing was replayed, and every
`file:line` is to be re-read before it is fixed.

### Findings

**Network and transport**

| # | Finding | Evidence |
|---|---|---|
| M1 | NetworkPolicy is ingress-only on the platform baseline; egress is open, and `zuno-ai-run`, where agent workloads run, is excluded from the baseline | `gitops/charts/namespaces/templates/networkpolicy-platform.yaml:20-21`, `gitops/charts/namespaces/values.yaml:314` |
| M2 | PostgreSQL and MariaDB run with `DISABLE` in the mesh and `sslmode` is unconfirmed | `gitops/charts/postgresql/templates/destinationrule-postgres.yaml:59`, `gitops/charts/mariadb/templates/destinationrule-mariadb.yaml:23` |
| M3 | Ansible turns certificate verification off for credentialed calls (501 hits for `validate_certs: false`, `insecure`, `verify=False` outside tests, not triaged), including the Keycloak automation password grant | `ansible/roles/kagent/tasks/keycloak_sa_groups.yml:18-70`, `ansible/roles/aap_config/tasks/*` |
| M4 | The Keycloak HTTP listener admits any source (port 8080) | `gitops/charts/keycloak/values.yaml:56-60` |

**Identity and keys**

| # | Finding | Evidence |
|---|---|---|
| M5 | The realm import is create-only, so hardening added later never reaches an existing cluster; only clients are reconciled | `gitops/charts/keycloak/templates/realmimport.yaml:20-43` |
| M6 | Sessions: SSO idle 8 h, max 10 h, on a shared password | `realm-zuno.json:11-13` |
| M7 | The internal PKI root lives in Vault for 10 years with no offline root or intermediate; cert-manager's three Vault roles share one ServiceAccount, so it can sign Istio identities | `ansible/roles/vault/kustomize/unseal-configure/configmap.yaml:53-57,153` |
| M8 | The Vault UI is published on a public Route; OpenShift keeps an `htpasswd` identity provider next to OIDC | `gitops/charts/vault/templates/route.yaml:20-22`, `gitops/charts/openshift-oauth/templates/oauth.yaml:4-10` |
| M9 | Credentials appear in command strings of Vault seeding tasks (SMTP, RHN, Quay); `no_log` unconfirmed there | `ansible/roles/vault/tasks/install.yml:700,719,754` |

**AI and agent surface**

| # | Finding | Evidence |
|---|---|---|
| M10 | `/admin/*` of ai-gateway and mcp-gateway has no authentication and relies on NetworkPolicy | `components/ai-gateway/app/main.py:113-165`, `components/mcp-gateway/app/main.py:99` |
| M11 | CQL injection in `search_pages` (`space` and the query reach a quoted literal unescaped); `limit` is uncapped on Confluence and Salesforce; `top_k` of `rag_query` is uncapped | `components/mcp-servers/confluence/server.py:221-223`, `components/mcp-servers/salesforce/server.py:182` |
| M12 | Write tools take any target on a shared credential: git-forge `write_file`, `create_repository`, `fork_repository`; Confluence `create_page`, `update_page`; `email.report.send` | `components/mcp-servers/*` |
| M13 | The Kubernetes metrics tool needs a label matcher but not a namespace matcher, and the service account has cluster-wide monitoring view | `gitops/charts/mcp-k8s/templates/rbac.yaml` |
| M14 | Delegation chain headers are not bound to the token; the REST tool path (`/v1/tools/{name}/invoke`) trusts the declared agent while `/mcp` checks the entitlement | `components/a2a-gateway/app/agent_chain.py`, `components/mcp-gateway/app/main.py` |
| M15 | Per-user labels on metrics (cardinality and personal data); unbounded JSON-RPC batches; no per-caller limit on the AAP audit launch | `components/mcp-gateway` |

**Supply chain and hygiene**

| # | Finding | Evidence |
|---|---|---|
| M16 | First-party charts use `:latest` with `pullPolicy: Always`; the pinned-release ledger has `digest: null` entries and is consumed by no deployment; base images are not digest-pinned | `gitops/charts/mcp-gateway/values.yaml:9`, `platform/supply-chain/pinned-releases.yaml`, `components/*/Dockerfile` |
| M17 | `ClusterImagePolicy` runs in warn mode; images built by GitHub Actions are not signed (ADR-0535 removed CI signing) | `gitops/charts/namespaces/values.yaml:243,269`, `.github/workflows/build-publish.yml:1-12` |
| M18 | The cosign binary is downloaded without a checksum; Trivy ignores unfixed findings; SBOMs are artifacts, not attestations | `components/supply-chain-signer/Dockerfile:26,40`, `.github/workflows/build-publish.yml:229-231` |
| M19 | GitHub Actions are pinned by tag; `lint.yml` had no `permissions:` block; no secret scanner, Dependabot, CODEOWNERS or SECURITY.md | `.github/workflows/*.yml` |
| M20 | Python requirements are `==`-pinned without hashes and drift between components (fastapi 0.141.1 against 0.115.0, pydantic 2.13.4 against 2.9.2); `kubernetes.core` is unpinned | `components/*/requirements.txt`, `ansible/requirements.yml` |
| M21 | A virtual environment is tracked (`evaluations/.venv-gate`, 1,902 files) and the `.venv/` ignore rule misses it | `git ls-files evaluations/.venv-gate` |
| M22 | Plaintext copies of live-looking credentials sit on the maintainer's workstation (`ansible/confidential-*.back`). They are ignored by `.gitignore` and absent from history, and are listed here only because the ignore rule is the sole barrier | `.gitignore:13` |

## Decision

**Close every finding above through ADR-0602's baseline work packages where they share a file, and through WP-222 and WP-226
where they do not.**

1. **Quick wins first (WP-222).** M10 (admin authentication), M11 (CQL escaping, space-key check, caps), M19 (SHA-pinned
   actions, `permissions:` on `lint.yml`, a secret scan in CI and a pre-commit hook), M21 (untrack the virtual environment
   and ignore `.venv*/`). Each ships with a test that fails on the old behaviour.
2. **Network and identity (WP-224, WP-223).** M1 and M4 with the mesh work; M2 with database-native `sslmode=verify-full`;
   M5 through a reconcile job for realm settings; M6 to M8 with the Keycloak and Vault work; M9 by moving the values to
   files read by the task, with `no_log`.
3. **Delegated scope (WP-225).** M12 to M15 with the shared-credential and token-exchange work.
4. **Supply chain (WP-226).** M16 and M17 (digests rendered into chart values at release, `ClusterImagePolicy` in enforce
   after a dry run on warn, CI images signed keylessly), M18, M20 (hashed lockfiles, one version per library), and the
   triage of the 501 `validate_certs` hits (M3): each is fixed, or kept with an ADR-referenced reason for a lab-only
   path.
5. **M22 is the maintainer's action, not a work package.** The keys in `ansible/confidential-*.back` are rotated if
   they are live, and the files move to an `ansible-vault` or sops store.

## Alternatives considered

- **Fold these into ADR-0602.** One long record with ten critical and twenty-two lesser clauses hides which ones block a
  customer install. Rejected.
- **Triage the 501 `validate_certs` hits before deciding.** The count says a policy is needed, not which hit is wrong.
  The triage is a task of WP-226.
- **Dependabot or Renovate for everything.** Useful for actions and Python; it does not pin base images or charts by
  digest. Retained for actions and requirements only.

## Consequences

- Pinned actions and hashed lockfiles need a refresh routine. Without one they go stale and are bypassed.
- `ClusterImagePolicy` in enforce stops an unsigned CI image from starting. The warn-to-enforce step is rehearsed first.
- Untracking the virtual environment removes 1,902 files from the tree; history keeps them unless it is purged, which is a
  separate decision.

## Security considerations

The tag-to-SHA mapping of an action was resolved on 2026-11-06 from the public repository. If a tag had already been
moved, the SHA would pin the moved commit; review each pinned SHA against the release notes when the dependency routine
is first run.

## Operational considerations

`gitleaks` runs on every push and pull request over full history; its first run may report old, already rotated values,
which are allow-listed with a reason. Admin calls now need a token: use a token of an `ocp-paas-ops` user.

## Work packages

WP-222 (shared with ADR-0602), WP-226.

## Amendment (2026-11-07): retargeted to v0.16 with ADR-0602

This record follows [ADR-0602](0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md) into v0.16. No
decision clause changes.

- **Done or live on 2026-11-07:** WP-222; WP-223; the WP-224 rollout; the repository part of WP-226 (hashed lockfiles,
  already in the live ai-gateway image).
- **After the 2026-11-09 demonstration only:** the rest of WP-224, WP-225, and the live steps of WP-226
  (`ClusterImagePolicy` from warn to enforce, digests rendered into the charts, `zuno_validate_route_certs`). Each one
  rebuilds or rolls shared components, so none of them runs inside the freeze of
  [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md).

## Amendment (2026-11-11): M12 and M13 values decided

User decisions of 2026-11-11 (post-demo hardening list, item 4). Both are now values in git.

- **M13.** `metrics.query` is offered to `ocp-ai-ops` only. That group's PromQL is scoped to:
  - the 13 namespaces that mcp-k8s already reads;
  - `nvidia-gpu-operator`.
  The values are in `metricsQuery.namespacesByGroup` in `gitops/apps/mcp/application-d1.yaml`. The kagent service
  account carries `ocp-ai-ops`, so kagent keeps the tool. A node-level or cluster-level series, which has no
  `namespace` label, selects nothing.
- **M12.** The shared Confluence identity sees 42 spaces: 4 internal ones, about 12 customer or project spaces, and 26
  personal spaces. It can write to them.
  - `consultant`, `board`, `cdp` and `lightspeed_readonly` now reach only the four internal spaces: SXSI, SXS, SXSD
    and SAC.
  - `consultant`, `board` and `cdp` reach only `github:startxfr/*` on git-forge. The GitHub token is a fine-grained,
    public, read-only token, so this narrows reads.
  - The `"*"` entries of `sales`, `finance`, `adv` and `recrut` are removed. The tool policy gives those groups no
    Confluence or git tool.
  - A space or repository is added to a group when a flow needs it.
