# WP-097: Route `make day1/day2/day3` through AAP via `zuno_make_aap_mode`

- **State:** Repo work merged - live verification pending.
- **ADRs:** ADR-0418 (amended, clause 6 - routing half).
- **Depends on:** WP-094 (Job Templates), WP-095 (Workflow Templates).
- **Unblocks:** none - this closes ADR-0418 clause 6's decided scope; only
  Phase 3/4 launch-RBAC remains open for future work.
- **Estimated files touched:** 4 (`Makefile`, 2 new playbooks,
  `ansible/confidential.example.yml`; `docs/adr/0418-*.md`).

> Execute this brief as a standalone task from the repository root.
> Numbered WP-097, not WP-096: WP-096 was claimed by a concurrent session
> (`qwen35-9b-fleet-default-and-ovh-reasoning-rollout`) while this WP's
> own code/comments were already being written under the WP-096 label -
> renumbered throughout before this brief was authored, per this repo's
> "re-check right before committing" WP-numbering convention.

## Goal

Make `make day1|d1 <verb>` and `make day2|d2 <verb>` launch the matching
AAP Workflow Template (falling back to the underlying Job Template when a
specific, non-`all` component is named - a workflow's DAG always runs its
full node set), and `make day3|d3 <verb>` launch its Job Template
directly, whenever a new `zuno_make_aap_mode` setting allows it - without
ever making AAP a hard dependency for operators who need these verbs to
keep working with no AAP instance at all.

## ADR references

ADR-0418 clause 6 (routing half) - see the 2026-08-30 amendment in
`docs/adr/0418-*.md`.

## Preconditions (verify before starting)

