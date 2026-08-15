# Comage Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for Comage
(ADR-0326/WP-33, the third real agent). `run_scenarios.py`/
`run_acceptance_gate.py` here are thin `AGENT=comage` wrappers around the
canonical, shared implementation in `evaluations/tekos/` (ADR-0342 - see
that directory's `run_scenarios.py` module docstring for why the shared
code lives there rather than being copied per agent); `scenarios.yaml`,
`gate_config.yaml` and `security_checks.py` are Comage's own, real
content.

**Not yet wired into `make day1|d1 check agents`'s automatic path**
(`ansible/roles/agents/tasks/check.yml` only smoke-tests Comage's frontend
`/healthz` today) - running this gate against a live cluster requires the
human scenario-review checkpoint WP-33's own brief gates on first. Once
that review has happened, the operator runs it explicitly:

```bash
cd evaluations/comage
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export FRONTEND_URL=https://comage.apps.<cluster-domain>
export COMAGE_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/comage-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / SALES_DB_MCP_URL /
# SALESFORCE_MCP_URL / AI_GATEWAY_URL default to their in-cluster Service DNS
# names - override if running this from outside the cluster via a
# port-forward instead. Reaching those in-cluster names at all requires
# running from a network location the ADR-0037/ADR-0052 NetworkPolicies
# actually allow, same constraint evaluations/tekos/README.md documents
# for its own gate Job.
python3 run_acceptance_gate.py     # scenarios + security_checks + gate_checks, one exit code
python3 run_scenarios.py           # just the 20 scenarios
python3 security_checks.py         # just the security-negative checks
```

`AGENT=comage`/`TASK_NAME=check-deal-status` are set by the wrapper
scripts automatically - only set them yourself if invoking the canonical
`evaluations/tekos/run_scenarios.py`/`run_acceptance_gate.py` directly
against this directory's `scenarios.yaml` for some other reason.

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters) - the exact same `type` vocabulary
`evaluations/tekos/scenarios.yaml` uses, since `run_scenarios.py`'s
handlers are generic HTTP call patterns, not Tekos-specific code.

Coverage: portal/tile access gating (scenarios 1, 2, 4-6), authentication
(3), the chat contract synchronous and streaming (7-9), the
**indexed-vs-live routing pair** (ADR-0205's core acceptance bullet,
exercised through a real agent for the first time - Arkos's own live call
is unconditional, so it never needed this distinction): an ordinary
deal-status question answered from `knowledge.sales` alone (7, no live
citation expected) versus a question asking for a mutable field's CURRENT
value, which triggers a live `salesforce.opportunity.read` search visible
in the reply's citations (10), RAG retrieval contributing a citation for
a sales topic (11), MCP Gateway policy enforcement (12-13, 18 - 18 is the
sharpest of the three: `sxa.opportunity.search` is denied for
`check-deal-status` even though Comage's OTHER task,
`compare-historical-deals`, declares it - proving ADR-0011's task_rights
factor narrows independently of the broader agent_declaration factor,
not just "a tool no task declares at all" the way scenario 12/13 do),
model routing/classification fail-closed behavior (14-15,
config-consistency checks that don't need a live cluster), BFF JWT
validation (16-17), namespace isolation for the two still-genuinely-
placeholder agents (19, Advantage/Finage - Arkos and Comage both dropped
from this list once their own frontend/BFF workloads deployed), and
service health including Comage's own new `salesforce-mcp` server (20).

This cannot be executed in the sandbox this repo was built in (no live
OpenShift cluster) - see the top-level feasibility plan for what a full
evaluation run requires.

## Security-negative checks

`security_checks.py` (same setup as above, run from this directory) checks
identity-propagation, classification and entitlement behavior that isn't
part of the fixed 20-scenario acceptance count: the BFF actually forwards
the caller's token to the Agent Runtime, the Runtime ignores a forged
`user_sub` in the request body rather than treating it as authoritative,
the three `salesforce.opportunity.*` capabilities are correctly classified
C2 (matching `knowledge.sales`'s own `sales-data: C2` domain - deliberately
*not* asserting `external_model_policy.allow_context: false` the way
Arkos's Confluence check does, since that restriction is Confluence's own
source-level/contractual one, not a general C2 rule), `X-Zuno-Local-Only:
true` actually forces `components/ai-gateway` to pick the local provider
even for a C2 request that would otherwise be SaaS-eligible, the
two-dimension group model is enforced server-side in both directions
using two new fixture personas mirroring Tekos/Arkos's own
(`comage-entitlement-only-user-01`: `agent_comage` entitlement but no
business role, denied `salesforce.opportunity.read` by the MCP Gateway
with 403; `sales-role-only-user-01`: `sales` business role but no
`agent_comage` entitlement, denied by the BFF itself with 403 before the
request ever reaches the Agent Runtime), and a direct call to
`salesforce-mcp` - Comage's own new server, unlike Arkos's re-proof
against the already-covered `sales-db-mcp` - that bypasses the MCP
Gateway entirely is denied by the server itself (401).
