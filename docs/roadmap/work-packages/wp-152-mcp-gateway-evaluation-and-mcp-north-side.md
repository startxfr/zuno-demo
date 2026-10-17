# WP-152: Evaluate the RHOAI MCP Gateway, else extend the mcp-gateway north side

- **State:** Not started
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
