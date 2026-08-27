# WP-074: mcp-aap server - expose AAP audits to Tekos and Arkos

- **State:** Repo work merged, live verification pending (2026-08-27).
- **ADRs:** ADR-0355 (Expose AAP audits to agents through an mcp-aap
  server)
- **Depends on:** WP-072 (`aap` live), WP-073 (`aap-config`'s Project/Job
  Template live, and a Controller API token minted for this server).
- **Unblocks:** none yet named; a future ADR-0418 phase could reuse this
  server's launch pattern for other Job Templates once proven.
- **Estimated files touched:** ~14 (scaffolded server: ~5, chart: ~5,
  apps: 2, bindings/policy/OKF wiring: ~4, mcp role: 1). **Actual: ~28** -
  the estimate missed the AAP-identity work in `aap_config` (see the
  Preconditions correction below) and the four registration points
  `platform/supply-chain/check_mcp_server_conformance.py` enforces
  (`check_workload_hardening.py`'s two chart lists,
  `.github/workflows/lint.yml`, `tag_local_release.py`).

> Execute this brief as a standalone task from the repository root. Read
> ADR-0355 in full before starting. This WP introduces the first
> agent-reachable capability in this repository that launches cluster
> automation rather than only reading state - treat the authorization
> wiring (step 5) as load-bearing, not boilerplate.

## Goal

Scaffold and deploy `mcp-aap`, an MCP server exposing two capabilities to
Tekos and Arkos:

- `aap.platform.audit` - read-only Gateway/Controller API summary
  (component health, Project sync status, recent Job Template runs).
- `aap.cluster.audit` - launches the `zuno-day0-check` Job Template
  (WP-073) via the Controller API, waits for completion, returns a
  summarized result.

## ADR references

Primary: [docs/adr/0355-expose-aap-audits-to-agents-through-an-mcp-aap-server.md](../../adr/0355-expose-aap-audits-to-agents-through-an-mcp-aap-server.md) -
read all 5 Decision clauses and the Security considerations section.

Related: ADR-0011 (policy intersection), ADR-0037 (network/workload
identity boundary), ADR-0116 (capability/binding split), ADR-0119
(scaffolding), ADR-0208 (service-identity credential mode), ADR-0354
(the `aap`/`aap-config` prerequisites).

## Preconditions (verify before starting)

- WP-072 and WP-073 both `Done`, live-verified.
- ~~A Controller API token scoped to launch only `zuno-day0-check` and
  read platform status exists (minted during WP-073's setup, per ADR-0355
  clause 3) and is seeded to Vault KV `zuno/aap/mcp-token`.~~

  **This precondition was false and is corrected here.** No such token,
  user, team or role assignment existed anywhere in the repository or the
  cluster. WP-073 minted only `zuno/aap/controller-token`, which despite
  its narrow description is an **admin** token: `POST
  /api/gateway/v1/tokens/` mints for the authenticated user, and that
  call authenticates as `admin`. Reusing it would have been the same
  mistake as reusing `zuno/aap/admin`, just less obviously.

  Building the least-privilege identity is therefore part of this WP -
  see step 0 below. `zuno/aap/admin` is never used by this server.
- Read `components/mcp-servers/git-forge/server.py` and
  `gitops/charts/mcp-git-forge/` in full - the closest existing precedent
  for a server wrapping a control-plane API rather than a document store.
