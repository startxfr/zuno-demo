# WP-152: Evaluate the RHOAI MCP Gateway, else extend the mcp-gateway north side

- **State:** Repo work in review
- **ADRs:** [ADR-0571](../../adr/0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md)
- **Depends on:** none
- **Related:** [ADR-0043](../../adr/0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md), [ADR-0116](../../adr/0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md), [ADR-0036](../../adr/0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md), [ADR-0011](../../adr/0011-define-tool-authorization-as-policy-intersection.md), [ADR-0524](../../adr/0524-integrate-openshift-lightspeed-with-the-zuno-ai-platform.md), [WP-146](wp-146-unifai-identity-and-context-header-forwarding.md), [WP-151](wp-151-deploy-unifai-on-zuno-via-argocd.md)
- **Target:** v0.11
- **Estimated files touched:** branch A (RHOAI gateway) ~15 — a chart, small MCP servers for the built-in tools; branch B (extend ours) ~5 — `components/mcp-gateway/app/{mcp_frontdoor.py,main.py}`, tests, chart values.

> UnifAI's MCP client speaks MCP, while the mcp-gateway's agent-facing
> contract is REST. Before writing more gateway code, find out whether the
> platform already ships an MCP gateway that does the job.

## Goal

UnifAI agents reach every tool they are entitled to through one MCP
endpoint that enforces the full ADR-0011/ADR-0036 intersection for the
calling user and agent, and forwards the user's identity downstream — using
the RHOAI/Connectivity Link MCP Gateway if it covers that, the zuno
mcp-gateway otherwise.

## Steps

1. **Evaluate availability — on demo333 at its next power-on.** demo333 is
   powered off; ask the user to power it on. Run, with `--context` explicit:
   `oc --context <demo333-context> api-resources | grep -i mcp` and
   `oc --context <demo333-context> get csv -A | grep -i -E 'kuadrant|connectivity|rhcl|mcp'`.
   In parallel (offline), read the RHOAI 3.5 and Red Hat Connectivity Link
   documentation for an MCP Gateway feature. Record the exact CRD names,
   versions and support level (GA / Tech Preview / Developer Preview) found.
   Availability is unverified until this step is done.

2. **Coverage check against three requirements.** (a) aggregation of several
   MCP servers behind one endpoint with per-caller `tools/list` filtering;
   (b) authorization by Keycloak group and by agent entitlement, i.e. the
   whole intersection of ADR-0011 (read `components/mcp-gateway/app/policy.py`
   and `agent_declarations.py` for what that means concretely); (c)
   delegation of the user identity to downstream servers (read
   `components/mcp-gateway/app/delegation.py`). Write the result as a table
   in the PR description: requirement, covered yes/no, evidence.

3. **Branch A — the platform gateway covers all three.** Write a migration
   plan, not code, in this WP's follow-up: each built-in handler in
   `components/mcp-gateway/app/handlers/` (`image_gen.py`, `diagram_gen.py`,
   `gmail.py`, `drive.py`, `web_search.py`, `email_report.py`) becomes a
   small MCP server under `components/mcp-servers/<name>/` (the CI matrix
   discovers them automatically, see `.github/workflows/build-publish.yml`);
   `rag_query.py` is dropped in favour of UnifAI RAG (WP-149); the policy
   moves into the platform gateway's CRs. Stop here and ask the user before
   implementing.

4. **Branch B — it does not.** The mcp-gateway already has a standard MCP
   north side: `POST /mcp` in `components/mcp-gateway/app/main.py`, built by
   `components/mcp-gateway/app/mcp_frontdoor.py` for OpenShift Lightspeed
   (ADR-0524). It uses a deployment-time capability ceiling
   (`frontdoor_policy=True`) because Lightspeed has no OKF bundle. Extend
   it, do not add a second endpoint: when the request carries a valid user
   JWT and an `X-Zuno-Agent` header (forwarded by UnifAI per WP-146), apply
   the full per-agent intersection used by `/v1/tools/{name}/invoke`
   (`frontdoor_policy=False` path), keep the Lightspeed ceiling for callers
   without an agent. Never add a policy check in `mcp_frontdoor.py` itself —
   its docstring forbids a second authorization path. Forward the JWT
   downstream through the existing `delegation.py`.

5. **Branch B tests.** Extend `components/mcp-gateway/tests/test_mcp_frontdoor.py`:
   `tools/list` for agent tekos returns exactly its entitled tools; a call
   to a tool outside the intersection is refused; a caller in a group
   without the right is refused; a call without `X-Zuno-Agent` still gets
   the Lightspeed ceiling. Tests need a venv built from
   `components/mcp-gateway/requirements.txt`.

6. **NetworkPolicy.** The UnifAI peer on
   `gitops/charts/mcp-gateway/templates/networkpolicy.yaml` is added by
   WP-151; check it covers `/mcp` (same port).

## Progress (2026-10-22, demo333)

