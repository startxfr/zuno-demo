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
| DNS rebinding on the outbound guard | Needs an attacker-controlled DNS name answering differently at connect time | Pin the resolved address if the guard moves to a shared HTTP client |
| Redirects followed by the MCP SDK | Not verified to reach internal addresses | Verify, then fix or accept |
| RAG web fetch resolve-then-connect gap | Same class as DNS rebinding | Same as above |

## Status of ADR-0583

Clauses 1 to 4 are verified on the rolled stack and clause 5 is in place: the
standing checks exist and pass against demo333, apart from the authenticated
A2A denial, which needs a run from inside the cluster. The residual risks above
are accepted. The ADR stays `Accepted` until the closing steps below are done.

Closing steps, in order:

1. (Done 2026-10-25.) The operator derives `confluence_allowed_hosts` from `spec.rag.confluence`
   and the outbound guard runs when a Confluence source is registered (a9,
   waiting for the user's confirmation in that session). Roll it out and
   re-run the 18-check probe.
2. Run the Tekos security checks from inside the cluster (an evaluation
   campaign); `a2a_gateway_denies_unentitled_callers_like_unknown_agents` and
   `unifai_denies_another_users_objects_like_missing_ones` must both pass.
3. Flip the status: `Accepted` to `Implemented` in the ADR header and in
   `docs/adr/README.md`, replace the ADR's verification note with a pointer to
   this file, update the WP-167 and WP-154 status lines in
   `docs/roadmap/implementation-roadmap.md` and their work-package files, and run
   `platform/docs/check_docs.py`.
