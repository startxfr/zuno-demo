# WP-222: Quick security wins: audience flag, admin authentication, CQL escaping, secret scan, action pins (delivers ADR-0602, ADR-0603)

- **State:** Done (2026-11-07, user decision). The repo work is merged into `devel` locally (not pushed). Named
  exception: the live checks of the rollout (audience refusal, admin routes, Confluence CQL) are not run; the user
  closed the package without them. The push, the in-cluster build of both gateways and the ArgoCD sync still wait for
  the user's go.
- **ADRs:** ADR-0602, ADR-0603
- **Depends on:** none
- **Blocks:** WP-227
- **Estimated files touched:** ~25 (plus 1,902 untracked venv files)

> Execute this brief as a standalone task from the repository root.

## Goal

Land the findings that need no design decision: gateway token audience, authenticated admin routes, a closed CQL
injection, capped model-chosen sizes, a secret scan, SHA-pinned actions and a virtual environment out of git.

## ADR references

ADR-0602 clauses 6 and 7; ADR-0603 clause 1 (M10, M11, M19, M21).

## Decisions taken with the user (2026-11-06)

- **Audience: reuse `zuno-admin-api`, active.** The `maas-gateway-audience` mapper of `realm-zuno.json` already adds it to
  every experience client, and a2a-gateway already requires it. `openshift`, `aap` and `zuno-signer` lack it, so their
  tokens are refused. No Keycloak change: `job-client-reconcile.yaml` already applies the realm's clients live. OpenShift
  opaque tokens on the `/mcp` front door go through TokenReview, not JWT validation, and are unaffected.
- **Admin routes: `enforce` by default**, groups `ocp-paas-ops,ocp-ai-ops`; `ADMIN_AUTH_MODE=off` is the visible opt-out.
- **Same pinning and secret scan in zuno-demo-agents** (branch `wp-222-action-pins`, local commit, not pushed).

## Repo changes

1. `components/{ai-gateway,mcp-gateway}/app/auth.py`: `JWT_AUDIENCE_REQUIRED` (module import raises when it is true and
   `JWT_AUDIENCE` is empty), `admin_groups()` (`ADMIN_GROUPS`) and `require_admin`.
2. `components/ai-gateway/app/main.py`: `Depends(require_admin)` on the five `/admin/*` routes;
   `components/mcp-gateway/app/main.py`: the same on `/admin/reload-policy`.
3. `gitops/charts/{ai-gateway,mcp-gateway}`: `jwtAudience: zuno-admin-api`, `jwtAudienceRequired: true`, rendered as env
   `JWT_AUDIENCE` and `JWT_AUDIENCE_REQUIRED` (same pattern as `gitops/charts/a2a-gateway`).
4. Model-chosen inputs: Confluence `space` must match `[A-Za-z0-9_~-]{1,64}`, the CQL literal is escaped
   (`_cql_escape`) and `limit` is capped at 50 (`components/mcp-servers/confluence/server.py`); the Salesforce SOQL
   `LIMIT` is capped at 50; `rag_query` `top_k` is capped at `MAX_TOP_K = 20`
   (`components/mcp-gateway/app/handlers/rag_query.py`).
5. Tests: `tests/test_wp222_audience_and_admin.py` in both gateways, `components/mcp-servers/confluence/tests/test_wp222_cql.py`,
   `test_wp222_top_k_is_capped` in `components/mcp-gateway/tests/test_rag_query.py`.
6. CI: every action pinned by the commit SHA of its tag (tag kept as a comment); `permissions: contents: read` on
   `lint.yml`; new `.github/workflows/secret-scan.yml` (gitleaks 8.21.2, checked against the release checksums, full
   history); new `.pre-commit-config.yaml`.
7. `.gitignore`: `.venv*` (also matches a symlinked venv); `evaluations/.venv-gate` (1,902 files, referenced by nothing) is untracked. History is not purged.
8. zuno-demo-agents (branch `wp-222-action-pins`): the five workflows' actions pinned by SHA, the same `secret-scan.yml`
   (also on `stable`) and `.pre-commit-config.yaml`.

## Verification (2026-11-06)

- **Tests.** ai-gateway 376 passed, 1 failed; mcp-gateway 126 passed, 12 failed, 4 errors. The failing set is identical,
  name for name, to a worktree of `devel` at 4dd321cc (372 and 121 passed there): the 4 and 5 new tests pass and nothing
  else moved. The Confluence CQL test passes (3 cases).
