# WP-30: Multi-shape Agent Runtime

- **State:** Repo work merged (2026-08-15 — repo-provable, no operator step for this WP: `components/agent-runtime/app/graph/shapes/` (new package) holds each workflow as a named module (`retrieve_reason_respond.py`, moved verbatim from the old `build.py`); `app/graph/build.py` is now `GraphFactory` (name → builder resolution + per-shape compile-and-cache) plus `validate_shapes()` (fail-fast startup check: every `active` agent must resolve to a known shape, a `placeholder` agent may omit one); `app/registry.py`'s `AgentDefinition` gained `graph_shape` (parsed from a new optional `zuno.graph_shape` OKF field, schema updated in `platform/okf/schema/zuno-okf-v0.2.schema.json`); Tekos's `agent.okf.md` declares `graph_shape: retrieve_reason_respond` (zero behavior change). `app/main.py`'s two routes are now `/v1/agents/{agent}/chat` and `/v1/agents/{agent}/runs/{run_id}/extract-memory`, both resolved through a new `_active_agent_or_404()` helper (404 for an unknown or placeholder agent) and `GraphFactory` - no route or graph is hardcoded to any agent name (agent-bff already called this exact generic pattern via its own `AGENT_NAME`-configured client, so no BFF change was needed); the extract-memory endpoint's classification fallback now reads the resolved agent's own OKF-declared baseline instead of a Tekos-specific constant. `graph_run_span` records `zuno.agent`/`zuno.graph_shape` trace attributes. 13 new tests (`tests/test_graph_factory.py`) cover shape-resolution fail-fast rules, GraphFactory caching, two structurally distinct shapes (Tekos's real one plus a minimal fixture-only second shape) serving concurrently on one instance, config-only shape switching for a fixture agent, and the generic dispatch helper resolving/refusing agents never named in any route. All pre-existing agent-runtime tests remain green.)
- **ADRs:** ADR-0342 (To be implemented -> Partially implemented; Implemented with WP-31)
- **Depends on:** WP-00 (done); WP-28 recommended first (the shared `knowledge.project` test)
- **Blocks:** WP-31 and every later agent slice
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root.

## Goal

Extend the Agent Runtime so `GraphFactory` selects among multiple named
LangGraph workflow shapes from the `AgentDefinition`, replacing the
hardcoded `/v1/agents/tekos/chat` route with generic per-agent dispatch that
fails fast on unknown/misconfigured shapes. Arkos's actual shape + task
bundle land in WP-31; this WP builds and proves the mechanism (with a
test-only second shape).

## ADR references

Primary: [docs/adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md](../../adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)

Acceptance criteria (satisfied by the Repo-changes steps below): shape
selection from `AgentDefinition` alone with no hardcoded per-agent route;
Arkos runs end to end on its own shape; Tekos/Arkos share
`knowledge.project` retrieval for the same `project_id` (ADR-0209's
scenario) through their own shapes and prompts/capabilities; switching a
shape is config-only; unit and end-to-end tests prove all of the above.

Body constraints: each shape is a distinct named module mirroring
`app/graph/build.py`; startup validation fails loudly (per `AgentRegistry`
fail-fast) if any agent doesn't resolve to exactly one known shape; tracing
records the serving shape; ADR-0039's platform-ceiling enforcement must not
be bypassed.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/agent-runtime/app/main.py` (the hardcoded route),
  `components/agent-runtime/app/graph/build.py` (the Tekos shape),
  the `GraphFactory` / `AgentRegistry` implementations under
  `components/agent-runtime/app/`, and `agents/tekos/agent.okf.md` (where a
  shape declaration will live in the OKF `zuno.` extension namespace).

## Repo changes (step by step)

1. **Shape registry:** make each workflow a named module under
   `components/agent-runtime/app/graph/` (move/wrap the existing Tekos flow
   as the first named shape, e.g. `retrieve_reason_respond`); `GraphFactory`
   maps shape name → builder and compiles per agent from `AgentDefinition`.
2. **OKF declaration:** agents declare their shape in the OKF `zuno.`
   extension metadata (follow the existing extension-field conventions,
   ADR-0006); Tekos's bundle gains the explicit declaration of its current
   shape (behavior unchanged).
3. **Generic dispatch:** `app/main.py` serves `/v1/agents/{agent}/chat`
   resolved through `AgentRegistry`; unknown agent → 404-equivalent
   deterministic error. Keep response/SSE behavior identical for Tekos.
4. **Fail-fast startup:** registry validation — every registered agent
   resolves to exactly one known shape; unknown shape name aborts startup
   with a clear error.
5. **Tracing:** add the serving shape name to the existing request trace
   attributes.
6. **Tests:** shape resolution unit tests (correct shape per agent; unknown
   shape → startup failure; unknown agent → deterministic error); an
   end-to-end test with Tekos's shape plus a minimal second test-only shape
   registered from fixtures proving two shapes serve on one instance and
   that switching a fixture agent's shape is config-only.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set.
- Tekos's observable behavior (routes may generalize, but
  `/v1/agents/tekos/chat` must keep working — BFFs depend on it).
- `agents/arkos/` content (WP-31).
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/agent-runtime/tests/ -q`
- `python3 -m py_compile` on touched runtime files
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `! grep -n "agents/tekos/chat" components/agent-runtime/app/main.py` (no hardcoded agent route; generic pattern only)

## Operator / human follow-up

None for the mechanism. Cluster verification rides WP-31's acceptance gate.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0342 →
  `Partially implemented (shape registry, generic dispatch, fail-fast validation and tests merged; Arkos second shape pending WP-31)`;
  index row to match; tracker → `Repo work merged`.
- After WP-31: ADR-0342 →
  `Implemented - see \`components/agent-runtime/app/graph/\`.`; index row
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet. (WP-31's brief
  carries the same instruction.)

## Out of scope / deferred

- Arkos's real shape, bundle, FE/BFF (WP-31).
- Comage/Advantage/Finage (WP-33/35/36, per ADR-0342's explicit scope note).
