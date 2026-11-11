# WP-221: incident revocation rehearsed on demo333 (2026-11-11)

The incident revocation path of [ADR-0584](../../adr/0584-define-agent-lifecycle-states-roles-and-incident-revocation.md)
clause 5, rehearsed once on demo333 with the user's go, following the
[runbook](../../platform/agent-revocation-runbook.md). UnifAI operator 0.1.68 (R-536 since 0.1.60). Session
zuno-avancement.

## Target

`comage`: Ready before the rehearsal, and used by neither the golden path nor the demonstration.

## Revocation

| Time (UTC) | Step |
|---|---|
| 14:33:02 | `agentRevocations: [{bundle: comage, reason: "WP-221 rehearsal ...", actor: "Christophe LARUE"}]` in `ansible/clusters/demo333.yml` (pushed a89a0855), `make d2 install unifai` started (exit 0 at about 14:34) |
| 14:35:10 | ArgoCD synced `zuno-unifai-d1`; ConfigMap `unifai-agent-revocations` carries the entry; event `Revoked` from `unifai-operator`: "revoked by the platform: WP-221 rehearsal of the incident revocation path (ADR-0584 clause 5) (actor Christophe LARUE)" |
| 14:35:10 | bundle `comage`: `Valid=False/Revoked`, `Emitted=False/Revoked`, `Ready=False/Pending`, each message naming the reason and the actor |
| 14:35:41 to 14:36:11 | operator log: "pruning object no longer in the bundle" for the emitted objects |

About two minutes from the start of the install to the revocation, and five to the end of the ArgoCD sync: within the
one-hour target, which the user confirmed as is.

## Finding: the revocation also deletes the agent's team, and that deletion wedges

The bundle-owned `UnifaiTeam agent-comage` got a `deletionTimestamp` at 14:35:10. Its finalizer then looped every 30 s
("delete failed, retrying ... still used by UnifaiRetriever/knowledge-comage"): the `knowledge-<agent>` retriever is
rendered by the zuno-demo `unifai` chart, not by the bundle, and still references the team. The UnifAI team
(`c19c706f8e7047dbba25f5deeb5e0a33`) and its sessions were not deleted.

The fork session's read of the operator code (unifai-main): revocation and retirement prune everything the bundle emits,
the team included; the delete is refused while an object references the team. So the sessions stay readable only as long
as `knowledge-<agent>` exists, and a later removal of that retriever would delete the team and its workspace, against
clause 4. The fork session proposes not pruning the agent team on revocation or retirement (decision with its user).

## Re-admission

| Time (UTC) | Step |
|---|---|
| 14:5x | entry removed (pushed 2610736e), `make d2 install unifai` (exit 0) |
| 15:01:13 | bundle `comage` Ready again, "3 tasks, 14 objects emitted"; the team CR still Terminating (the bundle's upsert leaves it as is) |
| 15:01:33 | finalizer removed from the Terminating `UnifaiTeam agent-comage` (user's go) |
| 15:01:39 | the bundle recreated the CR (new uid, `unifai.startx.fr/adopt: "true"`, owner `comage`), which adopted the existing UnifAI team by name: `Ready`, team `c19c706f8e7047dbba25f5deeb5e0a33`, no duplicate |
| 15:02 | `knowledge-comage` Ready, `arkos`, `comage`, `tekos` Ready, `zuno-unifai-d1` Synced/Healthy, no operator error after the patch |

## Not rehearsed (user decision)

The `deprecated` and `retired` states were not set on a live agent: they rest on the operator tests of R-536 and on the
[session pilot of 2026-11-05](wp-221-session-pilot-2026-11-05.md).