- **Charts.** `helm template` renders `JWT_AUDIENCE="zuno-admin-api"` and `JWT_AUDIENCE_REQUIRED="true"` for both charts.
- **Checks.** `check_docs.py` PASS, `check_unifai_pins.py` PASS. `check_no_latest_tags.py` (13 hits) and
  `check_workload_hardening.py` (the keycloak chart's `helm template` error) fail identically on `devel` before this change.
- **gitleaks 8.21.2 run locally:** zuno-demo history (2,432 commits) no leaks; zuno-demo-agents history no leaks; the files
  this package adds, no leaks. The run caught a defect in the first draft of the workflow (the archive was saved as
  `gl.tgz`, so `sha256sum -c` could not find the file the checksum names); fixed, and the install step was replayed locally.
- **Live, read-only, demo333.** The 12 live clients of realm `zuno` match `realm-zuno.json`: every experience client
  carries `zuno-admin-api`; `openshift`, `aap`, `zuno-signer` and `zuno-admin-api` itself do not. Prometheus
  `zuno_model_tokens_total` over 7 days shows the ai-gateway's callers: dify, kagent, open-webui, openclaw-consultant-02,
  openclaw-sale-01, unifai, zuno-evaluations, all carrying the audience. Residual gap: the mcp-gateway's metrics carry no
  client label; its known callers (the same experience clients, UnifAI with user tokens, a2a-gateway forwarding them,
  Lightspeed with opaque OpenShift tokens) carry the audience or skip JWT validation.

## Rollout (needs the user's go; live checks waived at closure)

1. Push, merge to `devel` then `main`, build `ai-gateway` and `mcp-gateway` in-cluster, sync both Applications.
2. Live checks: an `aap` client token gets 401 on both gateways; a `unifai` or `open-webui` token gets 200;
   `/admin/reload-routing` without a token gets 401, with a `consultant` token 403, with an `ocp-paas-ops` token 200;
   `zuno_model_tokens_total` keeps growing for every client listed above.
3. Back-out: `jwtAudience: ""` with `jwtAudienceRequired: false`, and/or `ADMIN_AUTH_MODE=off`, then sync.

## Not done here

- Blocking `/v1/messages` and `/v1/responses`: WP-220 verified those paths on purpose; metering belongs to WP-225.
- Issuer and audience pinning in Authorino (the quota route) and JWKS over HTTPS: WP-224.

## Review fixes (2026-11-07)

A read-only review by a second session found the points below. Each one is fixed in a separate commit on the same branch.

- **Stale comment:** both `auth.py` files claimed the audience flag "stays off". The charts set it, and the comment now
  says so.
- **`/admin/reload-policy` takes Keycloak JWTs only:** an OpenShift or ServiceAccount token gets `401`, unlike `/mcp`.
  This is now stated in the `main.py` docstring and in both gateway READMEs, which also describe `ADMIN_GROUPS` and
  `ADMIN_AUTH_MODE`.
- **Confluence:**
  - Personal space keys (`~john.doe`, `~557058:…`) are now accepted. A quote or a space still fails.
  - `read_page` and `update_page` reject any `page_id` that is not numeric before it reaches a URL path.
- **Salesforce:** the `LIKE` wildcards `%` and `_` are escaped. The ceiling is the named constant
  `MAX_OPPORTUNITY_LIMIT`.
- **`rag_query`:** a non-numeric `top_k` falls back to 5 instead of raising.
- **`secret-scan.yml`:**
  - Pull requests and pushes scan only the commits they bring, so an old, already-rotated finding no longer blocks
    unrelated work. A weekly run and a manual run scan the whole history.
  - The version is set once in `GITLEAKS_VERSION`. `.gitleaks.toml`, added in WP-223, is read automatically.
- **`.gitignore`:** `.venv*` was too broad and is now `.venv` plus `.venv-*/`.
- **Not changed:**
  - The duplicated `auth.py`: the duplication is deliberate and documented in the module docstring.
  - `importlib.reload` in the audience test: it is the only way to test an import-time guard.
- **Verification:**
  - New tests for personal space keys, numeric `page_id` and a non-numeric `top_k` all pass.
  - The gateway suites keep the same failing set as before (ai-gateway 376 passed / 1 failed, mcp-gateway 127 passed /
    12 failed / 4 errors, all pre-existing).
  - A local gitleaks run on the branch's commit range finds no leaks.
