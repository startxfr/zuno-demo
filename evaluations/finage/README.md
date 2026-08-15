# Finage Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for Finage
(ADR-0326/WP-36, the fifth and final real agent - closing the four-agent
generalization). `run_scenarios.py`/`run_acceptance_gate.py` here are
thin `AGENT=finage` wrappers around the canonical, shared implementation
in `evaluations/tekos/` (ADR-0342 - see that directory's
`run_scenarios.py` module docstring for why the shared code lives there
rather than being copied per agent); `scenarios.yaml`, `gate_config.yaml`
and `security_checks.py` are Finage's own, real content.

**Not yet wired into `make day1|d1 check agents`'s automatic path**
(`ansible/roles/agents/tasks/check.yml` only smoke-tests Finage's
frontend `/healthz` today) - running this gate against a live cluster
requires the human scenario-review checkpoint WP-36's own brief gates on
first. Once that review has happened, the operator runs it explicitly:

```bash
cd evaluations/finage
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export FRONTEND_URL=https://finage.apps.<cluster-domain>
export FINAGE_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/finage-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / SALES_DB_MCP_URL /
# AI_GATEWAY_URL default to their in-cluster Service DNS names - override if
# running this from outside the cluster via a port-forward instead. Reaching
# those in-cluster names at all requires running from a network location the
# ADR-0037/ADR-0052 NetworkPolicies actually allow, same constraint
# evaluations/tekos/README.md documents for its own gate Job.
python3 run_acceptance_gate.py     # scenarios + security_checks + gate_checks, one exit code
python3 run_scenarios.py           # just the 20 scenarios
python3 security_checks.py         # just the security-negative checks
```

`AGENT=finage`/`TASK_NAME=answer-finance-question` are set by the wrapper
scripts automatically - only set them yourself if invoking the canonical
`evaluations/tekos/run_scenarios.py`/`run_acceptance_gate.py` directly
against this directory's `scenarios.yaml` for some other reason.

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters) - the exact same `type` vocabulary
`evaluations/tekos/scenarios.yaml` uses, since `run_scenarios.py`'s
handlers are generic HTTP call patterns, not Tekos-specific code.

Coverage: portal/tile access gating (scenarios 1, 2, 4-6 - scenario 6
checks Arkos's own tile, since every catalog-only agent that came before
Finage has already shipped its own real bundle/chart by this point;
`portal_tile_state`'s `expect_placeholder` check is driven by each
agent's own `zuno.status` field, not by whether its chart is deployed, so
Arkos still correctly reports "coming soon" until its own gate passes),
authentication (3), the chat contract synchronous and streaming (7-9),
RAG retrieval over `knowledge.project` (10), MCP Gateway policy
enforcement (11-13, 18 - **this slice's signature proof, three
independent MCP denials**: 12 denies a live Salesforce capability, 13
denies a Comage-only legacy SXA pipeline-search capability neither
declared anywhere in Finage's bundle, and 18 denies
`sxa.aggregate.revenue-by-year` for the *live* task specifically - a
tool Finage's own `monthly-invoice-report` task DOES declare, but
`answer-finance-question` does not, proving the ADR-0011 task_rights
factor narrows independently of agent_declaration, the same sharp proof
Comage's own scenario 18 established first), model routing/classification
fail-closed behavior (14-15, config-consistency checks that don't need a
live cluster), BFF JWT validation (16-17), namespace isolation (19 - an
intentionally empty `agents: []` list: every agent now has a real,
deployed frontend/BFF, so this is a vacuously-true pass marking the
milestone rather than a removed check), and service health including
`sales-db-mcp` (20, the backend Finage's own `sxa.*` capabilities are
served by).

This cannot be executed in the sandbox this repo was built in (no live
OpenShift cluster) - see the top-level feasibility plan for what a full
evaluation run requires.

## Security-negative checks

`security_checks.py` (same setup as above, run from this directory)
checks identity-propagation and entitlement behavior that isn't part of
the fixed 20-scenario acceptance count: the BFF actually forwards the
caller's token to the Agent Runtime, the Runtime ignores a forged
`user_sub` in the request body rather than treating it as authoritative,
`X-Zuno-Local-Only: true` actually forces `components/ai-gateway` to pick
the local provider even for a C2 request that would otherwise be
SaaS-eligible, the two-dimension group model is enforced server-side in
both directions using two new fixture personas mirroring the prior
slices' own (`finage-entitlement-only-user-01`: `agent_finage`
entitlement but no business role, denied `sxa.customer.read` by the MCP
Gateway with 403; `finance-role-only-user-01`: `finance` business role
but no `agent_finage` entitlement, denied by the BFF itself with 403
before the request ever reaches the Agent Runtime), and a direct call to
`sales-db-mcp` that bypasses the MCP Gateway entirely is denied by the
server itself (401) - directly relevant here since that's the same
backend Finage's own `sxa.*` capabilities are served by, not just a
platform-wide boundary borrowed from another slice.

`finage_never_declares_sales_or_adv_knowledge_domains` is this slice's
own addition, mirroring Advantage's own equivalent check: it parses
every `agents/finage/tasks/*.md` file's actual YAML frontmatter (never
the Markdown body, which may legitimately reference other agents'
capabilities by name in prose) and fails if any task's
`allowed_knowledge` includes the sales or ADV knowledge domains, or
`allowed_tools` includes a `salesforce.*`/`aramis.*` capability - the
config-level half of this slice's least-privilege proof, independent of
(and redundant with) the live MCP Gateway denials scenarios 12/13 prove
at runtime.
