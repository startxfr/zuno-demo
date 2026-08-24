# WP-074: mcp-aap server - expose AAP audits to Tekos and Arkos

- **State:** Not started.
- **ADRs:** ADR-0355 (Expose AAP audits to agents through an mcp-aap
  server)
- **Depends on:** WP-072 (`aap` live), WP-073 (`aap-config`'s Project/Job
  Template live, and a Controller API token minted for this server).
- **Unblocks:** none yet named; a future ADR-0418 phase could reuse this
  server's launch pattern for other Job Templates once proven.
- **Estimated files touched:** ~14 (scaffolded server: ~5, chart: ~5,
  apps: 2, bindings/policy/OKF wiring: ~4, mcp role: 1).

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
- A Controller API token scoped to launch only `zuno-day0-check` and read
  platform status exists (minted during WP-073's setup, per ADR-0355
  clause 3) and is seeded to Vault KV `zuno/aap/mcp-token`. If it does
  not yet exist, seed it first following
  `ansible/tasks/vault_seed_if_missing.yml`'s pattern - do not reuse
  `zuno/aap/admin` for this server under any circumstance.
- Read `components/mcp-servers/git-forge/server.py` and
  `gitops/charts/mcp-git-forge/` in full - the closest existing precedent
  for a server wrapping a control-plane API rather than a document store.
- `python3 platform/docs/check_docs.py` exits 0.

## Repo changes (step by step)

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
   - `policies/tools/tool-policy.yaml`: `aap.cluster.audit` restricted to
     the same admin-ish `allowed_groups` a human launching this Job
     Template through Controller's own RBAC would need - never broader.
     `aap.platform.audit` may sit at a lower classification/broader
     group set, but both must be reviewed against ADR-0011's policy
     intersection, not just added by pattern-matching an existing entry.
   - `agents/tekos/tasks/*.md` and `agents/arkos/tasks/*.md`: add a new
     task (or extend an existing infra/ops-oriented task) with
     `zuno.allowed_tools` naming the capabilities each agent actually
     needs - do not grant both tools to both agents by default without
     checking whether each agent's role justifies `aap.cluster.audit`
     specifically.
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
6. `python3 platform/docs/check_docs.py` exits 0.

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