- `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

0. **Mint the least-privilege AAP identity** in
   `ansible/roles/aap_config/tasks/install.yml` (added by this WP - see
   the Preconditions correction). AAP 2.5+ RBAC shape, verified live
   against 2.7 before writing any of it:
   - `/api/controller/v2/role_metadata/` lists `awx.execute_jobtemplate`
     as assignable on content type `awx.jobtemplate`, so a role scoped to
     ONE Job Template object is supported. That object-scoped grant is
     what bounds `aap.cluster.audit` on the AAP side.
   - the read half is the Gateway user's own `is_platform_auditor` flag,
     the platform-native spelling of the managed "Platform Auditor" role
     (`awx.view_jobtemplate`/`view_project`/`view_inventory` +
     `shared.view_organization`). "Organization Viewer" grants only
     `shared.view_organization`/`view_team`, and `zuno-day0-check` has
     `organization: null`, so org-scoped roles never reach it.
   - users are **gateway** resources (same lesson as organizations in
     WP-073) and sync down into Controller with a *different* id, so the
     role assignment resolves the Controller-side id rather than reusing
     the gateway one.
   - the token is minted by authenticating **as `zuno-mcp`**, not admin.
   Every step is check-first, so re-running the role is a no-op.

1. **Scaffold.** `make new-mcp-server` (or
   `platform/scaffolding/new_mcp_server.py` directly) targeting `aap`,
   generating `components/mcp-servers/aap/`, `gitops/charts/mcp-aap/`,
   `gitops/apps/mcp-aap/`. Do not hand-write the boilerplate the
   scaffolder already produces (transport, `GatewayTokenMiddleware`,
   `/healthz`, `TransportSecuritySettings`).
2. **Implement the two tools** in
   `components/mcp-servers/aap/server.py`:
   - `aap.platform.audit`: GET calls against the Controller/Gateway API
     for component readiness, Project sync state, recent job history.
     No write calls.
   - `aap.cluster.audit`: POST to launch `zuno-day0-check`, poll job
     status until terminal, return a summarized pass/fail with key
     findings. Surface a clear error (not a silent timeout) if the
     Controller is unreachable or the token has expired, per ADR-0355's
     Operational considerations.
3. **Credential.** `gitops/charts/mcp-aap/templates/externalsecret.yaml`
   from `zuno/aap/mcp-token`, following
   `gitops/charts/mcp-git-forge/templates/externalsecret.yaml`'s shape.
4. **Deploy wiring.** Add `mcp-aap` to the Day 2 `mcp` role's server list
   (`ansible/roles/mcp/tasks/install.yml`), applying its `-d0`/`-d1`
   Application pair like `mcp-confluence`/`mcp-git-forge` already do.
   Build via `ansible/roles/mcp_build/tasks/build.yml`'s existing
   BuildConfig path - push to `origin/main` before triggering the
   in-cluster build (it clones from there, not the local tree).
5. **Authorization wiring (the five-factor chain) - do this precisely,
   it is the security-relevant part of this WP:**
   - `platform/bindings/tools/tool-bindings.yaml`: both capabilities,
     `transport: streamable-http`, backend `mcp-aap` at
     `http://mcp-aap.zuno-ai-run.svc:8000`.
   - `policies/tools/tool-policy.yaml`: both capabilities at `C2`,
     `allowed_groups: [consultant, board, cdp]`. **Deliberately
     identical, amending ADR-0355 clause 4** - this realm has no admin
     group to narrow to (`ocp-paas-ops` is an OpenShift RBAC group, not
     a zuno business group), so the read/action line is drawn at the
     agent declarations and at the server's own construction instead.
     That is already the accepted pattern for `git.repository.private.*`.
     See the block comment on the two entries, and ADR-0355 clause 4.
   - Agent declarations - this is where the read/action line actually
     holds, so it is load-bearing rather than bookkeeping:
     `agents/tekos/tasks/answer-technical-question.md` gets BOTH
     capabilities (its "is the cluster healthy right now?" case is the
     one no other agent's task set covers);
     `agents/arkos/tasks/draft-architecture-testimonial.md` and
     `workshop-presentation.md` get `aap.platform.audit` ONLY - an
     architecture-drafting task cannot justify launching automation.
   - `python3 platform/okf/generate_authorization_matrix.py` - regenerate
     and verify the new tools appear correctly scoped in both agents'
     `agent.okf.md`.
6. **Network policy.** `gitops/charts/namespaces/values.yaml`: add
   `zuno-ai-run` to `zuno-aap`'s `allowedFromNamespaces` (ADR-0354 clause
   3 explicitly deferred this edit to this ADR/WP).

## What NOT to touch

- Do not grant `aap.cluster.audit` to any agent whose task set does not
  clearly need it.
- Do not reuse `zuno/aap/admin` as this server's credential.
- Do not add capabilities for any Job Template beyond
  `zuno-day0-check` - WP-073's scope boundary carries forward here.
- Do not let `/healthz` depend on Controller reachability (ADR-0037's
  pattern - a Controller outage must degrade only this tool, not the
  gateway's own liveness).
- Do not widen `zuno-aap`'s `NetworkPolicy` beyond adding `zuno-ai-run`.

## Acceptance checks

1. `oc get applications.argoproj.io -n openshift-gitops mcp-aap-d0
   mcp-aap-d1` Synced/Healthy.
2. Through the MCP gateway, call `aap.platform.audit` as an authorized
   agent - returns live component health/Project sync/job history.
3. Call `aap.cluster.audit` as an authorized agent - launches
   `zuno-day0-check`, returns a summarized result matching a manual
   Controller-UI launch of the same template.
4. Call both tools as an **unauthorized** group/agent - both calls are
   rejected by policy, not merely by AAP-side RBAC (defense in depth,
   per ADR-0355's Security considerations).
5. `python3 platform/okf/generate_authorization_matrix.py` output shows
   the expected tools on the expected agents, nothing broader.
   **Done (repo):** `aap.cluster.audit` appears on Tekos only,
   `aap.platform.audit` on Tekos + Arkos, on no other agent.
6. `python3 platform/docs/check_docs.py` exits 0. **Done (repo)**, along
   with `check_mcp_server_conformance.py` (48/48),
   `check_workload_hardening.py` (9/9 on `mcp-aap`),
   `components/mcp-servers/aap/tests/test_mcp_protocol.py` (13/13) and
   `components/mcp-gateway/tests/test_bindings.py`.

## Operator / human follow-up

1. Deploy the GitOps change, confirm the build (push-before-build).
2. Run one authorized and one unauthorized call of each tool live,
   confirm the expected allow/deny outcome.
3. Confirm `zuno-day0-check`'s live output via `aap.cluster.audit` matches
   a local `make d0 check` run.

## Status updates

On repository merge but before live confirmation:

- WP-074 -> `Repo work merged, live verification pending`.

After all live acceptance checks pass:

- WP-074 -> `Done`.
- ADR-0355 -> `Implemented`.
- Update `docs/roadmap/v0.1-v0.3-implementation-roadmap.md` and
  `MEMORY.md`.

## Rollback

1. Remove the tool grants from `agents/tekos/tasks/*.md`/
   `agents/arkos/tasks/*.md` and regenerate the authorization matrix -
   this alone stops agents from reaching either capability even if the
   server keeps running.
2. `make day2 uninstall mcp-aap` (or the equivalent `mcp` role target) to
   remove the server entirely.
3. Revert the Git commit if the chart/role itself is at fault.

## Out of scope / deferred

- Any Job Template beyond `zuno-day0-check`.
- Routing `make day0|d0`/`make day1|d1` execution through AAP - ADR-0418
  (v0.4).
- Extending `aap.cluster.audit`-style launch capabilities to other
  agents beyond Tekos/Arkos.
