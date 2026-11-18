# ADR-0616: Prepare and play every catalogue demo through one make demo lifecycle

- **Status:** Implemented
- **Target:** v0.16
- **Date:** 2026-11-14
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0550](0550-demonstrate-sovereign-ai-through-classification-specialization-and-resilience.md) in part (its "Demo automation" section: the `make demo check|reset|step-1..5` webinar helpers)
- **Related:** [ADR-0605](0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md), [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md), [ADR-0536](0536-live-node-failover-drill-for-qwen-model-fallback.md), [ADR-0608](0608-keep-the-repository-the-only-source-of-cluster-state.md), [ADR-0604](0604-introduce-an-interactive-generative-world-model-experience.md), [ADR-0610](0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md)

## Context

The demo catalogue under `docs/demo/` (rewritten 2026-11-12 and 2026-11-13) holds 30 scenario pages, each with a
5-minute and a 15-minute version, and 6 workshops that chain them. It is the list of demonstrations the project wants to
give. The `make demo` verbs predate it: they are the helpers of a 20-minute webinar of September 2026 (WP-136,
ADR-0550), plus the catalogue-wide golden path and browser checks of November (ADR-0605, ADR-0606). A presenter who
picks a scenario today reads its page, runs its checklist by hand and types its commands. The owner asked on
2026-11-14 that every demo be prepared and played through `make demo` only, with the page saying what is left to the
presenter after each automated action or step.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | The webinar steps point to retired surfaces. | `ansible/playbooks/demo_step_1..4.yml` print `https://arkos.`, `tekos.`, `comage.` and `rhods-dashboard.` URLs; on 2026-11-14 `oc get route -A` on demo333 lists no such host. Step 4 names TrainJob `lora-tekos-sclvp` and a registry `zuno`; the only TrainJob is `lora-comage-4c28m` and no `ModelRegistry` instance exists. The agent runtime behind those URLs was retired by WP-156/WP-168 (2026-10-23/24). `docs/demo/scenarios/foundation/gitops-day0-3.md` already tells presenters to use the scenario pages instead. |
| F2 | Nothing links a catalogue page to automation. | Every page prepares the demo with a `## Before you start` checklist; three pages add an `## Appendix C - Setup` (`blender-3d.md`, `world-model.md`, `unifai-live-rag.md`). On 2026-11-09 the presenters ran only `make demo golden-path` ([demo-day runbook](../demo/demo-day-2026-11-09.md)). |
| F3 | The checks exist only for the whole catalogue. | `make demo golden-path` runs 14 probes (`evaluations/golden_path_probe.py`, `PROBES`), `make demo browser` 5 screens (`evaluations/browser/run.mjs`); a single demo is selected only by hand with `ONLY=`. |
| F4 | The freeze is a document, not a guard. | `docs/demo/freeze-protocol.md` lists the frozen commands; no tool refuses one. |
| F5 | No page has been played in its current form. | 38 pages under `docs/demo/` carry "Not rehearsed" in their status banner (2026-11-14). |
| F6 | The steps are regular and machine-readable. | The 30 pages share the same ten `##` sections in the same order. Steps are rows `\| M:SS \| Do \| Say \| You should see \|`: 157 rows in the 5-minute versions, 275 in the 15-minute versions, which start with "Run the 5-minute version, then:" and continue the clock from 5:00. Workshops already cite scenario steps by time stamp ("steps 10:30 and 12:30"). The Do cells hold 152 `oc` commands, nearly all reads. Four pages hold an extra block a parser must skip (the routing coding pair, the Blender prompt table, the quotas optional replay, the world-model prose). |
| F7 | CI syntax-checks every playbook. | `.github/workflows/lint.yml` runs `ansible-playbook --syntax-check` on each file of `ansible/playbooks/`; one playbook per step would add about 430 runs. |
| F8 | A checkout without `ansible/confidential.yml` sends `make dN` to AAP. | `resolve_aap_mode` (Makefile) falls back to `auto`; AAP runs `devel` from git, not the local tree. |
| F9 | The webinar probe left a copy of the persona password on the cluster. | Secret `demo-persona-probe-credentials`, ConfigMaps `demo-persona-probe-ca` and `demo-persona-probe-scripts` (67 days old) and Job `zuno-demo-persona-probe` in `zuno-ai-run`, created by `ansible/tasks/demo_persona_probe_job.yml` (2026-11-14). |

