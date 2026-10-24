# Tekos Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for Tekos,
the first functional agent. Since ADR-0342/WP-31, `run_scenarios.py`,
`run_acceptance_gate.py` and `gate_checks.py` here are the canonical,
shared implementation every real agent's own evaluation directory reuses
(see `evaluations/arkos/README.md` for the first reuse, via a thin
`AGENT=arkos` wrapper) - `scenarios.yaml` and `security_checks.py` stay
genuinely per-agent content.

UnifAI serves the agents (ADR-0561) and is the only evaluation target since
WP-156 retired the legacy agent stack: chat-shaped scenarios and checks run
through UnifAI's session API, the others call the shared platform services
(Keycloak, MCP gateway, ai-gateway, MCP servers) directly.

`run_acceptance_gate.py` is the layered entrypoint
`make day2|d2 check agents` actually invokes for Tekos specifically (see
`ansible/roles/agents/tasks/check.yml`'s `run_acceptance_gate.yml`
include, which runs it as a one-shot in-cluster Job): it combines this
file's 20 scenarios (75% threshold) with `security_checks.py` and
`gate_checks.py` (both 100% mandatory) into one exit code and one
machine-readable JSON summary line. Run any of the three modules directly
for a narrower check, or the combined gate for what
`make day2|d2 check agents` runs:

```bash
cd evaluations/tekos
pip install -r requirements.txt
export UNIFAI_URL=https://unifai-ui-zuno-unifai.apps.<cluster-domain>
export UNIFAI_TEAM_NAME=agent-tekos    # the team workspace that owns the agent's workflows (or UNIFAI_TEAM_ID)
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export EVAL_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/zuno-evaluations)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
# MCP_GATEWAY_URL / AI_GATEWAY_URL / CONFLUENCE_MCP_URL default to their
# in-cluster Service DNS names - override if running this from outside the
# cluster via a port-forward instead. Reaching those in-cluster names at all
# requires running from a network location the ADR-0037/ADR-0052
# NetworkPolicies actually allow - see
# ansible/roles/agents/tasks/run_acceptance_gate.yml for how
# `make day2|d2 check agents`'s own Job satisfies that (the
# "acceptance-gate" workload identity, narrowly allow-listed alongside
# the other real per-workload callers).
python3 run_acceptance_gate.py     # everything `make day2|d2 check agents` runs, one exit code
python3 run_scenarios.py           # just the 20 scenarios
```

`EVAL_CLIENT_SECRET` is the `zuno-evaluations` confidential client, which
mints the persona tokens sent to the services called directly; the persona
itself signs in to UnifAI through the UI route as a browser does
(`unifai_target.py`). `--target unifai`/`EVAL_TARGET=unifai` are still
accepted; any other target is refused.

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters); `run_scenarios.py` maps each `type` to one
handler function and prints a pass/fail table plus the overall rate against
the 75% threshold, exiting non-zero on failure so it's CI-friendly once a
live cluster is reachable from a GitHub Actions runner (not yet true for
this project - see `.github/README.md`). `gate_checks.py`'s checks need no
live cluster and are wired into `.github/workflows/lint.yml`'s
`policy-as-code` job accordingly (see below for what they check).

