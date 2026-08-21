# ADR-0057: Introduce Day 2 agent availability-test and stresstest operations

- **Status:** Implemented - repo work merged: `make day2|d2 test [agents|platform|all]`, the `platform/testing/day2_report.py` report engine (text/json/csv), and the discovery-driven availability checks are in place, and `ansible/roles/agents/tasks/check.yml`'s six hand-copied per-agent blocks are replaced by one shared, loop-driven include (WP-062, 2026-08-21). A first live run against a real cluster (2026-08-21) found and fixed two false-positive sources - see WP-062's own state notes: the agents component now intersects agent discovery with `gitops/charts/<agent>/` existing (excludes soursage/cognos, which have no deployment at all); the platform component's decision-5 target list no longer includes the four individual MCP servers (their NetworkPolicies restrict ingress to mcp-gateway's pod label only, ADR-0037 - this Job's identity was never going to reach them). Every other row (agent-runtime, ai-gateway, mcp-gateway, rag-service, all six real agents' frontends) passed live. A second live confirmation run (2026-08-21, same day) passed `14/14 passed overall - PASS`, confirming both fixes hold - all acceptance criteria discharged.
- **Target:** v0
- **Date:** 2026-08-21
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0056 restructured deployment into Day 0 (cluster prerequisites) / Day 1
(build + run the platform) sequencing. Neither stage answers "is the
already-deployed platform up right now" as a repeatable, on-demand operator
command - that question is currently answered only as a side effect of two
other things: `make day1 check agents`, which runs the ADR-0053 mandatory
release gate (20 scenarios, 100% security checks - a heavyweight, in-cluster
Job, not a quick health probe), and `ansible/roles/agents/tasks/check.yml`,
which hand-copies a ~35-line `/healthz` reachability block once per agent
(Tekos, Arkos, Comage, Advantage, Finage, Naveo each carry their own
near-identical block). Adding a new agent today means copy-pasting another
block by hand - exactly the kind of manual wiring that silently rots or
gets forgotten.

`evaluations/tekos/run_acceptance_gate.py`'s in-cluster Job
(`ansible/roles/agents/tasks/run_acceptance_gate.yml`) is also hardcoded to
Tekos alone (a single `KEYCLOAK_URL`/`FRONTEND_URL`/
`TEKOS_FRONTEND_CLIENT_SECRET`), even though its own Python layer
(`run_scenarios.py`) has been agent-parameterized since ADR-0342/WP-31.
Meanwhile `evaluations/tekos/stress_test.py` is a 530-line, Tekos-only,
exploratory battery whose own docstring explicitly invites a future agent
to "copy and adapt this file" rather than reuse it generically - there is
no shared, agent-parameterized runner for that content the way there is
for `run_scenarios.py`.

No component in the repository produces a JSON or CSV report today
(`evaluations/routing_report.py`, `benchmark.py` and every
`run_acceptance_gate.py` print a human-readable table plus one trailing
JSON summary line - none write CSV, none offer a format choice), and
`docs/adr/README.md`'s v0 number band has a genuinely free range directly
after this ADR's own number (ADR-0057-0100 are unused; the v0.1 stream
starts at ADR-0101) - the natural numeric and thematic continuation of
ADR-0056 (Day 0/Day 1) and ADR-0053 (`make check`).

This ADR defines the chassis for a new Day 2 stage: a `make d2 test`
command that only ever proves availability (cheap, safe, always runnable),
and the Makefile/Ansible dispatch, discovery mechanism and report engine
that both it and the stresstest content defined in
[ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md)
build on.

## Decision