## Decision

**Every demo of the catalogue is prepared and played through one `make demo` lifecycle: each action and each step runs
one Ansible file of that demo, then prints the matching section of its page, and the page stays the source of truth.**

1. **Grammar and session.** `make demo use <id> 5|15` stores the demo, its version and the step position on the
   presenter's workstation; the other verbs act on that session, or on an explicit id for one command. The verbs are
   `list`, `use`, `status`, `check`, `install`, `start`, `step next|<N>`, `stop`, `uninstall`, `freeze on|off`,
   `rehearse <id> 5|15`, and the catalogue-wide `golden-path` and `browser`, kept as they are. A demo is played in the
   order status, check, install, start, step 1..x, stop, uninstall. A thin Makefile grammar calls a stdlib Python
   orchestrator under `platform/demo/` (WP-270).
2. **The page is the source of truth.** A step is one timed row of the version's `Time | Do | Say | You should see`
   table; its time stamp is its id. The 15-minute version is the 5-minute rows followed by the 15-minute rows. The
   blocks that are not steps are listed by name in the parser; an unknown table inside a version section fails CI
   (WP-270, WP-271).
3. **One directory per demo, every file mandatory.** `ansible/demos/<id>/` holds a manifest `demo.yml`, the six action
   files `status.yml`, `check.yml`, `install.yml`, `start.yml`, `stop.yml`, `uninstall.yml`, and one `steps/MM-SS.yml`
   per timed row. They are task files included by one runner playbook, `ansible/playbooks/demo_run.yml`. A file with
   nothing to do still exists and reports "Nothing to run." (WP-270, WP-271).
4. **`## Presenter lifecycle` replaces `## Before you start`.** Each page has `### Status`, `### Check`, `### Install`,
   `### Start`, `### Stop` and `### Uninstall`, in that order, each saying what the presenter does once the action's
   file has run, or "Nothing to do.". The content of the old checklist and of Appendix C moves there. The command prints
   the file's result first, then the section; for a step, the row's Do, Say and You should see, its position and the
   next step; on a failure, the page's `If something goes wrong` rows (WP-269 for the contract, WP-271 to WP-280 for the
   pages).
5. **Steps run reads only.** A step file runs the read-only commands of its Do cell, without a shell, through an
   allowlist (`oc get|describe|logs|explain|whoami|api-resources|version|auth can-i|adm top`, filters after a pipe,
   GET-only `curl`, `git log|show`, and the read-only `make` verbs a page shows on stage). A step that changes the
   cluster is declared in the manifest, never run by the step, and skipped by a rehearsal (WP-270).
6. **Install and uninstall manage the demo's own add-ons only.** The world-model GPU node and application, the Blender
   add-on on the workstation, the demo documents of the live RAG. A shared component is verified by `install` and never
   removed by `uninstall`, whose section then says "Nothing to do." (WP-274, WP-279).
7. **Guards.** Before an action that changes the cluster, the command prints what will change and asks the presenter to
   type the demo id. Without a terminal it refuses, unless `DEMO_CONFIRM` holds that exact id; there is no global yes.
   `demo_run.yml` checks the confirmation again. A change to the infrastructure layer (a GPU node, a MachineSet)
   requires the owner's double approval and never scales down an existing GPU node (WP-270, WP-279).
8. **Freeze marker.** `make demo freeze on|off` writes a marker on the presenter's workstation. While it is set,
   `install`, `uninstall` and `rehearse` refuse. The marker is local by decision; the freeze protocol adds it to the
   step where every session is contacted (WP-270, WP-272).
9. **Check and status.** `check` runs the demo's golden-path probes (`--only`), its browser check when it has one, and
   its own read-only assertions. `status` reads only: Applications, workloads, routes, whether the add-on is installed,
   the freeze marker and the session position; it makes no model call (WP-271 to WP-279).
10. **Workshops by composition.** A workshop's manifest lists its agenda: scenario rows (all of a version, or named
    time stamps), inline rows of its own page, and its own opening and close. Its actions chain the scenarios' actions
    with no duplicated file; probes and browser checks run once, merged (WP-280).
11. **Proof by automated rehearsal.** `make demo rehearse <id> 5|15` runs the whole sequence without pauses, changing
    actions included, and writes a report. Every demo is rehearsed in both versions before ADR-0616 is Implemented; mouse
    actions are not clicked, and `make demo browser` covers the screens. The world model is the named exception while
    no GPU capacity exists: it is rehearsed without its install (WP-273 to WP-281).
