# WP-190: One identity, one budget and one infrastructure pattern for the three experiences

- **State:** Not started (ADR and brief 2026-11-03)
- **ADRs:** [ADR-0593](../../adr/0593-key-the-per-user-quota-and-telemetry-by-persona-across-experiences.md)
- **Depends on:** [WP-184](wp-184-three-experiences-demonstration.md), [WP-183](wp-183-install-openclaw-on-demo333.md), [WP-181](wp-181-install-open-webui-on-demo333.md)
- **Related:** [WP-179](wp-179-common-preparation-for-experience-clients.md), [WP-177](wp-177-finish-the-maas-quota-delegation.md)
- **Target:** v0.13
- **Estimated files touched:** ~25 (ai-gateway auth, quota, quota windows, MaaS adapter, telemetry and tests; Keycloak realm;
  Grafana and Perses dashboards; the three experiences' charts and roles; docs)

> Why: the WP-184 rehearsal showed that the per-user budget is one counter for Open WebUI and UnifAI but a separate one for
> OpenClaw, which calls as a service account. The user asked to unify the three experiences as far as possible on the
> infrastructure (RHOAI, logs, mesh, API gateway, SSO, Vault, AAP). Decisions of 2026-11-03 (user): one WP with phases;
> a signed `persona` claim on the OpenClaw service-account tokens (the person's own token for OpenClaw is only a spike,
> ADR-0589 rejected it); the `user` label becomes the persona; the check-before-consume race is out of scope.

## Steps

1. **Phase 0, documents.** ADR-0593, this brief, index, roadmap, versions; `check_docs.py` green.
2. **Phase 1, identity and quota per persona (first).**
   - *Keycloak (this track):* a hardcoded-claim mapper `persona=<id>` in the `protocolMappers` of `openclaw-consultant-02`
     and `openclaw-sale-01` in `gitops/charts/keycloak/files/realm-zuno.json`; the client-reconcile Job applies it on the
     next sync (it re-applies each client with `kcadm update -m`). Check live that the token carries the claim.
   - *ai-gateway (owned by the zuno-demo-40 session, one explicit-SHA push, one build, announced to the peers; the
     Arkos to Tekos tests of `da` also use the gateway, so warn before the roll):* `app/auth.py` derives the persona
     (claim for an `openclaw-*` `azp`, else `preferred_username` of a person's token, else `sub`; never a header);
     `app/quota.py` and `app/quota_windows.py` key the `user` dimension by persona (memory and Redis); `app/maas_adapter.py`
     attests the persona in `X-Zuno-User-Sub`; `app/telemetry.py` sets `user` to the persona and keeps the `sub` in
     `zuno.user_sub`. Tests: two subs of one persona share one budget; a `persona` claim from another client is ignored;
     the `service-account-` username is never a persona. `platform/testing/token_quota_429.py` gets a persona-then-service-
     account scenario. The `user` label is not bounded today (it is the `sub`); the persona set is smaller, so
     cardinality does not grow.
   - *Live proof (user go in the session that runs it):* the rehearsal group with sale-01 only; sale-01 spends the budget in
     Open WebUI, then 429 in UnifAI and in OpenClaw; raw Prometheus shows one `user="sale-01"` series across the three
     `client` values.
   - *Spike:* OpenClaw with the person's own token for the interactive session (oauth2-proxy forward and refresh): note and
     go/no-go, no commitment.
3. **Phase 2, observability and logs.** Same pattern for the three: a per-experience ServiceMonitor or a recorded decision
   for Open WebUI and OpenClaw (none today), log forwarding labels, a health row in the Three experiences dashboards
   (Grafana and Perses), modelled on UnifAI's OTel wiring (ADR-0566).
4. **Phase 3, mesh, network, automation, RHOAI.** Decide and record: UnifAI under the label-based ingress grant or kept a
   platform client; an EgressFirewall for `zuno-unifai` or the reason not to; the mesh stays outside for all three unless
   an audit says otherwise; the same Day 2 node shape in the AAP workflows and the `-d0`/`-d1` split for Open WebUI; backup
   or retention for the Open WebUI volume and the OpenClaw volume; the ai-gateway as the only model path.
5. **Phase 4, common chart and role base.** One shared helper for the near-identical Keycloak client plumbing
   (`externalsecret-*-client.yaml`, KC_VAULT entry, Vault seed), the precheck conventions of
   `ansible/roles/open_webui/tasks/precheck.yml` (probe the chain from the pod) and the `make d2 check` shape.
6. **Close.** Evidence `docs/roadmap/evidence/wp-190-*.md`; the WP-184 note on the OpenClaw counter reverts to "one budget
   for the three"; ADR-0593 to `Implemented`.

## Acceptance

On demo333, one persona has one per-user budget across Open WebUI, UnifAI and OpenClaw: with the rehearsal class, the
budget spent in any one of them ends in a 429 in the other two, and raw Prometheus shows one `user` series per persona
across the `client` values. Each later phase closes with its own recorded decisions and a green `make d2 check` for the
experience it touches.

## Coordination

Keycloak and docs: this track. `app/*` of the ai-gateway: the zuno-demo-40 session. `ansible/roles/openclaw` and
`gitops/charts/openclaw`: the OpenClaw track, asked before any edit. UnifAI operator and bundle sessions: told before
phase 3 touches `zuno-unifai`. Every cluster action needs the user's go in the session that runs it.
