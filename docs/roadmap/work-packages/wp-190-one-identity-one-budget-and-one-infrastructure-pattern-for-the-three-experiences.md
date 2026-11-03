# WP-190: One identity, one budget and one infrastructure pattern for the three experiences

- **State:** Repo work merged (phases 0 to 3 done 2026-11-03, phase 4 open)
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
2. **Phase 1, identity and quota per persona (done 2026-11-03, [evidence](../evidence/wp-190-persona-quota-proof.md); the OpenClaw own-token spike is a no-go, [note](../evidence/wp-190-openclaw-user-token-spike.md)).**
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
3. **Phase 2, observability and logs (done 2026-11-03).** The `client` label of the ai-gateway is the common vantage
   point for the three, so the work is on the Three experiences dashboards (Grafana and Perses): a row *Same health, three
   experiences* with the model-call error rate and the p95 latency by client, from `zuno_model_calls_total` (outcome
   `error`) and `zuno_model_call_duration_ms_milliseconds_bucket`. Decisions: no OpenTelemetry export and no ServiceMonitor
   for Open WebUI and OpenClaw (they expose no metrics of their own, and OTel would open their closed egress to
   `zuno-monitoring`; UnifAI keeps its operator ServiceMonitor and its OTel wiring, ADR-0566); log collection is not
   codified in this repository (no ClusterLogForwarder or LokiStack), a platform gap outside this WP; a quota refusal is not
   a model call, so no dashboard counts the 429s (an ai-gateway metric for them would be a separate change).
4. **Phase 3, mesh, network, automation, RHOAI (done 2026-11-03, decisions recorded).**
   - *Gateway admission:* UnifAI stays a platform client. The ai-gateway and mcp-gateway admit it by namespace name AND the pod
     label `app.kubernetes.io/name: multiagent` (an intersection), while Open WebUI and OpenClaw come in by the namespace label
     `zuno.io/experience-client`. The label on `zuno-unifai` would admit every pod of the namespace (Mongo, Qdrant, RAG,
     backend) and would still not cover the a2a-gateway or the embedding model, which keep the name peer.
   - *Egress:* no EgressFirewall for `zuno-unifai`. Its legitimate internet egress is broad and operator-driven (Confluence,
     the Red Hat docs sync, S3 backups, the Kubernetes API for the rag TokenReview); the Open WebUI pattern (Allow the Keycloak
     name, Deny the rest) would break them. If one is wanted later: Allow Keycloak, the Atlassian and docs hosts, the S3
     endpoint and the control plane on 6443, Deny `0.0.0.0/0`. Its operator-made NetworkPolicies are not in this repository:
     check them live with `oc get netpol,egressfirewall -n zuno-unifai`.
   - *Mesh:* the three stay outside the mesh (no sidecar, no PeerAuthentication).
   - *Automation:* the Day 2 nodes already have the same shape (install `unifai -> [open-webui, openclaw]`, check
     `unifai -> [open-webui, openclaw, supply-chain]`, uninstall in reverse). Open WebUI has no `-d0` Application because it has
     no operator; neither the Makefile nor `check_docs.py` requires one. Its check runs from `precheck.yml`.
   - *Backup:* only PostgreSQL and UnifAI have Day 3 backup and restore. The Open WebUI volume (5Gi, chats in SQLite) and the
     OpenClaw volume (operator-made, not described in the repository) hold demo data and are not backed up; a CronJob would
     need S3 egress, which their EgressFirewalls forbid.
   - *Images:* no ClusterImagePolicy for Open WebUI and OpenClaw: they are third-party images Zuno does not sign (ADR-0586
     decision 7), so the keyless policy cannot cover them, and their namespaces must not carry `policy.rhtas.com/include`
     (harmless in `warn`, a refusal in `enforce`). The integrity check is the digest pin, now compared with the running image by
     `make d2 check` for both (`ansible/roles/open_webui/tasks/precheck.yml`, `check_persona.yml`).
   - *RHOAI:* the ai-gateway is the only model path for the three; no change.
5. **Phase 4, common chart and role base ([inventory](../evidence/wp-190-keycloak-plumbing-inventory.md)).**
   - *4a (done 2026-11-03):* the experience clients are declared once in `gitops/charts/keycloak/values.yaml`
     (`experienceClients`: `unifai`, `open-webui`, `openclaw-consultant-02`, `openclaw-sale-01`). The Keycloak chart renders their
     ExternalSecrets (`templates/externalsecret-experience-clients.yaml`) and the KC_VAULT items of `keycloak.yaml` from it, and the
     vault role seeds `keycloak/<name>` from the same file. Checked by rendering the chart before and after in a copy without
     the remote `operator` dependency: the 21 rendered objects are identical. The realm client blocks stay in `realm-zuno.json`.
   - *4b:* one precheck skeleton (state, pod, in-pod probes, Route, running-image digest) shared by Open WebUI and OpenClaw.
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
