# WP-51: Adaptation hooks and conformance suite (promotes ADR-0508)

- **State:** Not started
- **ADRs:** ADR-0508
- **Depends on:** WP-49 (fixtures consumed at the pin); runs in
  parallel with WP-50
- **Blocks:** WP-52
- **Estimated files touched:** ~8 (A, in zuno-okf) + ~10 (B) + ~12 (C)

> Execute this brief as a standalone task. Parts are independently
> committable; Part A lands in zuno-okf, Parts B/C in zuno-demo.

## Goal

Every OKF-consuming component confines its OKF reads to one designated
hook module, and every hook passes the zuno-okf conformance fixture
suite at the pinned ref in blocking CI, with a startup version
handshake against `okf-package.yaml`.

## ADR references

ADR-0508 clauses 1–4. Hook designations: agent-frontend
`internal/okf/`; agent-runtime `app/registry.py`; mcp-gateway
`app/agent_declarations.py`; agent-bff — new module owning the
`agent_<name>` derivation; ai-gateway — new module wrapping policy/
budget reads.

## Preconditions (verify before starting)

- WP-49 merged (pin + fetch available to component CI).
- Component test prerequisites from memory: mcp-gateway and
  agent-runtime tests need venvs built from each component's own
  requirements.txt; agent-frontend Go tests need a Redis at
  localhost:6379 (throwaway container).
- Read: the three existing parsers; `components/agent-bff/main.go`'s
  entitlement derivation; ADR-0511's ai-gateway budget-config reader
  if WP-54 has merged.

## Repo changes (step by step)

**Part A — fixtures (zuno-okf):**
1. Finalize `conformance/`: valid bundles (each graph shape, task with
   ui/quota/project marks), invalid + security-negative bundles
   (unknown `access.groups`, missing `allowed_tools`, task naming an
   undeclared knowledge domain, bad frontmatter type) — each paired
   with an expected-parse-result JSON (or expected-rejection marker).
   Set `okf-package.yaml`'s schema version.

**Part B — Go hooks (zuno-demo):**
2. agent-frontend: formalize `internal/okf/` as the hook (audit for
   OKF reads outside it; move any); add the fixture-driven test
   (parse every fixture at the pin, compare to expected) + the startup
   version check with its supported range; blocking in component CI.
3. agent-bff: new `internal/okfhook/` owning entitlement derivation
   (`agent_<name>`) — `main.go` consumes it; same fixture test (for
   the subset it parses) + version check.

**Part C — Python hooks (zuno-demo):**
4. agent-runtime (`registry.py`), mcp-gateway
   (`agent_declarations.py`), ai-gateway (new hook wrapping its
   policy/budget reads): same pattern each — boundary audit,
   fixture-driven test, startup version check.
5. All five components: a light CI lint (grep-level) that OKF file
   reads appear only under the hook path.

## What NOT to touch

Standard list; plus: **no shared parsing library in either language**
(ADR-0508 clause 4 — parsers stay per-component); no behavior changes
beyond moving reads behind boundaries (fixture results must match
current parsing, or the divergence is a real finding to record, not
silently normalize).

## Acceptance checks

- All five hook fixture tests green at the pin; flipping one
  expected-result value fails the right component only (restore after
  proving).
- A mismatched `okf-package.yaml` version fails each component fast at
  startup with a named error (component test).
- Boundary lint green; full component suites green; `check_docs.py`
  passes.

## Operator / human follow-up (not executable by the model)

None (component CI only; deploys ride the next normal rollout).

## Status updates (then re-run check_docs.py)

On all three parts merged: ADR-0508 → `Implemented - see the
conformance/ tree in zuno-okf and each component's hook module.`
Index + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Mounted-content source order in hooks (WP-52 adds it).
