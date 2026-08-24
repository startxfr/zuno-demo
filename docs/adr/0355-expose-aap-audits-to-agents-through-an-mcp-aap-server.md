# ADR-0355: Expose AAP audits to agents through an mcp-aap server

- **Status:** Proposed
- **Target:** v0.3
- **Date:** 2026-08-24
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0354 (v0.2) delivers Ansible Automation Platform (`aap`) as a running
Day 1 component with one registered artifact: a Job Template,
`zuno-day0-check`, running `ansible/playbooks/day0_check.yml` against this
OpenShift cluster. Today, launching or reading that Job Template - or
anything else about the AAP platform itself (component health, recent job
history, registered projects) - requires an interactive login to the
Controller/Gateway UI or a direct API call. No agent can reach it.

This repository already has a full, standard pattern for making a new
capability reachable by agents (ADR-0116's capability/binding split, the
tool-policy authorization model of ADR-0011, and ADR-0119's scaffolding):
`platform/scaffolding/new_mcp_server.py` (also `make new-mcp-server`)
generates a new MCP server from the `confluence` template - real `mcp` SDK
server at `/mcp`, `GatewayTokenMiddleware` (ADR-0037's workload-token
boundary), a `/healthz` that never touches the backend, and one credential
from Vault in `service-identity` mode (ADR-0208). `components/mcp-servers/
git-forge/` is the closest existing precedent for a server that wraps a
git-hosted control plane's API rather than a document store. Registered
servers deploy through the Day 2 `mcp` role
(`ansible/roles/mcp/tasks/install.yml`), which already applies each
server's `-d0`/`-d1` ArgoCD Application pair.

## Decision

1. **A new MCP server, `mcp-aap`**, scaffolded via `make new-mcp-server` at
   `components/mcp-servers/aap/`, with chart `gitops/charts/mcp-aap/` and
   apps `gitops/apps/mcp-aap/`, deployed by the existing Day 2 `mcp` role
   (added to its server list alongside `mcp`, `mcp-confluence`,
   `mcp-git-forge`), reachable from `zuno-ai-run` at
   `http://mcp-aap.zuno-ai-run.svc:8000` per the gateway's `backends:`
   shorthand (`platform/bindings/tools/tool-bindings.yaml`).

2. **Two capabilities, one read-only and one action-capable, kept
   deliberately narrow:**
   - `aap.platform.audit` - **read-only.** Calls the AAP Gateway/Controller
     API to summarize component health (Gateway/Controller/Hub/EDA
     readiness), the Project's last SCM sync result, and recent Job
     Template run history. No state changes.
   - `aap.cluster.audit` - **action-capable.** Launches the
     `zuno-day0-check` Job Template via the Controller API, polls until
     the run completes, and returns a summarized result (success/failure,
     key findings). This is the first agent-reachable capability in this
     repository that runs arbitrary automation against the cluster rather
     than reading state - `day0_check.yml` is chosen specifically because
     it is read-mostly and safe to re-run (the same property ADR-0418
     uses to justify making Phase 1 of AAP-routed execution start there),
     but the capability's shape (launch a Job Template, wait, report) is
     generic and could point at a more consequential playbook in the
     future. This ADR authorizes launching `zuno-day0-check` only.

3. **Authentication: a scoped AAP token, not the admin credential.**
   `mcp-aap`'s credential is a Controller API token tied to a
   least-privilege AAP user/team that can launch `zuno-day0-check` and
   read platform status, generated during `aap-config`'s setup (WP-073)
   and seeded to Vault KV `zuno/aap/mcp-token`, delivered via the same
   `ExternalSecret` pattern every other MCP server credential already
   uses (e.g. `gitops/charts/mcp-git-forge/templates/externalsecret.yaml`).
   `zuno/aap/admin` (ADR-0354 clause 5) is never used by this server.

4. **Authorization wiring follows the standard five-factor chain**
   (`components/agent-runtime/app/registry.py`'s `declared_tools()`):
   - `platform/bindings/tools/tool-bindings.yaml` - both capabilities,
     `transport: streamable-http`, backend `mcp-aap`.
   - `policies/tools/tool-policy.yaml` - `aap.platform.audit` at a lower
     classification/broader `allowed_groups` than `aap.cluster.audit`,
     which is restricted to the same admin-ish groups AAP's own Controller
     RBAC (ADR-0418's Security considerations) would gate a human launch
     with, so the agent path is never more permissive than the human path.
   - Agent OKF task front-matter (`agents/tekos/tasks/*.md`,
     `agents/arkos/tasks/*.md`) - a new task per agent granting
     `zuno.allowed_tools: [aap.platform.audit, aap.cluster.audit]` (or a
     subset, per agent role).
   - `python3 platform/okf/generate_authorization_matrix.py` regenerated
     so each agent's `agent.okf.md` reflects the new tools.

5. **Network policy.** `aap`'s `zuno-aap` namespace (ADR-0354 clause 3)
   gains `zuno-ai-run` in its `allowedFromNamespaces` so `mcp-aap`
   (running in `zuno-ai-run`) can reach the Controller/Gateway API
   in-cluster - the one edit ADR-0354 explicitly deferred to this ADR.

## Consequences

- Agents gain their first cluster-automation-launching capability, not
  just a read/query one - a qualitative step up from every other MCP
  server registered so far (all read-only against documents/repos/CRM
  data). Policy and RBAC must both actively hold that line, not just the
  gateway's default posture.
- `mcp-aap` becomes a dependency of both `aap` (v0.2, for the Job Template
  it launches) and `aap-config` (v0.2, for the token it consumes) - it
  cannot ship before both are live.

## Security considerations

`aap.cluster.audit`'s launch path is the primary new attack surface: an
agent that can be tricked (prompt injection, compromised task definition)
into invoking it can trigger cluster automation. Mitigations: the AAP-side
token is scoped to launch only `zuno-day0-check`, never arbitrary Job
Templates; `tool-policy.yaml`'s `allowed_groups` for `aap.cluster.audit`
must match or be narrower than who could already launch it as a human
through Controller's own RBAC; the launched playbook itself
(`day0_check.yml`) is read-mostly by construction, so even a successful
misuse cannot mutate cluster state. Security-negative tests must prove an
unauthorized agent/group cannot reach `aap.cluster.audit` through the
gateway.

## Operational considerations

`mcp-aap`'s `/healthz` must not depend on Controller being reachable
(ADR-0037's pattern), so a Controller outage degrades this one tool rather
than the gateway's own liveness. Job Template launch failures (Controller
down, token expired, Project out of sync) must surface as a clear tool
error to the calling agent, not a silent timeout.

## Acceptance criteria

- The implementation is merged through the normal repository review
  process.
- Relevant documentation and `MEMORY.md` are updated to describe the
  implemented state rather than the target state.
- `platform/okf/generate_authorization_matrix.py`'s output and
  `platform/docs/check_docs.py` demonstrate the behavior described in this
  ADR.
- Security-negative tests are included proving `aap.cluster.audit` is
  unreachable outside its authorized groups, per the Security
  considerations above.

## Implementation state

**To be implemented.** This ADR records an agreed architectural decision.
Implementation lands via WP-074 under `docs/roadmap/work-packages/`, after
WP-072/WP-073 (ADR-0354) are live.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0119](0119-introduce-mcp-server-scaffolding-and-conformance-tooling.md)
- [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md)
- [ADR-0354](0354-add-ansible-automation-platform-as-a-day-1-component.md) (prerequisite, v0.2)
- [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md)

See [Standard clauses](README.md#standard-clauses) for Alternatives and
Review evidence.