- WP-094/WP-095 merged (Job Templates and Workflow Templates registered
  and named as this WP's routing logic expects - Workflow Templates carry
  the `-workflow` suffix fixed during WP-095/096's own work).
- Confirm no other in-flight session is editing `Makefile` (`git status`
  immediately before any edit and again immediately before committing -
  this repo's shared-workdir convention).

## Repo changes (step by step)

1. `ansible/confidential.example.yml`: add `zuno_make_aap_mode: auto`
   (`local`/`remote`/`auto`) with a comment block documenting each mode's
   semantics, right after the existing AAP Red Hat subscription block.
   Fixed two stale `make d1 install aap` references in that same block
   while touching it (ADR-0421 moved `aap` to Day 0).
2. New `ansible/playbooks/aap_probe.yml`: a non-blocking reachability
   probe - succeeds (exit 0) iff AAP's Gateway API answers, fails
   otherwise (Route missing, timeout, non-200). The Makefile checks this
   playbook's own exit code, never parses its stdout.
3. New `ansible/playbooks/aap_launch.yml`: launches a Job or Workflow
   Template (`aap_launch_type`/`aap_launch_template` extra-vars) with an
   arbitrary `aap_launch_extra_vars` JSON blob, polls
   `/api/controller/v2/{jobs,workflow_jobs}/{id}/` until terminal, prints
   a Job Template's stdout (a Workflow run's own stdout is empty - its
   nodes' individual output lives in the Controller UI/API), and fails
   the playbook (propagating to `make`'s own exit code) if the run didn't
   end `successful`.
4. `Makefile`: new `AAP_ROUTING_SHELL_FUNCS` (a `define...endef` shell-
   function pair, `resolve_aap_mode()`/`aap_route()`) shared across
   `DAY1_RECIPE`/`DAY2_RECIPE`/`DAY3_RECIPE` - each recipe body runs as
   its own separate shell invocation, so this is the only way to avoid
   tripling the routing logic. `resolve_aap_mode()` reads `ansible/
   confidential.yml` directly via a one-line `python3 -c` (the Makefile
   has no other way to reach an Ansible-sourced variable before deciding
   whether to invoke `ansible-playbook` at all), defaulting to `auto` if
   the file, PyYAML, or the key itself is missing. `aap_route()` returns
   `0` (launched and succeeded), `99` (a NOT-ROUTED sentinel - `local`
   mode, or `auto` with AAP unreachable - caller falls back to local),
   or any other nonzero code (a REAL launch/job failure the caller must
   propagate, never silently falling back to local for it).
   `DAY1_RECIPE`/`DAY2_RECIPE` gain a shared `route_or_local()` helper
   (component `all` → the verb's Workflow Template; a specific component
   → the verb's Job Template directly) wrapping `run_check`/`run_build`/
   `run_install`/`run_reconcile` (never `run_uninstall`).
   `DAY3_RECIPE`'s six verb branches each call `aap_route job
   zuno-day3-<verb> "<extra_vars json>"` inline (no shared helper - each
   verb's extra-vars shape differs: `test`/`check` add `report_format`,
   `stresstest` also adds `bulk_interactions`/`cleanup_test_data`,
   `backup`/`restore`/`sign` need only `target_component`), falling back
   to the identical local `ansible-playbook` call already there on a `99`
   sentinel.
5. `docs/adr/0418-*.md`: clause 6's routing paragraph updated from "not
   decided by this clause" to "decided and implemented - repo work
   merged, live verification pending"; Implementation state section
   updated to mention WP-097 alongside WP-094/WP-095.

## A real bug found and fixed while building this (worth flagging for future debugging)

Two bugs surfaced only once the generated recipe text was actually run
through `bash -n`/isolated execution - neither was visible from reading
the Makefile source alone:

1. **Parameter-name drift**: `aap_route()`'s launch call still passed
   `-e "aap_launch_component=$component"` after `aap_launch.yml` itself
   had already been redesigned to expect a generic `aap_launch_extra_vars`
   JSON blob (needed for Day 3's extra report_format/bulk/cleanup vars).
   Caught by `make -n d1 install kiali | grep aap_launch` showing the
   stale variable name.
2. **Missing statement separator across a `$(VAR)` splice**: Make's
   `define...endef` line-joining does NOT insert a separator between a
   variable's last line and whatever follows it at the call site - and,
   less obviously, a trailing `\` on the line immediately before a
   `define` block's own `endef` gets joined into it, so `endef` is no
   longer recognized as a bare line and Make reports "missing endef"
   pointing at the block's *start* line instead of anywhere near the real
   cause. Fix: the last line of `AAP_ROUTING_SHELL_FUNCS`'s body ends
   `};` with **no** trailing backslash (`endef` must remain a truly bare
   line); every other embedded function's closing line ends `}; \` (WITH
   the backslash, since those aren't the line immediately before an
   `endef`). Caught in two stages: `bash -n` first reported "unexpected
   token `route_or_local`" (the missing-`;` symptom, before the `endef`
   fix existed), then, after adding the `;`, `make -n` itself started
   failing with "missing endef" once a trailing `\` was left before it -
   both required actually invoking `make -n`/`bash -n`, not just
   re-reading the source.

## What NOT to touch

- `run_uninstall`/the `uninstall`/`reinstall` verb branches in any of the
  three recipes - never routed through AAP (ADR-0418 clause 1's Phase 4
  gate stays unimplemented; this WP does not touch it).
- Day 0's own recipe (`DAY0_RECIPE`) - Day 0 installs `aap` itself
  (ADR-0421's chicken-and-egg), never routed through AAP by design.
- Live cluster state - this WP's own verification was entirely offline:
  `bash -n` on the generated recipe text for 14 verb×day×component
  combinations, plus isolated shell-function tests (extracted the actual
  generated `aap_route`/`route_or_local` bodies into a standalone script,
  mocked `resolve_aap_mode`/`aap_route` to exercise all four outcomes -
  local fallback for both `all` and a specific component, remote success,
  remote real-failure) confirming the fallback/propagation contract holds
  exactly as designed. `resolve_aap_mode()` was also exercised for real
  against the actual (gitignored) `ansible/confidential.yml` on this
  machine - a pure local file read, no cluster contact - confirming it
  resolves to `auto` when the key is absent, matching the documented
  default. No `make d1/d2/d3 <verb>` was run for real against the live
  cluster (default mode `auto` would probe AAP's Gateway API, which
  needs the operator's own explicit live-testing go-ahead per this
  session's stated boundary).

## Acceptance checks

- `bash -n` on `make -n`'s generated recipe text passes for every
  verb×day combination exercised (test matrix in the WP's own commit).
- Isolated shell-logic tests confirm: `zuno_make_aap_mode=local` always
  falls back, for both `component=all` and a specific component;
  `aap_route` returning `0` (simulated success) short-circuits with no
  local fallback and the workflow name used for `all`/job name for a
  specific component; `aap_route` returning a non-`99` failure code
  propagates that code without falling back to local.
- `python3 platform/docs/check_docs.py` passes.
- `make help`/`make d1`/`make d2`/`make d3` (no verb) still render their
  help text unchanged.

## Operator / human follow-up

- With AAP live-registered (WP-094/095's own operator follow-up run
  first), set `zuno_make_aap_mode: auto` (or leave unset - it's already
  the default) in a real `ansible/confidential.yml` and run
  `make d1 check kiali` - confirm it launches `zuno-day1-check` (the Job
  Template, not the workflow, since a specific component was named) via
  the Controller API and the make invocation's own exit code matches the
  job's real outcome.
- Run `make d1 check` (no component, defaults to `all`) - confirm it
  launches `zuno-day1-check-workflow` instead, and that the DAG's
  parallel waves actually start concurrently in the Controller UI.
- Set `zuno_make_aap_mode: remote` and stop/break AAP reachability (or
  point at a wrong Route) - confirm the make invocation fails outright
  with no silent local fallback, per clause 6's explicit "no silent
  fallback" contract for `remote` mode.
- Set `zuno_make_aap_mode: auto` with AAP unreachable - confirm a single
  warning line prints and the invocation completes exactly as `local`
  mode would (today's unchanged behavior).

## Status updates

- 2026-08-30: Repo changes merged, `check_docs.py`/offline `bash -n` and
  isolated shell-logic tests all green. State: `Repo work merged - live
  verification pending`.

## Rollback

`git revert` - no live cluster state depends on this WP; `local` mode
(settable in `ansible/confidential.yml`, or simply never routing anywhere
since the setting doesn't exist in the real file <yet> and default `auto`
harmlessly falls back whenever AAP isn't live-registered) reproduces
today's exact pre-WP-097 behavior with zero code changes needed to revert
to it operationally.

## Out of scope / deferred

- Phase 3/4 launch-RBAC (who may launch which template via Controller's
  own user/team permissions) - ADR-0418's Security considerations still
  flags this as open; this WP only builds the launch mechanism itself.
- A Survey-driven "run only this subtree" option on Workflow Templates -
  not decided by ADR-0418 clause 6; the existing per-component Job
  Template route already covers that need without touching the workflow.
- WP-098 (live resource tuning on `zuno-aap` from real Workflow/Job
  Template load) - deferred until an operator runs the live verification
  above and there is real load to measure.
