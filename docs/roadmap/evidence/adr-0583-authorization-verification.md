# ADR-0583: authorization verification on the UnifAI pilot

Measured on `demo333` on 2026-10-24 against `zuno-unifai` (UnifAI images
`devel-1bb72a84d`, fork `devel`), with real browser-flow sign-ins through realm
`zuno`: `consultant-01` (member of `agent_tekos`, `agent_arkos`, `agent_comage`)
and `sale-01` (member of `agent_comage` only). Probes only read, or attempt an
action that must be refused; the one session created for the isolation check was
deleted.

## Clauses

| Clause | Result |
|---|---|
| 1. Group visibility | Verified. Group-bound teams come from the token's `groups` claim (`oidc-claims`). `consultant-01` sees the arkos, tekos and comage workflows, `sale-01` only comage; a non-member selecting another group's team gets `403 TEAM_ACCESS_DENIED`. |
| 2. Object-level audit | Audited across the multi-agent API, the identity service and the RAG service (see "Audit scope"). Findings with a direct cross-user effect are fixed (below). Remaining lower-severity items are tracked in the fork roadmap and kept out of public records until fixed, as the ADR requires. |
| 3. Uniform denial | Verified for blueprints, sessions, teams, resources and schedules: a denied object answers exactly like a missing one (status and body). |
| 4. Session isolation | Verified. Another user's session cannot be read, executed or deleted, and does not appear in that user's session list. |
| 5. Automated tests | Fork: endpoint tests for every fixed route (the new tests fail on the previous code and pass now). Pilot: the two-user probe below. Wiring the probe into `evaluations/common/unifai_checks.py` is still to do. |

## Fixed by the audit (fork `devel`, 2026-10-24)

- Graph validation and config validation required no session and resolved
  referenced resources without the caller's scope. They now need a session and
  use the caller's scope.
- Resource and blueprint validation took the credential-lookup identity from the
  request body. They now use the verified session identity.
- Team rename, member change and delete are limited to the creator, an admin or
  the trusted service; member lists proposed by a session user are vetted
  server-side (no client-supplied group snapshot, only groups the caller is in).
- Resource write and schedule denials, and team delete for a non-member, answer
  like a missing object.
- Template routes require a session and hide non-public templates from
  non-admins.
- The CLI login callback accepts a loopback address only.
- RAG uploads are stored per uploader.
- Deployment Confluence credentials can be limited to listed hosts
  (`CONFLUENCE_ALLOWED_HOSTS`); the setting is opt-in until the operator can
  render it.

## Pilot probe (18 checks, all passed)

Anonymous calls to the validation and template routes are refused (401).
`sale-01` cannot read the tekos blueprint through its team (403), reads another
user's session as an unknown session, and gets the same answer for an existing
team it is not in as for a missing one. `consultant-01`, a group member but not
the creator, cannot update or delete the tekos team (403) and cannot create a
team around a group it does not belong to (400). A denied resource update answers
like an unknown id. `consultant-01` still sees its three workflows.

Not covered here: a full chat turn after the roll-out (quota of the shared
personas), and the items still open in the fork roadmap.

## Status of ADR-0583

Clauses 1, 3 and 4 are verified and clause 5 is half done, so the ADR stays
`Accepted`. It moves to `Implemented` when the remaining audit items are closed
and the probe runs as a standing check.