1. **New `make day2|d2 <verb> [component]` namespace**, added to the root
   `Makefile` alongside `day0`/`d0`/`day1`/`d1`, sharing their exact
   dispatch idiom: `DAY_VERB`/`DAY_COMPONENT` read from word 2/3 of
   `MAKECMDGOALS`, a `DAY2_RECIPE` `define` block, every verb/component
   token declared as a no-op `.PHONY` target so Make doesn't error on it as
   an unknown goal. Verbs: `test`, `stresstest` (the latter's content is
   ADR-0058's decision). Components: `agents` (every agent bundle under
   `agents/`, collectively - matching Day 1's existing "agents" component
   granularity, which already treats every agent as one unit), `platform`
   (the shared services: agent-runtime, ai-gateway, mcp-gateway,
   rag-service, mcp-servers/*), `all` (default, both). Unlike Day 0/Day 1's
   static per-component lists, no new Make-level token is ever needed when
   a new agent is added - that discovery happens dynamically one layer
   down (decision 3).

2. **Dispatch mirrors Day 0/Day 1**: `make d2 test|stresstest [component]`
   runs `ansible-playbook ansible/playbooks/day2_test.yml` (or
   `day2_stresstest.yml`) `-e target_component=... -e
   report_format=...`, through the same `ANSIBLE_PLAYBOOK`/`INVENTORY`/
   `EXTRA_VARS` variables day0/day1 already use. `report_format` is new: an
   Ansible variable, default `text`, declared in
   `ansible/inventories/demo/group_vars/all.yml` as `day2_report_format:
   text` and overridable per-run through the Makefile's existing
   `EXTRA_VARS` mechanism (`make d2 test EXTRA_VARS="-e
   report_format=csv"`, or a `REPORT_FORMAT` Make variable forwarded the
   same way) - this is the "CSV extract if defined in an Ansible
   configuration var" mechanism.

3. **Dynamic discovery, not hand-maintained lists.** Both playbooks resolve
   "which agents exist" the same way `platform/supply-chain/validate_okf_bundle.py`,
   `platform/okf/generate_authorization_matrix.py` and
   `platform/okf/run_agent_contract_tests.py` already do - iterate
   `agents/*/agent.okf.md` (the `AGENTS_DIR.iterdir()` idiom, translated to
   an Ansible `find`/`set_fact` loop) - rather than a Python or Ansible
   list a human must remember to extend. A bundle appearing under
   `agents/` is enough for `d2 test` to check it, with zero code changes
   beyond the bundle itself.

4. **A shared report engine**, `platform/testing/day2_report.py`, used by
   `d2 test` and (per ADR-0058) `d2 stresstest`: a `Day2Result` dataclass
   (`agent, layer, id, category, passed, detail, duration_ms`) plus three
   renderers:
   - `text` (default) - the existing repo convention
     (`run_acceptance_gate.py`'s style: a human-readable table, per-category
     pass counts, an overall N/M line) printed to stdout/Job log. This is
     always printed regardless of `report_format`, satisfying "by default
     display a raw of the report."
   - `json` - one structured document (result list + summary), extending
     `run_acceptance_gate.py`'s existing trailing-JSON-line convention into
     the primary artifact, written to
     `evaluations/day2-reports/<timestamp>-<component>.json`.
   - `csv` - one row per result, the same fields flattened, written to
     `evaluations/day2-reports/<timestamp>-<component>.csv`.

   `report_format` selects which non-text artifact (if any) is additionally
   written; the text table is always printed either way.

5. **`d2 test` checks availability only** - no chat traffic, no
   credentials beyond what a `/healthz` GET already needs, and it must stay
   cheap and safe to run at any time (a contract ADR-0058's stresstest
   content must not weaken):
   - `agents` component: for every discovered agent bundle, `GET
     https://<agent>.<cluster_base_domain>/healthz`, expect 200 - the exact
     check six blocks in `check.yml` already hand-duplicate, now one loop.
   - `platform` component: `GET .../healthz` and `.../readyz` for every
     shared service already enumerated in
     `evaluations/tekos/run_scenarios.py`'s `SERVICE_HEALTH_URLS` map
     (agent-runtime, mcp-gateway, ai-gateway, rag-service, mcp-servers/*).
     These have no external Route, so this runs as a lightweight in-cluster
     Job - structurally the same pattern as
     `run_acceptance_gate.yml` (ServiceAccount, NetworkPolicy allow-list,
     ConfigMap-mounted script), but with no scenario/security payload, just
     the health map.

6. **`ansible/roles/agents/tasks/check.yml`'s six repeated per-agent
   `/healthz` blocks (Tekos, Arkos, Comage, Advantage, Finage, Naveo) are
   replaced by a single include of the new Day 2 availability logic**
   (decision 5's `agents` component, factored into
   `ansible/roles/agents/tasks/availability_check.yml`). `make day1 check
   agents` keeps its current behavior and output, now sourced from one
   shared, loop-driven implementation instead of six hand-copied blocks.
   The Arkos-specific AIAgent CR condition check and the OKF
   structural/placeholder checks in `check.yml` are unaffected - out of
   scope for this ADR.

## Consequences

A new, safe-by-default, always-runnable "is it up" command exists,
independent of the heavier ADR-0053 mandatory gate. The six hand-copied
`check.yml` blocks collapse into one generic, loop-driven path that scales
to new agents automatically instead of requiring a manual per-agent edit. A
reusable report engine exists for ADR-0058's stresstest content to build on
rather than each command reinventing table/JSON/CSV output independently.

## Security considerations

`d2 test` reads only `/healthz`/`/readyz` and public agent Routes - no
credentials, no PII, no write paths, and no load beyond a handful of GET
requests. The `platform` component's in-cluster Job reuses the existing
acceptance-gate Job's namespace/NetworkPolicy allow-list posture
(`zuno-ai-run`, `app.kubernetes.io/name` label scoping) rather than a
namespace-wide policy, so it does not widen what any workload in that
namespace can reach.

## Operational considerations

Report artifacts under `evaluations/day2-reports/` are Job-local/ephemeral,
not committed to Git; operators fetch them via `oc cp` or pod logs, the
same pattern the existing acceptance gate's log-fetch task already uses.
No new CI wiring is introduced - Day 2 commands are on-demand operator
tools, not blocking gates.

## Acceptance criteria

- `make d2 test agents`, `make d2 test platform` and `make d2 test` (all)
  run against a live cluster and print a text table by default; setting
  `report_format` to `json` or `csv` additionally produces the
  corresponding artifact under `evaluations/day2-reports/`.
- Adding a new `agents/<name>/agent.okf.md` bundle with a deployed
  frontend is checked by `make d2 test agents` with no code change beyond
  the bundle itself.
- `ansible/roles/agents/tasks/check.yml`'s six per-agent `/healthz` blocks
  are gone, replaced by one included, loop-driven task list; `make day1
  check agents` output is unchanged in substance.
- `python3 platform/docs/check_docs.py` passes.

## Related ADRs

- [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md)
- [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md)
- [ADR-0053](0053-make-make-check-an-end-to-end-acceptance-and-security-gate.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0058](0058-aggregate-existing-test-content-into-a-bulk-interaction-stresstest.md)
- [ADR-0342](0342-support-multiple-agent-graph-shapes-in-agent-runtime.md)
- [ADR-0502](0502-formalize-the-two-stage-agent-maturity-model.md)
- [ADR-0503](0503-make-each-okf-bundle-state-its-complete-authorization-contract.md)

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.
