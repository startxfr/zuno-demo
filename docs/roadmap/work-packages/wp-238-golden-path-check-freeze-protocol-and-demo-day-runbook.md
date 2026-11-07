# WP-238: Golden-path check, freeze protocol and demo-day runbook

- **State:** Repo work in review
- **ADRs:** [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md)
- **Depends on:** none
- **Related:** [WP-136](wp-136-webinar-demo-orchestration.md) (`make demo check`), [WP-208](wp-208-five-experiences-demonstration.md) (the five-experiences script and its known defects), [WP-174](wp-174-tekos-to-arkos-delegation-on-demo333.md) (the delegation check)
- **Target:** v0.15
- **Estimated files touched:** ~12: `evaluations/golden_path_probe.py` and its test, `ansible/playbooks/demo_golden_path.yml`, `Makefile` (the `golden-path` demo verb), the CI step, `docs/demo/freeze-protocol.md`, `docs/demo/golden-path.md`, `docs/demo/demo-day-2026-11-09.md`, `RELEASING.md`, the tracker and this brief

> Why: the demonstration of 2026-11-09 09:00 has four moments, and no check today sends a real turn through any of the
> five experiences. The freeze procedure that protected earlier demonstrations is not in the repository, and a push to
> `devel` is a deployment. Every cluster action needs the user's go; the probes themselves are read-only.

## Goal

`make demo golden-path` proves each demonstration moment with a real call, the freeze has a written protocol, and the
2026-11-09 demonstration has a runbook with its fallbacks.

## Steps

1. **Freeze protocol** (`docs/demo/freeze-protocol.md`, ADR-0605 clause 3). Who is told (every working session that can
   act on the cluster, found with the session list), what is named (namespaces, Applications, make verbs), what stays
   allowed (file edits, local commits), the break-glass rule, the end of the freeze. Include the 2026-11-02 lesson: a
   green control plane is not a working path; prove it with a run.
2. **Deployment branch** (`RELEASING.md`). Say what is true: the live Applications track `devel` with automated sync, so
   a push to `devel` is a deployment; `main` carries the tags.
3. **Probes** (ADR-0605 clause 1). `evaluations/golden_path_probe.py`, run by `make demo golden-path`
   (`ansible/playbooks/demo_golden_path.yml`), one row per moment, read-only:
   - UnifAI: `evaluations/demo_presenter_probe.py` signs in; add one Tekos turn in the `agent-tekos` workspace, then
     cancel the session (`session.cancel`).
   - Open WebUI, OpenClaw, Dify, kagent, Zuno Code: run the role prechecks, then get one model answer under the
     client's identity. Use the experience's own API where it has one for a persona credential. Otherwise, and as a
     minimum, check that the ai-gateway counted a call with `client=<azp>` within the run window. Write down which path
     each experience uses.
   - Lightspeed: the existing health probe plus one question.
   - Delegation: a delegating run, then `platform/testing/a2a_delegation_check.py --delegator arkos --target tekos
     --since <run window>`.
   - Approval: run only when the pinned UnifAI release has a proven approval relay; otherwise report `not in this
     demonstration`.
   - Sovereignty: one C3 turn answered by a local model (routing in the ai-gateway audit line), one seeded guardrails
     detection, and the trace found in Tempo by run id.
   - World model: a placeholder row that reports `roadmap` until ADR-0604 ships a probe.
4. **Manual checklist** (`docs/demo/golden-path.md`): the screens a person checks, one line each, with what must be seen.
5. **Demo-day runbook** (`docs/demo/demo-day-2026-11-09.md`): order of the moments, timings, accounts (names and Vault
   paths only), the named exceptions with their fallback (D1 Dify stall: restart the run; D11 is install-only;
   approval: UnifAI 0.1.64 was pinned on demo333 on 2026-11-07 with the approval relay proven (approve 200, stale id 409), so the approval step is live; if its probe fails on the morning, show the delegation without it; world model: roadmap slide), the frozen sessions
   and the baseline (clause 4).
6. **Runs:** dry run Sunday 2026-11-08 14:00 (fix what fails), baseline at the start of the freeze (20:00), then Monday
   07:30 and 08:30. Record each result in the runbook.

## First live run (2026-11-07, user's go)

Every required moment passed on demo333 after one fix: the delegation moment first required a delegated tool call in
the mcp-gateway audit, which a rejected approval never produces (nothing runs). It is now judged on the a2a-gateway's
access line for the call to Tekos (`judge_delegation`). Results are in the
[demo-day runbook](../../demo/demo-day-2026-11-09.md#golden-path-results).

## Acceptance

- `make demo golden-path` reports one row per moment, each pass or fail with its evidence, in about 15 minutes.
- The dry run and the baseline run are recorded in the runbook; every failure has an owner or a fallback.
- `docs/demo/freeze-protocol.md` exists, and the freeze of 2026-11-08 20:00 was announced and acknowledged by every live
  working session.
- ADR-0605 can then move to `Implemented`.
