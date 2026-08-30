# WP-102: Custom AAP execution environment carrying `kustomize`

- **State:** Not started.
- **ADRs:** ADR-0418 (clause 6 - Workflow Template Day 2 live verification).
- **Depends on:** WP-095 (Workflow Templates registered and DAG-verified).
- **Unblocks:** a full green `zuno-day2-check-workflow` run (currently
  blocked on the `agents` node alone).

> Execute this brief as a standalone task from the repository root.

## Goal

Every Job/Workflow Template in this repo runs under Controller's stock
`ee-supported-rhel9` execution environment (`registry.redhat.io/
ansible-automation-platform-27/ee-supported-rhel9`) - nothing in
`gitops/charts/aap-config` assigns a custom one. Day 2's `agents` check
task (`ansible/roles/agents/tasks/run_acceptance_gate.yml`'s
`apply_kustomize.yml` include, ADR-0053's acceptance gate) shells out to
the `kustomize` CLI binary, which that stock EE does not ship - confirmed
live 2026-08-30 running `zuno-day2-check-workflow` for real (job 335,
node `agents`/job 353: `/bin/sh: line 1: kustomize: command not found`,
`rc=127`). This is the first Day 2 AAP run to ever reach that task - it
would fail identically on any future Day 2 `check`/`install` launch
through AAP until fixed.

## ADR references

ADR-0418 clause 6 - Day 2 Workflow Template live verification is complete
for the DAG/edges themselves (WP-095's own live pass confirmed the
`rag`/`rag-ingestion`/`mcp` parallel edge), but a full green end-to-end
run is blocked on this gap, which is outside the Job/Workflow Template
mechanism ADR-0418 itself decided.

## Scope (not yet designed - this WP starts from a blank slate)

- Build (via `ansible-builder`, matching how `ee-supported-rhel9` itself
  is built upstream) a custom EE image layering `kustomize` onto the
  stock base - not a from-scratch image, to keep every other tool/
  collection Controller already relies on intact.
- Publish it somewhere Controller can pull from (this repo's existing
  Quay/registry path - see the "Build chain: two parallel paths" pattern
  already used for component images) and register it in Controller
  (`POST /api/controller/v2/execution_environments/`), then assign it to
  the affected Job Templates (`zuno-day2-check`/`zuno-day2-install` at
  minimum - audit whether any other Day 1/Day 2 check task shells out to
  a CLI tool the stock EE also lacks, e.g. `helm`, before assuming
  `kustomize` is the only gap).
- Decide whether to assign the custom EE narrowly (only the Job Templates
  that need it) or broadly (every Job Template, for consistency) - narrow
  is probably right given ADR-0418's own least-privilege-by-default
  posture elsewhere in this ADR's credential design.

## Out of scope / deferred

- Any change to `verify_okf_signatures.yml`'s own logic - the unrelated
  `.rc`/`no_log` reporting bug in that file was found in the same live run
  and already fixed directly (not part of this WP).
- Re-signing any agent bundle whose signature is stale - a data-state
  issue, not an execution-environment one (see WP-31/33/35/36's own
  retroactive-signing work for that).
