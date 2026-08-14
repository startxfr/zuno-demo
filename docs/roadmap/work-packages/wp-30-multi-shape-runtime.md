# WP-30: Multi-shape Agent Runtime

- **State:** Not started
- **ADRs:** ADR-0342 (To be implemented -> Partially implemented; Implemented with WP-31)
- **Depends on:** WP-00 (done); WP-28 recommended first (the shared `knowledge.project` test)
- **Blocks:** WP-31 and every later agent slice
- **Estimated files touched:** ~8

> Execute this brief as a standalone task from the repository root.

## Goal

Extend the Agent Runtime so `GraphFactory` selects among multiple named
LangGraph workflow shapes from the `AgentDefinition`, and replace the
hardcoded `/v1/agents/tekos/chat` route with generic per-agent dispatch that
fails fast at startup on unknown/misconfigured shape references. Arkos's
actual shape + task bundle land in WP-31; this WP builds and proves the
mechanism (with a test-only second shape).

## ADR references

Primary: [docs/adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md](../../adr/0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)

Acceptance criteria (verbatim):

> - `GraphFactory` builds/selects at least two distinct graph shapes (Tekos's existing one, plus Arkos's) from `AgentDefinition` alone, with no per-agent hardcoded route in `app/main.py` beyond generic dispatch.
> - Arkos runs a real task end to end through its own graph shape.
> - Tekos and Arkos both successfully retrieve `knowledge.project` content for the same `project_id` (ADR-0209's acceptance scenario), each through its own graph shape and its own task prompts/capabilities.
> - Changing which graph shape an agent uses is a configuration/registration change, not a runtime code change to the other agent's path.
> - Unit tests cover graph-shape resolution/selection; an end-to-end test exercises both Tekos's and Arkos's graphs against the same running Agent Runtime instance.

(The Arkos-specific bullets are discharged by WP-31; this WP owns the
mechanism bullets: shape selection, generic dispatch, config-only change,
unit tests.)

Body constraints: each shape is a distinct named workflow module mirroring
`app/graph/build.py`; startup validation confirms every registered agent
resolves to exactly one known shape, failing loudly (consistent with
`AgentRegistry` fail-fast); tracing records which shape served a request;
platform-ceiling enforcement from ADR-0039 must not be bypassed.

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
