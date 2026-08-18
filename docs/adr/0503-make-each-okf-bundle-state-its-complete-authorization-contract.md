# ADR-0503: Make each OKF bundle state its complete authorization contract

- **Status:** Implemented - see `platform/okf/generate_authorization_matrix.py`, `platform/okf/generate_deployment_snapshot.py` and `agents/*/deployment/` (WP-44 + WP-45, 2026-08-18)
- **Target:** OKF v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

The authorization story of an agent is complete and enforced today, but it
is stated nowhere in one place. Answering "who can use what, for what,
under which policy" for Tekos requires joining five files by hand:
`agents/tekos/agent.okf.md` (`zuno.access.groups`, the entitlement
dimension of ADR-0040; `zuno.model.preferred_classification`), each
`agents/tekos/tasks/*.md` (`zuno.allowed_tools`, `zuno.allowed_knowledge`,
`zuno.live_read_tool` — declared ceilings, ADR-0011/ADR-0203),
`policies/tools/tool-policy.yaml` (per-tool `capability`, `mcp_server`,
`min_classification`, `allowed_groups`, `external_model_policy`) and
`policies/knowledge/knowledge-policy.yaml` (the same for `knowledge.*`
domains). The canonical formula heads both policy files:

```
allowed = agent_declaration ∩ task_rights ∩ user_group_rights ∩ classification ∩ platform_policy
```

The enforcement path is healthy — MCP Gateway computes the intersection
(ADR-0036), Agent Runtime gates tool/RAG calls from its registry
(ADR-0039), the portal filters tiles — but the *human-readable* contract
is scattered, so reviews of "what can Finage's finance tasks actually
reach, and who can trigger them" are archaeology. Separately, every
`agents/<name>/deployment/` directory contains only a one-line stub
README, while the agent's real deployment shape lives in
`gitops/charts/<name>/` (an `AIAgent` CR for CR-managed agents, plain
manifests for Tekos) — the directory the OKF skeleton reserves for
deployment says nothing about deployment.

## Decision

1. **Every `agent.okf.md` body carries a generated `## Authorization
   matrix` section** rendering, for that agent, the complete intersection:
   one row per (task × tool) and (task × knowledge domain) pair, with the
   columns WHO — the `agent_<name>` entitlement group plus the business
   roles (`allowed_groups`) the policy files grant the resource to; WHAT —
   the tool (with its ADR-0116 capability id and MCP server) or knowledge
   domain, its `min_classification`, its `external_model_policy` posture,
   and its ADR-0511 quota class once quota policy exists; FOR WHAT — the
   task (and its prompt) the row belongs to, with `live_read_tool` and
   `primary_task` flagged; POLICY — the policy file entry the row derives
   from. A header paragraph states the agent's
   `preferred_classification` ceiling and `zuno.access.groups`.

2. **The matrix is derived, never hand-authored.** A generator/validator
   extension in `platform/okf/` recomputes each agent's matrix from the
   frontmatter and policy YAML sources and fails when the committed
   section differs — the same policy-as-code posture as
   `check_knowledge_refs.py`, wired into the same lint chain. The matrix
   is documentation of the intersection, not an input to it: MCP Gateway,
   Agent Runtime and the portal keep reading the YAML sources; a matrix
   edit changes nothing at runtime and is always overwritten by the
   generator.

3. **Stage-2 `deployment/` directories hold a generated deployment
   snapshot instead of a stub**: the agent's `AIAgent` CR spec as rendered
   from `gitops/charts/<name>/` (or, for grandfathered plain-manifest
   Tekos, a generated summary of its chart's Deployments/Routes), plus a
   README naming the chart, Applications and sync-waves that actually
   deploy the agent. The snapshot is validated against the chart the same
   way the matrix is validated against the policy files — drift fails CI.
   `agents/<name>/deployment/` thereby becomes a faithful, reviewable
   mirror of the deployment surface, while `gitops/` remains the sole
   applied source (ADR-0022).

4. **Per-stage README templates** (Stage 1 and Stage 2, ADR-0502) are
   added to `platform/templates/agent/`, each with a mandatory
   "Authorization at a glance" pointer to the generated matrix.

## Consequences

An agent review reads one generated section instead of joining five
files. The generator becomes a fourth reader of the bundle format —
acceptable because it lives beside the schema in `platform/okf/` and runs
only in CI, not in any service. Matrix and deployment-snapshot
regeneration become part of every policy or task change; WP-44 and WP-45
execute the initial generation.

## Security considerations

The matrix must never become an enforcement input — enforcement stays
with the YAML sources and their existing consumers (ADR-0036, ADR-0039);
a generated document that services trusted would be a new attack surface.
Because the matrix makes grants legible, review of an over-broad grant
becomes easier, not harder; the generator must render exactly what the
sources say, including an explicit `(no groups — unusable)` marker when a
declared tool has no overlap with any business role, rather than omitting
awkward rows.

## Operational considerations

The generator runs in the lint chain (`.github/workflows/lint.yml`'s
policy-as-code job) and locally via `platform/okf/`; a failed run prints
the diff between committed and recomputed matrix. Deployment snapshots
regenerate whenever `gitops/charts/<name>/` changes.

## Acceptance criteria

- Tekos and Naveo carry generated matrices whose every row is traceable
  to a frontmatter + policy-file pair; the remaining six agents follow.
- Editing a `tool-policy.yaml` `allowed_groups` entry without
  regenerating fails the lint chain.
- Stage-2 agents' `deployment/` content matches `gitops/charts/<name>/`;
  the one-line stub READMEs are gone.
- `python3 platform/docs/check_docs.py` passes.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0040](0040-separate-agent-entitlement-from-business-role-authorization.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0203](0203-enforce-knowledge-authorization-as-policy-intersection.md)
- [ADR-0502](0502-formalize-the-two-stage-agent-maturity-model.md)
- [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md)
