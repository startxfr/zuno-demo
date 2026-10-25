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
| 5. Automated tests | Fork: endpoint tests for every fixed route (the new tests fail on the previous code and pass now). Pilot: the two-user probe below. The probe is wired as standing checks (`cross_user_isolation`, `a2a_gateway_denies_unentitled` in `evaluations/common/unifai_checks.py`, run by the Tekos security checks); they run against the cluster after the next roll-out. |

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

## Second pass (fork `devel` ffb64e335, not yet rolled out)

- Share accept, decline, cancel and read answer a third party like a missing id.
- The duplicate-file check compares within the caller's own files only.
- The forwarded RAG bearer path requires the configured audience.
- A team's name is returned to members, admins and the trusted service only.
- Builtin-resource lookups for a non-builtin id answer like a missing one.
- A shared outbound-URL guard (`global_utils/utils/net_guard.py`) refuses
  non-public targets (loopback, link-local and cloud metadata, private ranges,
  internal service names outside `zuno-ai-run`) for MCP transports, the A2A
  client, OAuth discovery, the forwarded-token probe and the Confluence fetch.

## Roll-out check on demo333 (fork `devel-ffb64e335`, images pinned by digest, 2026-10-25)

- The 18-check pilot probe passes again (18/18) on the rolled stack.
- The standing check `cross_user_isolation` (`consultant-01` vs `sale-01`) passes.
- A2A gateway: anonymous POST to a served agent is refused (401). Real delegated
  turns: `sale-01` through `test-sale-01-a2a` gets an answer from the comage
  agent (1.9 s) with its own token. `adv-01`'s A2A blueprint reports a clean
  404 on the card because `advantage` is still a placeholder (not served).
- The authenticated denial case of `a2a_gateway_denies_unentitled` runs from a
  pod with a persona token (cluster-internal service); it is not yet exercised
  against the live gateway, only by the gateway's unit tests.
- The earlier slow `finance-01` chat did not reproduce (39.8 s, on-topic reply).

## Roll-out with the Confluence binding (fork `devel-8498fe02b`, operator 0.1.38, 2026-10-25)

- `stack.rag.confluenceUrl` is set in the unifai chart; the RAG server and worker
  carry `CONFLUENCE_ALLOWED_HOSTS=["startxfr.atlassian.net"]`; a source on another
  host is fetched anonymously, and a source on an internal host is refused when it
  is registered (operator e2e).
- The 18-check probe passes again (18/18), `cross_user_isolation` passes, and a
  real delegated A2A turn as `sale-01` answers in 2.5 s.
- Unrelated known issue: seven bundles show `signature manifest has 35 layers,
  at most 32 are read` (tracked by the operator owner); their workflows stay Ready.

## Outbound guard, second hardening (fork `devel-9c13a282b`, 2026-10-25)

Every request and redirect hop of a user-supplied URL is vetted again and the connection goes to the vetted
address (`net_guard_httpx`, `net_guard_requests`): MCP transports and validator, the A2A client, discovery GETs, and
the Confluence session. Rolled on demo333 with the a2a-gateway rebuild (uniform 404 for every `/agents/` name no
agent can have). Checks after the roll: 18/18 probe, `cross_user_isolation`, real delegated A2A turns as `sale-01`,
`paas-dev-01` and `recrut-01`. Not covered by any e2e: MCP and A2A against a real external server (no fixture), so the
address pinning there rests on unit tests.

## Open decisions and recommendations

**Confluence allowed hosts (open, recommended to close).** The setting exists
but is `None` (open) because the operator does not render it. Recommendation:
the operator derives `confluence_allowed_hosts` from the host of
`spec.rag.confluence`, the stack-wide Confluence every Confluence source uses,
rather than a hand-maintained value. It is a small operator change (owner of the
operator session) and should land before the ADR moves to `Implemented`. The
guard is also not applied when a Confluence source is registered, only when it
is fetched; adding it there is quick and recommended.

**Residual risks accepted by the user (2026-10-25).**

| Item | Why it is low | Condition |
|---|---|---|
| Slack lookups open to any signed-in user | Slack is not configured on this stack | Revisit before enabling Slack |
| Global RAG counts | Counts only, no content or identifiers | None |
| Team name already taken at creation | Reveals a name exists, not its members or content | None |
| ~~DNS rebinding on the outbound guard~~ | Closed 2026-10-25: the HTTP clients connect to the address just vetted (fork `faed4e198`); Confluence (`requests`) re-vets each request but does not pin | None |
| ~~Redirects followed by the MCP SDK~~ | Closed 2026-10-25: the installed SDK follows same-origin redirects only; every hop is re-vetted by the guarded transport | None |
| RAG web fetch resolve-then-connect gap | Same class as DNS rebinding; the web source path was exercised by the operator e2e, not pinned by the transport | Revisit if the web fetcher moves to the guarded transport |

## Status of ADR-0583

`Implemented` (2026-10-25). The closing steps were done: the Confluence host
binding is rolled out, the Tekos stresstest on `devel` cd197d24 passed both
standing checks (`a2a_gateway_denies_unentitled_callers_like_unknown_agents`:
anonymous 401, denied and unknown 404 with identical bodies;
`unifai_denies_another_users_objects_like_missing_ones`), with security checks
14/14 overall, and the residual risks above are accepted.

Still open, not blocking: the A2A gateway image does not yet carry the uniform
404 for names no agent can have (the check passes with a valid unknown name);
it ships with the next gateway rebuild.
