# Freeze protocol for a live demonstration

[ADR-0605](../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md) clause 3. A freeze protects
a live demonstration from the people and sessions who would otherwise keep improving the platform under it. It opens
with the golden-path baseline run and closes when the demonstration ends.

## Before the freeze

1. **Set the window.** The start is the baseline golden-path run, normally the evening before; the end is the end of the
   demonstration. Write both in the demo-day runbook (`docs/demo/demo-day-<date>.md`).
2. **Land what must land.** Every change meant for the demonstration is pushed, built and rolled before the baseline
   run. A pre-GA upgrade must leave time for one full golden-path run and one restore before the freeze starts.
3. **Find every working session that can act on the cluster.** List the sessions, people and coding agents alike. Send
   each one a message that names:
   - the window (start and end, with the time zone);
   - the frozen namespaces: `zuno-ai-run`, `zuno-unifai`, `zuno-data`, `zuno-auth`, `zuno-aap`, `zuno-vault`,
     `zuno-monitoring`, and the namespaces of the experience clients;
   - the frozen Applications: the gateways, UnifAI, the models, and every experience client;
   - the frozen commands: every `make d0|d1|d2 install|reconcile|build`, `make d3 release|restore|stresstest|run`, any
     operator, catalog or image pin, and any node or MachineSet change;
   - what stays allowed: editing files and committing locally.
   Each session answers before the freeze starts. A session that does not answer is listed in the runbook as unconfirmed.

## During the freeze

- **Do not push** to `devel` or `main`. On demo333 the Applications track `devel` with automated sync, so a push is a
  deployment.
- **Do not run any frozen command.** That includes running one "just to check".
- **Read-only work is allowed:** `make demo check`, `oc get`, logs, dashboards, Tempo searches.
- **Break glass only with the owner's go.** Name the one change, make it, then run the full golden path. Write the change
  and its result in the runbook.
- **A red probe on the morning switches that moment to its fallback.** Do not try to fix it.

## The proof of a path is a run, not a status

Status can stay green while the path behind it is dead. On 2026-11-02 the AAP resources and every pod were green while
the dispatcher had run nothing for a week. On 2026-09-14, after a cluster restart, the `AnsibleAutomationPlatform`
resource said `Successful` and nothing had executed for two days. A moment is proved only by the probe that makes it
answer (ADR-0605 clause 1). For AAP that means launching a read-only `*-check` job template and seeing its
`automation-job-*` pod start in `zuno-aap`.

Never run an `install`, `reconcile`, `release`, `restore` or `stresstest` template in front of an audience.

## After the demonstration

1. Tell every session that the freeze is over.
2. Push the commits held during the freeze: the baseline snapshot, the runbook results, and the local work of other
   sessions, in the order they agree on.
3. Run the delayed cluster steps in their own windows, for example the release ledger (`make d3 release`), which builds on
   the same nodes as UnifAI.
4. Write in the runbook what failed, what the fallback looked like, and what changes for the next demonstration.
