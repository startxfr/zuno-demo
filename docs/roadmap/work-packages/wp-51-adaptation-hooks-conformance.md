# WP-51: Adaptation hooks and conformance suite (promotes ADR-0508)

- **State:** Repo work in review
- **ADRs:** ADR-0508
- **Depends on:** WP-160 (fixtures consumed from the admitted corp
  release; WP-49 and WP-50, its original predecessors, were abandoned on
  2026-10-22 with ADR-0507)
- **Blocks:** none (WP-52 abandoned on 2026-10-22)
- **Note (2026-10-22):** ADR-0508 still stands, but the repository it
  names is now `startxfr/zuno-demo-agents` (ADR-0576) and the consumers
  left after WP-156 are mcp-gateway, mlops, `unifai-operator` and the
  ADR-0581 generator. Re-scope Parts A-C to those before starting.
- **Re-scoped (2026-10-23, WP-165):** done below. agent-frontend,
  agent-bff and agent-runtime are retired (WP-156); `zuno-okf` was never
  created; the fixtures and the schema version come from the agents
  repository and reach this platform inside the admitted release. The
  original parts are kept below as history, superseded by this re-scope.
- **Estimated files touched:** ~6 (A, in zuno-demo-agents) + ~8 (B, in
  zuno-demo); the `unifai-operator` hook (`internal/okf/`, ADR-0575) is
  that fork's own work.

## Progress (2026-10-24)

Decisions taken with the user: fixtures live in `zuno-demo-agents`
(`conformance/`, prepared on a local branch and consumed through
`ZUNO_OKF_CONFORMANCE_DIR`; nothing published yet); every reader accepts
`okf_version` `v0.2` and `v0.3` only (ADR-0579 clause 6: the admitted release
0.3.0 is still entirely v0.2, so "v0.3 only" would refuse it); parsers stay
per component (ADR-0508 clause 4).

Done in this repository:

- mcp-gateway hook (`agent_declarations.py`) refuses a missing or unsupported
  `okf_version` on the agent index and on every task, naming file and version;
  `tests/test_okf_conformance.py` runs every case through it.
- Admission hook (`admit_okf_bundle.py` `agents_view`, behind
  `generate_stack_config.py`) does the same through `checked_frontmatter`;
  `platform/okf/tests/test_okf_conformance.py` runs every case through it.
- `platform/okf/check_okf_read_boundary.py` (CI: lint.yml) fails on a new
  direct OKF read outside the hooks; four pre-existing reads are a baseline
  that may only shrink (two tekos evaluation scripts, `check_docs.py`,
  `day2_contract_attribution.py`).
- mlops hook (`_task_system_prompt` in `components/mlops/src/mlops.py`) refuses a
  missing or unsupported `okf_version` by name; three tests in `test_mlops.py`
  (versions, refusals, conformance cases).
- Proven: flipping one expected value fails the matching hook only; the live
  release 0.3.0 still loads (8 agents) through both hooks.

Remaining before this WP closes:

- The evaluations reader, then empty the lint baseline.
- The conformance cases are merged on zuno-demo-agents devel (PR #7). The
  release builder now ships them as an optional corp-artifact layer (branch
  `prep/wp51-release-conformance`, ADR-0577 amendment 2026-10-24) and
  `admit_okf_bundle.extract` unpacks it; they reach this repo's CI once a
  release carrying the layer (0.3.1) is promoted into `platform/okf/agents.lock`
  (release version bump and promotion are the maintainer's), at which point the
  fixture tests stop skipping.
- Finding to settle: the admission reader (`okf_narrowing.py`) skips documents
  that are not v0.3 instead of refusing them; harmless today, worth a decision
  when v0.2 stops being readable.

## Re-scoped plan (2026-10-23)

The OKF readers left in `zuno-demo` after the cutover (WP-165):

| Reader | Hook | Reads |
|---|---|---|
| mcp-gateway | `components/mcp-gateway/app/agent_declarations.py` | agents, tasks (entitlement factors) |
| ADR-0581 generator and admission | `platform/supply-chain/admit_okf_bundle.py` (`agents_view`, `frontmatter`), `platform/okf/generate_stack_config.py` | agents, tasks, corp policies |
| mlops | `components/mlops/src/mlops.py` (task prompts) and the evaluation gates | agents, corp policies |
| evaluations | `evaluations/common/okf_release.py` (path only), the per-agent `security_checks.py` | agents, corp policies |

- **Part A (zuno-demo-agents):** a `conformance/` fixture set (valid
  bundles of each graph shape, invalid and security-negative bundles, each
  with its expected parse result), published inside the release or as its
  own attested artifact, and the OKF schema versions the release declares
  (`okfVersion` in `okf-index.json`).
- **Part B (zuno-demo):** each reader above confines its OKF reads to its
  hook; a fixture-driven test per hook against the fixtures of the
  admitted release (through `platform/okf/release_cache.py`); a startup
  version check against the schema versions the hook supports (mcp-gateway
  at load, the generator and admission at run); a grep-level CI lint that
  OKF file reads appear only under the hook paths. No shared parsing
  library (ADR-0508 clause 4).

Acceptance: every hook's fixture test green against the locked release;
flipping one expected result fails the right hook only; an unsupported
`okfVersion` fails each reader fast with a named error; `check_docs.py`
passes.

The sections below are the original 2026-08-18 plan, superseded by this
re-scope.

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