12. **Local execution.** The demo verbs never go through AAP. An action that delegates to a Day 0-3 playbook runs that
    playbook locally from a commit already on `origin/devel`; a step that shows a `make dN check` runs its local
    equivalent (WP-270).
13. **The webinar helpers are retired.** `make demo check` (the webinar preflight), `all-check`, `reset` and
    `step-1..5` are removed with their playbooks, `ansible/tasks/demo_persona_probe_job.yml` and
    `evaluations/demo_presenter_probe.py`. Their useful reads move into the per-demo checks. The GPU failover drill stays
    the Day-3 verb `make d3 scenario-failover-node`. The leftovers of F9 are deleted from the cluster with the owner's
    go (WP-272).
14. **CI keeps pages and files together.** A test fails when a page lacks a lifecycle section, when a timed row has no
    step file or a step file no row, when an action file is missing, when a step file runs a command outside the
    allowlist or leaves a Do command uncovered, when a workshop agenda does not resolve, or when a document names a
    `make demo` verb that does not exist (WP-271).

## Alternatives considered

- **One playbook per action and step under `ansible/playbooks/`.** Literal, but about 430 more syntax-check runs in CI
  (F7) and as many top-level playbooks. Task files included by one runner keep one Ansible file per action and step.
- **Pure data, no Ansible.** A manifest per demo interpreted by Python. Rejected: the owner asked for one Ansible file
  per action and step, and the platform's automation is Ansible.
- **Run the commands straight from the page.** The cells carry placeholders, line continuations and escaped pipes, and
  a page edit would become a code change on the cluster. Rejected for the allowlist and explicit step files.
- **Stateless commands** (`make demo step <id> 15 7`). Longer to type on stage, and `step next` needs a position
  anyway.
- **A freeze marker on the cluster** (a ConfigMap). Shared by all sessions, but created outside git, against ADR-0608.
  The owner chose the local marker.
- **Keep the webinar tools beside the new ones.** Two meanings of `make demo check` and dead URLs on stage.
- **Separate 15-minute tables.** The pages are cumulative by design; duplicating the 5-minute rows would let them drift.

## Consequences

- About 500 small YAML files under `ansible/demos/`. A page edit that adds, moves or removes a timed row needs its step
  file changed in the same commit; CI enforces it.
- A presenter types `make demo use <id> 5|15`, then `make demo step next`, and reads one section at a time.
- The presenter's workstation needs python3, PyYAML (shipped with Ansible), ansible-playbook and `oc` logged in.
- `docs/demo/README.md`, both templates and every page change shape once.

## Security considerations

- No step runs a command that changes the cluster, and no read runs through a shell. The allowlist refuses Secret
  reads, watches and follows, redirects, command chaining and substitutions other than `$(oc whoami -t)`, whose value
  is hidden in the output.
- `DEMO_CONFIRM` covers one demo id, never all; the runner playbook checks it again, so a direct `ansible-playbook` run
  is guarded too.
- Credentials are read at run time (Vault-backed Secrets through `oc`) and never printed or written to the session file.
- F9's Secret, a copy of the shared persona password, is deleted (clause 13).

## Operational considerations

- The session, the freeze marker, the logs and the rehearsal reports live under `~/.config/zuno/` and
  `~/.cache/zuno/demo/` on the presenter's workstation.
- `make demo golden-path` and `make demo browser` keep their role in the freeze protocol (ADR-0605): the per-demo
  `check` calls them for one demo only.
- Rehearsals that change shared state touch only the demo's named objects (for example consultant-01's three RAG
  files) and are refused during a freeze.
- The world model is not show-ready while no GPU capacity exists; its install refuses until `zuno_world_model_enabled`
  is true on `origin/devel`.

## Work packages

- [WP-269](../roadmap/work-packages/wp-269-record-the-demo-lifecycle-decision-and-page-contract.md) (this record, the
  page contract, the templates).
- [WP-270](../roadmap/work-packages/wp-270-build-the-make-demo-lifecycle-engine.md) (the orchestrator, the runner
  playbook, the Makefile grammar, the guards).
- [WP-271](../roadmap/work-packages/wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md) (the 36 demo
  directories and the CI consistency test).
