# Advantage Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for
Advantage (ADR-0326/WP-35, the fourth real agent). `run_scenarios.py`/
`run_acceptance_gate.py` here are thin `AGENT=advantage` wrappers around
the canonical, shared implementation in `evaluations/tekos/` (ADR-0342 -
see that directory's `run_scenarios.py` module docstring for why the
shared code lives there rather than being copied per agent);
`scenarios.yaml`, `gate_config.yaml` and `security_checks.py` are
Advantage's own, real content.

**Not yet wired into `make day1|d1 check agents`'s automatic path**
(`ansible/roles/agents/tasks/check.yml` only smoke-tests Advantage's
frontend `/healthz` today) - running this gate against a live cluster
requires the human scenario-review checkpoint WP-35's own brief gates on
first. Once that review has happened, the operator runs it explicitly:

```bash
cd evaluations/advantage
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export FRONTEND_URL=https://advantage.apps.<cluster-domain>
export ADVANTAGE_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/advantage-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / AI_GATEWAY_URL
# default to their in-cluster Service DNS names - override if running this
# from outside the cluster via a port-forward instead. Reaching those
# in-cluster names at all requires running from a network location the
# ADR-0037/ADR-0052 NetworkPolicies actually allow, same constraint
# evaluations/tekos/README.md documents for its own gate Job.
python3 run_acceptance_gate.py     # scenarios + security_checks + gate_checks, one exit code
python3 run_scenarios.py           # just the 20 scenarios
python3 security_checks.py         # just the security-negative checks
```

`AGENT=advantage`/`TASK_NAME=answer-project-question` are set by the
wrapper scripts automatically - only set them yourself if invoking the
canonical `evaluations/tekos/run_scenarios.py`/`run_acceptance_gate.py`
directly against this directory's `scenarios.yaml` for some other reason.

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters) - the exact same `type` vocabulary
`evaluations/tekos/scenarios.yaml` uses, since `run_scenarios.py`'s
handlers are generic HTTP call patterns, not Tekos-specific code.

Coverage: portal/tile access gating (scenarios 1, 2, 4-6), authentication
(3), the chat contract synchronous and streaming (7-9), RAG retrieval
over `knowledge.adv` (10), MCP Gateway policy enforcement (11-13, 18 -
**12/13 are this slice's signature proof**: a live Salesforce capability
and a legacy SXA/sales capability are both denied with 403, since
Advantage never declares either anywhere in its own OKF bundle - the
cross-domain authorization boundary ADR-0326 requires, proven by explicit
omission rather than a runtime filter; 18 mirrors the generic
agent_declaration proof every prior slice's own scenario 18 makes, here
against `confluence.page.search`), model routing/classification
fail-closed behavior (14-15, config-consistency checks that don't need a
live cluster), BFF JWT validation (16-17), namespace isolation for the
one still-genuinely-placeholder agent (19, Finage - Arkos/Comage/Advantage
have all now dropped off this list once their own frontend/BFF workloads
deployed), and service health (20).

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
slices' own (`advantage-entitlement-only-user-01`: `agent_advantage`
entitlement but no business role, denied `list_drive_files` by the MCP
Gateway with 403; `adv-role-only-user-01`: `adv` business role but no
`agent_advantage` entitlement, denied by the BFF itself with 403 before
the request ever reaches the Agent Runtime), and a direct call to
`sales-db-mcp` that bypasses the MCP Gateway entirely is denied by the
server itself (401) - a platform-wide (ADR-0037), not Advantage-specific,
boundary this gate still verifies.

`advantage_never_declares_the_sales_knowledge_domain` is this slice's own
addition, replacing the per-agent capability-classification check every
prior slice has (Advantage introduces no new capability, so there is
nothing new to classify): it parses every `agents/advantage/tasks/*.md`
file's actual YAML frontmatter (never the Markdown body, which may
legitimately reference other agents' capabilities by name in prose) and
fails if any task's `allowed_knowledge` includes the sales knowledge
domain or `allowed_tools` includes a `salesforce.*`/`sxa.*` capability -
the config-level half of this slice's signature proof, independent of
(and redundant with) the live MCP Gateway denials scenarios 12/13 prove
at runtime.