Coverage: agent visibility and access gating (scenarios 1, 2, 4-6),
authentication (3), the chat contract synchronous and streaming (7-9),
tool-triggered retrieval (10-11), MCP Gateway policy enforcement (12-13,
18), model routing/classification fail-closed behavior (14-15,
config-consistency checks that don't need a live cluster), unauthenticated
access refused (16-17), namespace isolation (19), and service health (20).

`gate_checks.py` holds three config-only checks (no live cluster needed):
permitted SaaS fallback at C2, `write-code`'s model-routing preference
genuinely resolving to `mistral-codestral` first (ADR-0417), and Tekos's
OKF bundle staying free of the DAT-drafting/image-generation capabilities
that belong to Arkos alone (ADR-0415) - all three are wired into
`.github/workflows/lint.yml`'s `policy-as-code` job.

This cannot be executed in the sandbox this repo was built in (no live
OpenShift cluster) - see the top-level feasibility plan for what "make
check" and a full evaluation run require.

## How the scenarios run on UnifAI (WP-154)

A persona signs in to the UnifAI UI through realm `zuno` (`unifai_target.py`),
then creates and streams a session with `/api2/sessions/user.session.*`, the
way a browser does. Scenarios about shared services (MCP gateway, model
router, Keycloak) call those services directly.

| Scenario | On UnifAI |
|---|---|
| 1, 4 portal tiles | the persona sees the agent's workflows |
| 5 tile disabled | no workflows listed for a non-member **and** the MCP gateway refuses the agent (403) |
| 2, 16 login required | an anonymous API call gets 401 |
| 7-10 chat | session create + streamed execute (`llm_token`, `tool_calling`, `complete` events); scenario 10 accepts the retriever (`docs_rag_retriever_tool`) as well as `confluence.page.search`, and every run has an overall deadline |
| 11 RAG citation | a member of the source's groups asks about a known page; the answer must come through the retriever and name the page (`UNIFAI_RAG_QUESTION`, `UNIFAI_RAG_EXPECT`) |
| 20 health | the UnifAI UI route, the MCP gateway and the ai-gateway (`services:` in `scenarios.yaml`) |
| 6, 17, 19 | reported as skipped, not counted: no placeholder tiles, no bearer-token API, in-cluster-only check |

Skipped scenarios are excluded from the pass rate, which is still compared
with the 75% threshold. A diagram request takes over a minute (several tool
calls), so run the checks with a generous timeout.

## Security-negative checks

`security_checks.py` (same setup as above, run from this directory) checks
identity-propagation, classification and entitlement behavior that isn't
part of the fixed 20-scenario acceptance count (these are negative/security
checks, not acceptance coverage):

- ADR-0032 `unifai_forwards_identity_to_the_gateways`: a Confluence tool
  call succeeds through the MCP gateway, which only serves the user's own
  JWT, so the caller's token demonstrably travels UnifAI -> mcp-gateway.
- ADR-0033 `unifai_ignores_a_client_supplied_identity_header`: an outside
  `X-Authenticated-User` header without a session gets 401.
- ADR-0034/0035: Confluence is correctly classified C2 with
  `external_model_policy.allow_context: false` (a config-only check, no
  live cluster needed), and `X-Zuno-Local-Only: true` actually forces
  `components/ai-gateway` to pick a local provider even for a C2 request
  that would otherwise be SaaS-eligible.
- ADR-0040, both directions of the two-dimension group model: a caller with
  the `agent_tekos` entitlement but no business role is denied
  `search_confluence` by the MCP Gateway (403), and a caller with the
  `consultant` business role but no `agent_tekos` entitlement neither sees
  the agent's workflow nor gets past the MCP gateway's agent declaration
  (`business_role_without_entitlement_denied_by_unifai`).
- ADR-0037: a direct call to `confluence-mcp` that bypasses the MCP
  Gateway entirely (no `X-Zuno-Gateway-Token`) is denied by the server
  itself (401) - the workload-identity layer required in addition to the
  NetworkPolicy boundary (`gitops/charts/mcp-confluence`'s
  `NetworkPolicy`, which an HTTP-level check like this can't directly
  exercise; `platform/security/check_workload_hardening.py` statically
  verifies that policy and the rest of the hardening baseline exist in
  every chart's rendered manifests instead).
- ADR-0415/ADR-0036: a direct `generate_image` call "as Tekos" is denied
  (403) by the MCP Gateway's agent_declaration factor alone -
  `generate_image`'s `allowed_groups` includes `consultant`, so this
  isolates the boundary from group/role noise - and a diagram request on
  UnifAI never reaches the SDXL tool nor returns a PNG
  (`unifai_tekos_never_generates_photorealistic_images`), since Tekos's
  task never declares that capability in the first place
  (Arkos/Advantage/Comage's alone).
- ADR-0355: the `aap.*` capabilities deny an unauthorized group and serve
  an authorized caller.
- ADR-0401/0403/0406 (WP-174): the first agent delegation, Tekos to Arkos
  (`draft-architecture-testimonial`), through the MCP gateway
  (`evaluations/common/delegation_checks.py`): as `eval-consultant-01` the delegated
  surface lists only read tools while the direct one lists a write tool; refused when
  the user lacks `agent_arkos`, for a target Tekos does not declare, beyond the depth
  limit, on a cycle, with a depth header that disagrees and with half a chain.
  **They are reported as skipped, never as passes, while the admitted release does not
  declare Tekos -> Arkos** (release 0.3.1 declares nothing) and while the corp flag
  `delegation.allow_write` is true. They do not need the A2A server of WP-173; the
  behavioural proof (a real delegation that runs, the chain in the trace) is WP-174's live pass.

## Exploratory stress test

The former `stress_test.py` battery drove the retired agent stack's chat
endpoints directly and was removed with it (WP-156); `make d2 stresstest`
reports the stress_test layer as not run until a UnifAI port exists.