- [WP-272](../roadmap/work-packages/wp-272-retire-the-webinar-demo-tools.md) (clause 13 and the operations pages).
- [WP-273](../roadmap/work-packages/wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md) and
  [WP-274](../roadmap/work-packages/wp-274-pilot-the-unifai-live-rag-demo-on-the-lifecycle.md) (the pilots, and the
  owner's gate).
- [WP-275](../roadmap/work-packages/wp-275-move-the-experience-demos-to-the-lifecycle.md) to
  [WP-279](../roadmap/work-packages/wp-279-move-the-blender-and-world-model-demos-to-the-lifecycle.md) (the rollout by
  layer).
- [WP-280](../roadmap/work-packages/wp-280-compose-the-workshops-from-scenario-steps.md) (the workshops).
- [WP-281](../roadmap/work-packages/wp-281-rehearse-every-demo-and-workshop-end-to-end.md) (the full rehearsal).

## Update 2026-11-15 (WP-273 to WP-280): what the pilots, the rollout and an incident added

- **Clause 7, by the owner's decision of 2026-11-15:** `make demo rehearse` also lists the golden-path probes and
  browser checks its sequence will run and asks for the demo id (or `DEMO_CONFIRM=<id>`) when there is at least one.
  They change nothing on the cluster, but they call the models and spend persona budgets; a rehearsal started by
  mistake on 2026-11-15 showed the gap. One prompt covers the changing units and the probes.
- **Clause 6, by the owner's decision of 2026-11-15:** the world-model `install` and `uninstall` never create or remove
  the GPU node. They check the switch on `origin/devel`, read what exists and print the owner's actions. The Blender
  add-on is installed and removed by its files, on the workstation, and a rehearsal never runs them
  (`not_rehearsed` in the manifest).
- **Clause 9:** a demo's `status` passes an Argo CD Application only when the application controller is running and
  the Application was reconciled in the last 30 minutes. On 2026-11-15 at 01:38 the teardown of the world-model GPU
  MachineSets (another work stream) deleted the Argo CD instance; five rehearsals then passed on the Applications'
  stored `Synced/Healthy`. Those runs are not counted as evidence.
- **Clause 5:** a step may also read a repository file (`grep`, `tail`, `head`, `cat`, `wc` as the first command, on
  a relative path inside the repository, never a secret or key file), and a `$NAME` in a command is resolved from the
  variables the manifest or the step declares.
- **Clause 14:** `platform/demo/consistency.py` also warns when a page's `### Status` or `### Check` names an object
  its file does not read; the rollout brought the count from 62 to 0.

## Implementation (2026-11-15)

Implemented by WP-269 to WP-281 (Phase 56). Every catalogue demo, 30 scenarios in both versions and 6 workshops, has a
`make demo rehearse` report ending with `RESULT: PASS`, and `make demo golden-path` and `make demo browser` pass
([evidence](../roadmap/evidence/wp-281-full-rehearsal-2026-11-15.md)). What the evidence does not show: the reports are
the sum of one day's layer runs at four commits, not one pass at one commit; nobody reviewed the presenter's screen
output of the runs; a rehearsal `PASS` is not "show-ready" (the world model is switched off, and
`model-catalog-registry` has no `ModelRegistry` instance). The live rehearsals found three defects of the files, each
fixed with a test:

- **Clause 9:** the queued golden-path probes ran in queue order, so `trace` ran before `unifai-tekos`, whose run it
  reads. The queue now runs in the probe script's own order, and a failed check names its probe and the reason. That
  last path has not been seen live, since no check failed after the fix.
- **Clause 10:** inside a workshop `demo_dir` is the workshop's directory. A scenario file reaches a file of its own
  directory through `demo_unit.dir`; the catalogue test refuses a bare `demo_dir` in a demo file.

## Update 2026-11-15 (ADR-0617): the order of the sections of a page

[ADR-0617](0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md) amends clause 4 for the position of the
sections only. `## Presenter lifecycle`, its six `###` and their content are unchanged. A catalogue page now follows
`## Introduction`, `## Personas`, `## Presenter lifecycle`, the version sections, `## If something goes wrong`,
`## Limits`, the appendices, `## References` and `## Page status` (the status banner, last); the contract is the one
in `docs/demo/README.md`. This is a dated correction note, not a supersession: every clause of this record stays in
force and the status stays `Implemented`.
