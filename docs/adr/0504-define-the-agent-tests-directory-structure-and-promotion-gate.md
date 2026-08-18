# ADR-0504: Define the agent tests directory structure and promotion gate

- **Status:** Implemented - see `platform/okf/run_agent_contract_tests.py` and `agents/*/tests/` (WP-46, 2026-08-18; the ADR defines structure, not content - suites fill at promotion)
- **Target:** OKF v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team

## Context

Every full-skeleton agent reserves an `agents/<name>/tests/` directory,
and every one of them contains exactly one one-line stub README. Nothing
defines what belongs there, so nothing ever went there. Meanwhile the
platform already has two real, *separate* verification layers the
directory must not duplicate: structural bundle validation
(`validate_okf_bundle.py`, `check_knowledge_refs.py`, the JSON Schemas
under `platform/okf/schema/` — platform-wide, agent-agnostic) and
behavioral evaluation (`evaluations/<name>/scenarios.yaml`, the
20-scenario/75 % gates of ADR-0027/ADR-0028 run by the shared ADR-0342
runner — cluster-dependent, gate-scoped). What no layer covers today is
**per-agent contract self-consistency**: that Finage's declared tool
ceilings actually intersect with the business roles its users hold, that
a task's `live_read_tool` is one of its own `allowed_tools`, that a
prompt file carries the frontmatter Agent Runtime's registry requires
(the exact bug WP-41 found in the generator, caught only by the
agent-runtime suite failing on import).

## Decision

1. **`agents/<name>/tests/` holds per-agent contract tests in three fixed
   subdirectories:**
   - `contract/` — bundle-level self-consistency: frontmatter conforms to
     the schemas; every `allowed_tools` entry exists in
     `policies/tools/tool-policy.yaml` and every `allowed_knowledge`
     entry in `policies/knowledge/knowledge-policy.yaml`; each declared
     resource has a non-empty `allowed_groups` intersection with the
     agent's intended business roles; the ADR-0503 authorization matrix
     and deployment snapshot are current.
   - `tasks/` — per-task assertions: `live_read_tool ∈ allowed_tools`;
     `primary_task ∈ zuno.tasks`; a `project_required` task (ADR-0512)
     names no tool the project context cannot scope.
   - `prompts/` — prompt lint: required OKF frontmatter (`type: prompt`),
     referenced-by-a-task check, golden-format checks where a task
     defines one.
   A `tests/README.md` states how the suite runs and this ADR's layer
   boundaries.

2. **The suite is composed into the existing repo-side lint chain**, next
   to `validate_okf_bundle.py` in `.github/workflows/lint.yml`'s
   policy-as-code job and runnable locally from the repository root. It
   needs no cluster, no model calls and no credentials — anything that
   does belongs in `evaluations/<name>/`, which this ADR leaves untouched
   as the sole behavioral layer.

3. **A filled `tests/` directory is a Stage-2 promotion criterion**
   (ADR-0502 criterion c). Stage-1 agents have no `tests/` directory at
   all — the generator does not emit one, and the promotion checklist
   (`platform/templates/agent/PROMOTION.md`) is where the directory is
   born.

4. **Test content is explicitly out of scope for the OKF v0.1 work
   packages.** WP-46 lands the structure (subdirectories + READMEs + the
   runner wiring) with zero test content; filling the suites is
   promotion-time work, per agent, owned by whichever WP or slice
   promotes that agent.

## Consequences

The three verification layers get named boundaries: schema/structural
(platform-wide), contract (per-agent, repo-side, this ADR), behavioral
(per-agent, cluster-side, ADR-0027/0028). Generator bugs of the
WP-41 class fail in lint instead of surfacing as an unrelated component
suite's import error. The empty-stub pattern ends: a `tests/` directory
now either has real content or does not exist.

## Security considerations

Contract tests are pure static analysis of repository files — no
credentials, no network. They strengthen the authorization story by
making "declared but unusable" and "declared but ungoverned" states fail
CI rather than lurk; they must never weaken it by being mistaken for the
enforcement path (which remains ADR-0036/ADR-0039) or for the
security-negative behavioral tests in `evaluations/<name>/`.

## Operational considerations

One new blocking lint step, colocated with the existing policy-as-code
job; runtime is file parsing only. When ADR-0506 moves `agents/` to the
`zuno-okf` repository, the contract suite moves with it (it is
self-contained by construction — repository files only), becoming part of
that repository's own CI.

## Acceptance criteria

- The target structure and runner wiring exist; running the suite against
  the current tree passes with zero test content present.
- The promotion checklist names "fill `tests/` per ADR-0504" as a Stage-2
  criterion.
- `python3 platform/docs/check_docs.py` passes.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md)
- [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0502](0502-formalize-the-two-stage-agent-maturity-model.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)
- [ADR-0506](0506-extract-okf-content-into-a-standalone-zuno-okf-repository.md)
- [ADR-0512](0512-introduce-project-bound-tasks-with-salesforce-verified-context.md)