1. **Done: availability.** demo333 offers the OLM package `mcp-gateway`
   v0.7.1 from `redhat-operators`. It ships in channel `preview`, image
   `registry.redhat.io/rhcl-tech-preview/mcp-gateway-rhel9-operator`, and
   Red Hat calls it a Technology Preview. It is upstream
   [Kuadrant/mcp-gateway](https://github.com/Kuadrant/mcp-gateway) v0.7.1,
   which needs `kuadrant-operator >= 1.4.3`, Gateway API with Istio, and an
   EnvoyFilter. It owns `mcp.kuadrant.io/v1alpha1` `MCPGatewayExtension`,
   `MCPServerRegistration` and `MCPVirtualServer`. On demo333 it is not
   installed, and `rhcl-operator.v1.4.3` is stuck in `Installing`.
2. **Done: coverage check** (upstream tag v0.7.1; docs.redhat.com returned
   503, so the support wording comes from search results only):

   | Requirement | Covered | Evidence |
   |---|---|---|
   | (a) one MCP endpoint for many servers | yes | `docs/design/routing.md`; `MCPServerRegistration.spec.prefix` |
   | (a) `tools/list` per caller | partly | only with an Authorino-minted signed `x-mcp-authorized` header; `--enforce-capability-filtering` defaults to false; `MCPVirtualServer` hides tools without authorizing them |
   | (b) per-tool rights by Keycloak group | yes | AuthPolicy CEL on `x-mcp-toolname`/`x-mcp-servername` (`docs/guides/authorization.md`) |
   | (b) agent declaration and task rights (ADR-0011 factors 1-2) | no | nothing ships; it would be custom Rego/CEL, written twice (`tools/list` wristband and `tools/call`) with nothing keeping the two in step, over a header the gateway does not authenticate |
   | (c) user identity downstream | yes | the bearer token is forwarded by default; RFC 8693 is possible through Authorino (`docs/design/security-architecture.md`) |

   The gap is the agent part of (b). The user chose **branch B** on
   2026-10-22: extend the zuno mcp-gateway, and re-evaluate the platform
   gateway once it is GA (announced for RHCL 1.5; upstream is at v1.0.x).
3. **Done: branch B.**
   - zuno-demo `daa99dad`, `dbca2165`: `/mcp` accepts `X-Zuno-Agent` and
     `X-Zuno-Task` together with a Keycloak JWT. Such a caller gets the full
     five-factor intersection that `/v1/tools/{name}/invoke` applies. Its
     surface is the agent task's declared tools.
   - The caller must be in the agent's `zuno.access.groups` (ADR-0040).
     Otherwise the request is refused with a 403, as it is for an OpenShift
     token that declares an agent.
   - Callers without an agent keep the ADR-0524 ceiling.
   - `main.py` builds the surface and `mcp_frontdoor.py` only iterates it,
     so there is still one intersection (ADR-0036).
   - Tests: `tests/test_mcp_frontdoor_agent.py` (7). The whole suite passes
     (52).
4. **Done: fork side, awaiting release.** Fork devel `dbfc4752e`:
   `UnifaiAgentBundle.spec.mcp` emits one owned `UnifaiProvider` per task
   with `X-Zuno-Agent`/`X-Zuno-Task`/classification/run id. It ships with
   operator 0.1.19 (release by the startx-unifai session).
   - zuno-demo `5d652ffd` adds `mcpGateway.perTask` to the `unifai` chart.
     It stays off until 0.1.19 is on the cluster.
5. **Done: live proof on demo333.**
   - The mcp-gateway image was built from `5d652ffd`.
   - From the `zuno-unifai` namespace, with real realm zuno tokens:
     - `consultant-01` as `tekos`/`answer-technical-question` was listed
       exactly the task's allowed tools (`aap.cluster.audit`,
       `aap.platform.audit`, `confluence.page.search`,
       `diagram.generation.create`, `git.repository.list`,
       `git.repository.read`, `web.page.search`). The same caller without
       an agent got the Lightspeed ceiling.
     - `tekos-entitlement-only-user-01` was listed nothing.
     - `confluence.page.create` (undeclared) was refused as not exposed.
     - `confluence.page.search` for a caller without the group was refused.
       The mcp-gateway audit log shows `agent=tekos
       task=answer-technical-question ... allowed=False reason=caller groups
       ['agent_tekos'] do not intersect ...`.
     - An allowed call returned real Confluence results.
   - Through UnifAI: a throwaway `UnifaiProvider` with the headers 0.1.19
     will emit, and a persona browser login as `consultant-01`. The agent's
     `confluence.page.search` calls reached `/mcp` with that user's JWT and
     were logged `agent=tekos ... allowed=True`. Test objects were deleted.
6. **Finding for WP-154.** With `ovhcloud-gpt-oss-120b`, the C2 route for
   tekos, the agent kept re-querying the tool until `max_rounds` and ended
   without output. A direct gateway call with a tool result answered in one
   of two tries. The gateway round trip is fine; the agent prompt, rounds or
   model need tuning in the tekos pilot.

**Remaining:** turn on `mcpGateway.perTask` once operator 0.1.19 is on
stable, then repeat the UnifAI proof with a bundle-emitted provider. The
entitlement check (step 3) still needs to be deployed on demo333; the
image proven in step 5 predates it.

## Acceptance

The evaluation table of step 2 exists with evidence. Branch B: the mcp-gateway
suite is green, including the new tests; on demo333 (powered on at the user's
request, `--context` explicit), an UnifAI `UnifaiProvider` pointing at
`/mcp` lists only tekos's tools, and a refused call is visible in the
mcp-gateway audit log. Branch A: the migration plan is approved by the user.

## Open questions

- Does RHOAI 3.5 or Connectivity Link ship an MCP gateway at all, and at
  what support level? Unverified; step 1.
- If the platform gateway covers (a) and (c) but not the agent part of (b),
  is a Keycloak-group-only policy acceptable? That weakens ADR-0036; the
  user must decide.
