# Testing and Evaluation

Last reviewed: 2026-11-19

How the platform is tested, from a unit test to a stress campaign. Each layer says what it proves and how to run it.

| Layer | What it proves | How to run it |
|---|---|---|
| Documentation against the code | Links and anchors resolve; the ADR index matches the ADR files; Makefile verbs, demo tables and stress tables match the repository | `python3 platform/docs/check_docs.py` (also in CI, `.github/workflows/lint.yml`) |
| Unit and contract tests | Components and platform scripts behave as designed | The test files next to each component and under `platform/*/tests`, run in CI |
| Component checks | A deployed component is installed and healthy | `make dN check [component]` (N = 0 to 3; [configuration](../platform/configuration.md) lists the components) |
| Acceptance and security gate | A signed-in user reaches each agent and gets answers under policy | `make d2 check agents` ([acceptance criteria](acceptance-criteria.md)) |
| Agent evaluation | Quality of the agents on scenarios (20 per agent, 75% target) | `evaluations/` and the TrustyAI and EvalHub path ([agent evaluation](agent-evaluation.md), [scenario](../demo/scenarios/rhoai/evaluation-trustyai-evalhub.md)) |
| Golden path | The live moments of the demos answer for real | `make demo golden-path` ([golden path](../demo/golden-path.md)) |
| Demo rehearsal | A scenario page plays from start to end | `make demo rehearse <id> 5\|15` ([demo catalogue](../demo/README.md)) |
| Stress | Load, saturation, chaos, state checks, the isolation of budgets | `make d3 stresstest PROFILE=...` ([stresstest runbook](../platform/stresstest.md)) |
| Hardware smoke test | One component on a real GPU | [World-model GPU smoke test, 2026-11-08](world-model-gpu-smoke-2026-11-08.md) |

Also: the [testing strategy](testing-strategy.md) is the one-paragraph statement of the layers above, and a failure of a check is first read
in [troubleshooting](../platform/troubleshooting.md).
