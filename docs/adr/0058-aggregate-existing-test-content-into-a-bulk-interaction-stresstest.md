# ADR-0058: Aggregate existing agent test content into `make d2 stresstest`, with a bulk-interaction load mode

- **Status:** Implemented - repo work merged: `make day2|d2 stresstest [agents|platform|all]` aggregates contract/scenario/security/gate/stress_test content per discovered agent (contract tests attributed via a control-node-only pass; the other four layers via a generalized, per-agent in-cluster Job reusing the ADR-0053 acceptance-gate Job mechanism), plus a bulk-interaction load mode (interactive `BULK=<n>` prompt, or non-interactive default) replaying each agent's own `scenarios.yaml` message content (WP-063, 2026-08-21). Live cluster confirmation (2026-08-21, `make d2 stresstest BULK=25`) proved the mechanism itself end to end - discovery, all five content layers, bulk mode, and correct non-zero exit on failure all worked exactly as specified; every acceptance criterion below is met. That run's content result was `166/178 passed overall - FAIL`, but the 12 failures are new live application-layer findings (tekos code-generation and model-routing 429s, a missing-citation scenario, three arkos 500/502 scenario errors - see WP-063's dated note), not a defect in this ADR's own mechanism.
- **Target:** v0
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team

## Context

[ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md)
establishes the Day 2 chassis - the `make d2` namespace, dynamic
agent/service discovery, and a shared text/JSON/CSV report engine - and
scopes `d2 test` to availability only. This ADR defines what `d2
stresstest` actually runs.

Every Stage-2 agent already carries real, runnable test content: schema-
level contract tests (`agents/<agent>/tests/{contract,tasks,prompts}`,
ADR-0504), a fixed 20-scenario acceptance battery
(`evaluations/<agent>/{scenarios.yaml,run_scenarios.py}`, ADR-0027/0028),
100%-mandatory security-negative checks (`security_checks.py`) and
remaining capability gates (`gate_checks.py`). Tekos additionally has
`evaluations/tekos/stress_test.py`, a 530-line exploratory battery whose
own docstring explicitly invites a future agent to "copy and adapt this
file" the same way `scenarios.yaml` is already per-agent content while
`run_scenarios.py` stays shared. None of this content is runnable together,
generically, per agent, on demand - an operator who wants the full picture
for one agent today has to know and invoke four separate scripts by hand.

The in-cluster Job that runs the acceptance-gate content
(`ansible/roles/agents/tasks/run_acceptance_gate.yml`) is also hardcoded to
Tekos alone, even though its own Python layer
(`run_scenarios.py`) has been agent-parameterized since ADR-0342/WP-31 -
the Ansible/Job layer never caught up.

Separately, there is no concurrency, load, or "bulk interaction" testing
anywhere in this repository (`evaluations/`, `components/*/tests`) -
confirmed by search across `concurren`, `load_test`, `bulk`,
`asyncio.gather`, `ThreadPoolExecutor`. Despite its filename,
`stress_test.py` is not a load test; it issues one sequential request per
functional case. This ADR introduces that missing capability, deliberately
built entirely out of already-authored prompt content rather than inventing
new adversarial or load-test-specific fixtures.

## Decision

1. **`d2 stresstest` runs every layer of existing content that exists for
   each agent discovered by ADR-0057's mechanism**, skipping gracefully
   what a given agent doesn't have yet: Stage-1 stub agents simply produce
   an explicit "no content" row, never a failure - the same
   informational, non-blocking posture `stress_test.py`'s own docstring
   already established for why it stays out of the mandatory gate, now
   applied platform-wide. The layers, run in order per agent:
   - `platform/okf/run_agent_contract_tests.py` (schema-level, no cluster).
   - `evaluations/<agent>/run_scenarios.py` (the fixed scenario battery).
   - `evaluations/<agent>/security_checks.py` and `gate_checks.py`, when
     present.
   - `evaluations/<agent>/stress_test.py`, when present (today: Tekos
     only).

   Every result normalizes into ADR-0057's `Day2Result` shape and renders
   through the same text/json/csv report engine - one unified report
   across every layer and every agent, replacing four separate ad hoc
   per-script tables.

2. **The acceptance-gate Job mechanism is generalized from Tekos-only to
   loop over every discovered agent that has `evaluations/<agent>/`
   content**, reusing the same ConfigMap-bundling, credential-mounting and
   internal-CA-trust mechanism `run_acceptance_gate.yml` already has,
   parameterized by agent name instead of the single hardcoded
   `tekos`/`TEKOS_FRONTEND_CLIENT_SECRET` (mirroring how `run_scenarios.py`
   is already parameterized by an `AGENT` environment variable at the
   Python layer, per ADR-0342/WP-31). This is purely an
   execution-generalization of the existing mechanism: it does not change
   ADR-0053's mandatory-gate semantics or its 75%/100% thresholds. `d2
   stresstest`'s own exit code and output stay informational and
   non-blocking, exactly like `stress_test.py`'s existing posture - it
   never feeds `make day1 check agents` / the ADR-0053 mandatory gate.

3. **Bulk-interaction load mode** (new capability - no existing pattern to
   generalize). `make d2 stresstest` interactively prompts at the shell,
   before dispatch, for a bulk interaction count, offering a sane default
   (e.g. 10) if the operator presses enter; a non-interactive or scripted
   invocation supplies it directly (`make d2 stresstest BULK=25`),
   skipping the prompt entirely (also the path taken automatically when
   stdin is not a TTY). The chosen count is forwarded as `-e
   bulk_interactions=N` to the stresstest playbook and baked into the Job.

   The interaction content itself is not new: per the user's own framing
   ("rely on existing test content"), bulk mode replays the same prompts
   already defined in each in-scope agent's `scenarios.yaml` and
   `stress_test.py`, cycling through them to reach the requested count,
   sent sequentially per agent. Each call's pass/fail reuses that prompt's
   existing assertion where derivable (e.g. "got a non-empty reply",
   "citations present"), plus its latency is recorded. The report gains a
   per-agent load-analysis summary (interaction count, error rate,
   p50/p95/max latency) alongside the functional per-check results from
   decision 1.

4. **Auto-coverage is binding policy, not an incidental side effect.**
   Because agent discovery (ADR-0057 decision 3) walks
   `agents/*/agent.okf.md`, and per-agent content discovery walks
   `evaluations/<agent>/*.py` plus `agents/<agent>/tests/` by file
   presence, adding a new agent or a new task under an existing agent
   requires zero changes to the stresstest engine itself - only the new
   content (scenarios, prompts, contract tests) needs to be authored, the
   same authoring step promotion already requires
   (ADR-0502/`platform/templates/agent/PROMOTION.md`). This ADR states
   that requirement as a binding rule the Day 2 stresstest engine must
   uphold, so any future change to it can be held to "does this still run
   automatically for a brand-new agent bundle with zero engine edits."

## Consequences

One command surfaces the full existing test estate for every agent instead
of requiring an operator to know and invoke four separate scripts per
agent. The acceptance-gate Job mechanism stops being Tekos-special-cased.
A genuinely new load/bulk-interaction signal exists where none did before,
grounded entirely in already-authored prompt content rather than invented
adversarial fixtures - keeping this ADR's scope to aggregation and
execution, not new test-content authoring.

## Security considerations

Bulk mode issues real chat traffic under the same demo-persona credentials
`run_scenarios.py` already uses - no new credential class is introduced. A
large `BULK` value is exactly the kind of real load ADR-0057's `d2 test`
deliberately stays free of; this ADR's bulk mode is the only Day 2 path
permitted to generate non-trivial traffic, and it must remain an explicit,
operator-invoked command only - never wired into CI, a cron job, or the
ADR-0053 mandatory gate.

## Operational considerations

Bulk mode's runtime scales with `BULK` x (prompts per agent) x (agents in
scope). The Job's `resources` request/limit and its wait-for-terminal-state
timeout must scale with the requested `BULK`, and the Makefile/playbook
should refuse an unreasonably large `BULK` without an explicit override, to
avoid an accidental denial-of-service against the demo cluster's shared
GPU/model capacity.

## Acceptance criteria

- `make d2 stresstest agents` runs contract, scenario, security, gate and
  stress-test content for every agent that has it, and reports an explicit
  "no content" row (not a failure) for agents that don't.
- `make d2 stresstest` (interactive) prompts for a bulk count and honors
  it; `make d2 stresstest BULK=N` skips the prompt and honors `N` directly,
  including when stdin is not a TTY.
- The rendered report (text, json, or csv) includes both the functional
  per-check results from decision 1 and the bulk-mode load-analysis
  summary from decision 3.
- `d2 stresstest`'s exit code and output never feed `make day1 check
  agents` / the ADR-0053 mandatory gate - confirmed by the mandatory gate's
  own tests/behavior being unaffected by a `d2 stresstest` run.
- `python3 platform/docs/check_docs.py` passes.

## Related ADRs

- [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md)
- [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md)
- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0057](0057-introduce-day-2-agent-availability-test-and-stresstest-operations.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0502](0502-formalize-the-two-stage-agent-maturity-model.md)
- [ADR-0504](0504-define-the-agent-tests-directory-structure-and-promotion-gate.md)

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.
