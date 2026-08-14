# WP-31: Arkos vertical slice (first of four; closes ADR-0209 and ADR-0342)

- **State:** Not started
- **ADRs:** ADR-0326 (To be implemented -> Partially implemented, 1 of 4); closes ADR-0209 and ADR-0342 to Implemented
- **Depends on:** WP-30, WP-28, WP-26 (merged); Phase 2 knowledge stack (WP-20/21/22 for `knowledge.tech` reuse)
- **Blocks:** WP-33, WP-37
- **Estimated files touched:** ~25 across three parts — execute as three PRs (a/b/c)

> Execute each part as its own standalone task. Arkos is the template every
> later agent slice mirrors — favor the most regular possible structure.
> The evaluation scenarios in part (c) REQUIRE human review before any
> cluster gate run counts (they define the agent's acceptance bar).

## Goal

Make Arkos the second real agent: a genuine OKF task bundle exercising its
own graph shape (long-form document generation — materially different from
Tekos's Q&A shape), one frontend + one BFF deployment, Keycloak entitlement
+ business-role wiring, `knowledge.tech` + `knowledge.project` reuse,
delegated Google Drive/Docs write, live Confluence (and Jira when its server
exists), and the full 20-scenario evaluation gate.

## ADR references

- [docs/adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md](../../adr/0326-generalize-the-tekos-vertical-slice-to-the-four-remaining-agents.md)
  — read the "mandatory common completion pattern" list in full; Arkos must
  prove delegated Drive/Docs access, `knowledge.tech` reuse, and live
  Jira/Confluence actions without physical endpoint coupling.
- [docs/adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md](../../adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
  — Arkos runs a real task end to end through its own graph shape; Tekos and
  Arkos both retrieve `knowledge.project` content for the same `project_id`
  (ADR-0209's acceptance scenario) each through its own shape and task
  prompts/capabilities.
- [docs/adr/0209-introduce-project-scoped-agent-memory.md](../../adr/0209-introduce-project-scoped-agent-memory.md)
  — the cross-agent `demo-001` acceptance bullet closes here.

## Preconditions (verify before starting)

- WP-30 merged (shape mechanism), WP-28 merged (`knowledge.project`), WP-26
  merged (auth modes; `drive.*` = delegated-user).
- `python3 platform/docs/check_docs.py` exits 0.
- Read as templates: the complete Tekos slice — `agents/tekos/**`,
  `gitops/charts/tekos/`, `evaluations/tekos/**`, and how
  `ansible/roles/agents` + `make d1 install agents` deploy it; also
  `agents/arkos/` (current placeholder to replace) and `docs/agents/arkos.md`
  (intended persona/behavior).

## Part (a) — OKF bundle, policies, graph shape

1. Replace `agents/arkos/tasks/coming-soon.md` with real task bundles
   (long-form document generation from `knowledge.tech` context + Drive
   write; mirror Tekos task file structure), real prompts under
   `agents/arkos/prompts/`, and a completed `agents/arkos/agent.okf.md`:
   graph-shape declaration (new named shape, e.g. `plan_draft_write`),
   `zuno.allowed_knowledge: [knowledge.tech, knowledge.project]`, logical
   tool capabilities only (`drive.document.create`, `drive.document.update`,
   `confluence.page.read`, `confluence.page.search`, … — no URLs/vendor
   names).
2. Implement the Arkos graph shape module in
   `components/agent-runtime/app/graph/` (register in `GraphFactory`), a
   plan → retrieve → draft → write flow that is genuinely structurally
   different from Tekos's shape.
3. Policy: add Arkos to `policies/tools/tool-policy.yaml` +
   `policies/knowledge/knowledge-policy.yaml` (agent entitlement
   `agent_arkos`, business roles per `docs/agents/arkos.md`).
4. Tests: shape registered and resolvable; the ADR-0209 cross-agent test —
   Tekos stores `demo-001` facts, Arkos retrieves them through its own shape
   (extend WP-28's end-to-end test).

## Part (b) — deployment surface

5. Chart `gitops/charts/arkos/` mirroring `gitops/charts/tekos/` (frontend +
   BFF per ADR-0008, hardened, in `zuno-ai-run` per ADR-0329); Application
   under `gitops/apps/` mirroring the tekos app wiring; immutable image tag
   if WP-04 stage 3 has landed (ask the operator for the release tag).
6. Keycloak: `agent_arkos` entitlement + role mappings in
   `gitops/charts/keycloak/files/realm-zuno.json` mirroring Tekos's
   entries.
7. Day 1: ensure `make d1 install|check|uninstall agents` covers Arkos
   (follow how `ansible/roles/agents` enumerates agents — data-driven if
   possible).

## Part (c) — evaluation gate

8. `evaluations/arkos/`: 20 acceptance scenarios (`scenarios.yaml` mirroring
   `evaluations/tekos/scenarios.yaml` structure exactly) + the runner files
   (reuse/parameterize `run_scenarios.py`, `run_acceptance_gate.py`,
   `gate_checks.py`, `security_checks.py` rather than copying, if they can
   take an agent argument), including C1/C2/C3 and external-model
   eligibility security scenarios per ADR-0326's completion pattern.
9. **Human review checkpoint:** scenarios must be reviewed by the user
   before the operator gate run counts. Flag the PR accordingly.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Tekos's bundle/chart/evaluations (shared code may be parameterized, but
  Tekos behavior must not change — its tests prove it).
- Shared services (no forks — ADR-0326's core rule).
- `gitops/apps/*` `targetRevision` (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/agent-runtime/tests/ -q` (incl. cross-agent memory test)
- `python3 platform/docs/check_knowledge_refs.py` (Arkos references valid)
- `helm lint gitops/charts/arkos`; `python3 platform/security/check_workload_hardening.py`
- `python3 platform/supply-chain/check_build_matrix.py` (if new Dockerfiles)
- `! grep -rn "http\|svc.cluster.local" agents/arkos/` (no physical endpoints)
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- If WP-05 landed: bundle signing validation passes for `agents/arkos/`.

## Operator / human follow-up (not executable by the model)

1. User: review the 20 scenarios (part c checkpoint).
2. Operator: deploy (`make d1 install agents`), run the acceptance gate at
   the ADR-0028 75% threshold on cluster, plus the delegated Drive/Docs
   write with a real Google account (ADR-0014 flow) and a live Confluence
   action (WP-02's server).
3. Operator: flip `agents/arkos` status from `placeholder` to `active` in
   its OKF metadata only after the gate passes (per ADR-0326).

## Status updates (then re-run check_docs.py)

- After parts a–c merge: ADR-0326 →
  `Partially implemented (Arkos slice merged, 1 of 4; cluster gate pending)`;
  ADR-0342 → `Implemented - see \`components/agent-runtime/app/graph/\`.`;
  ADR-0209 → `Implemented - see \`knowledge/project/\`, \`components/agent-runtime/app/\`.`;
  index rows to match; tracker rows updated.
- After the operator gate: update ADR-0326's dated progress note (Arkos
  active); tracker WP-31 → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Jira MCP server (template from WP-02 when scheduled; Arkos's live-Jira
  bullet can complete then — note it in ADR-0326's progress note if
  deferred).
- Comage/Advantage/Finage (WP-33/35/36).
