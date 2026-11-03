# WP-179: Common preparation for experience clients

- **State:** Done (2026-11-02)
- **ADRs:** [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
- **Depends on:** none
- **Related:** [WP-180](wp-180-open-webui-preparation.md), [WP-182](wp-182-openclaw-preparation.md), [WP-184](wp-184-three-experiences-demonstration.md)
- **Target:** v0.13
- **Estimated files touched:** ~12 in `zuno-demo` (`components/ai-gateway`, `gitops/charts/{ai-gateway,mcp-gateway,namespaces,grafana,perses}`, `Makefile`, `aap-config` DAGs, docs)

> Decision of 2026-11-02 (user): UnifAI, Open WebUI and OpenClaw are three experiences over one governed backend (ADR-0587).
> Open WebUI and OpenClaw are built **in parallel by two sessions**; this package is the shared groundwork both need, done
> **once, by one session, before either track touches shared files**.

## Goal

After this package, each track only adds files in its own directories: every file the two tracks would both edit is already
changed here, and the rules for the rest are written down.

## Steps

1. **Client identity in the ai-gateway.** `components/ai-gateway/app/auth.py` exposes the token's `azp` as `client`;
   `app/telemetry.py` adds `client` to `zuno_model_*` and `zuno_guardrails_*`, bounded by an allowlist from values
   (`experienceClients: [unifai, open-webui, openclaw-*]`, prefix match, else `other`). Tests in the ai-gateway suite
   (baseline 131/132, `test_optimizer` is a known failure). Experience clients are **not** added to
   `TRUSTED_PLATFORM_CLIENTS` (`gitops/charts/ai-gateway/templates/deployment.yaml`).
2. **Label-based ingress.** `gitops/charts/ai-gateway/templates/networkpolicy.yaml` and
   `gitops/charts/mcp-gateway/templates/networkpolicy.yaml` admit any namespace labelled
   `zuno.io/experience-client: "true"` on the API port. Keycloak's ingress is checked for the same peers.
3. **Namespaces.** `gitops/charts/namespaces/values.yaml` declares `zuno-openwebui` with the label, default-deny,
   outside the mesh (as `zuno-unifai`). OpenClaw's namespaces are created by its operator: WP-182 decides how they get the
   label; this step documents the rule that only the `namespaces` chart or the `openclaw` chart sets it.
4. **Make and AAP.** `Makefile` `DAY2_RUN_COMPONENTS` gains `open-webui` and `openclaw`, with empty roles
   `ansible/roles/open_webui` and `ansible/roles/openclaw` that fail with "not implemented (WP-181/WP-183)"; the
   `aap-config` workflow DAGs gain both (`check_docs.py` checks the two lists agree).
5. **Keycloak clients pattern.** The realm import is create-only, so new clients do not reach a live realm by
   import. Write once how a track adds a client to `gitops/charts/keycloak/files/realm-zuno.json` **and** reconciles it
   live (the role task used for UnifAI's client), so WP-181 and WP-183 each add their own client without editing the
   mechanism.
6. **Dashboards.** `gitops/charts/{grafana,perses}/templates/dashboard-usage-cost.yaml` gain "by client" panels (tokens,
   cost, calls, guardrail hits); WP-184 builds the dedicated dashboard on them.
7. **One build and roll of the ai-gateway and the mcp-gateway**, after the user's go in this session; push first, check
   the Build's commit, then verify a UnifAI chat gives `zuno_model_tokens{client="unifai"}` in raw Prometheus.

## Implementation notes (2026-11-02)

- **Step 1.** `CallerIdentity.client` (`app/auth.py`) is the `azp`. The handlers of `/v1/chat/completions` and
  `/v1/images/generations` call `set_caller_client()` (`app/telemetry.py`) after token validation: a ContextVar, like the trace
  context of ADR-0566, because `validate_token` is a sync dependency run on a copied context. `model_call_span` puts
  `zuno.client` on the span and `client` on `zuno_model_calls`, `zuno_model_call_duration_ms`, `zuno_model_tokens` and
  `zuno_model_cost_usd`; `record_guardrails_evaluation` puts it on both guardrails counters. The label is bounded by
  `EXPERIENCE_CLIENTS` (chart value `experienceClients`: `unifai`, `open-webui`, `openclaw-*`, `zuno-evaluations`,
  `zuno-stresstest`); any other client is `other`. Tests: `tests/test_experience_client.py` (8, including the propagation
  through a real FastAPI request); the suite is 300/300.
- **Step 2.** Both NetworkPolicies admit `namespaceSelector: zuno.io/experience-client: "true"` on port 8080. Keycloak is not
  touched: experience clients reach it through its Route, like UnifAI, never through the in-cluster `http` service (its
  issuer would be `http://`, see the UnifAI 401 of 2026-10).
- **Step 3.** `zuno-openwebui` in `gitops/charts/namespaces/values.yaml`: label, default-deny baseline, outside the mesh.
- **Step 4.** `open-webui` and `openclaw` in `DAY2_RUN_COMPONENTS`, the Day 2 install, check and uninstall playbooks and both
  AAP Day 2 DAGs (independent leaves after `unifai`). The stub roles are **no-ops that say so**, not failures, so a full
  `make d2 install` and `make d2 check` stay green until the tracks replace `tasks/`.
- **Step 5, Keycloak client pattern.** The mechanism exists (ADR-0530): the `zuno-keycloak-client-reconcile` Job creates or
  merges every client of `gitops/charts/keycloak/files/realm-zuno.json` on each sync, so a client added there reaches the
  live realm. A confidential client touches four places, each an append, in one commit of its own track, announced to the
  other session:
  1. the client in `realm-zuno.json` (shape of `unifai`: `secret: "${vault.<name>_client_secret}"`, redirect URIs on
     `apps.mycluster.example.com`, the `groups` mapper; a client-credentials client sets `serviceAccountsEnabled` and,
     for its groups, a `users` entry with `serviceAccountClientId` - users are create-only, so a persona's service-account
     groups are checked live after the first sync);
  2. an ExternalSecret in `gitops/charts/keycloak/templates/` (shape of `externalsecret-unifai-client.yaml`, Vault key
     `keycloak/<name>`);
  3. an item of the `vault-secrets` projected volume in `gitops/charts/keycloak/templates/keycloak.yaml` (path
     `zuno_<name>__client__secret`, `optional: true`);
  4. a `vault_seed_if_missing.yml` call in `ansible/roles/vault/tasks/install.yml` (shape of `keycloak/unifai`).
  The consumer side (the experience's own ExternalSecret on `keycloak/<name>`) stays in the track's chart.
- **Step 6.** A collapsed "By experience client" row in both `dashboard-usage-cost.yaml` (Grafana and Perses): calls, tokens,
  cost and guardrails evaluations by `client`. Like the user panels, a multi-group user counts once per group.
- **Push.** Some demo333 Applications follow `devel`: pushing these commits may apply the namespace, the NetworkPolicies and
  the ai-gateway environment on demo333 at the next sync. The push is therefore a cluster action and waits for the user's go.

## Live evidence (2026-11-02, demo333, user's go)

- **Push and sync.** 9dd8df9f pushed to `devel`; the seven Applications concerned follow `devel` with automated sync and applied
  it (`zuno-ai-gateway-d1`, `zuno-mcp-d1`, `zuno-namespaces-d1`, `zuno-llm-d1` Synced/Healthy). `zuno-openwebui` exists with
  `zuno.io/experience-client=true`; both NetworkPolicies carry the namespace-label peer.
- **Build and roll.** ai-gateway Build 30 (commit 590b920d, which contains 9dd8df9f), image `sha256:9021fe15...`, rolled 1/1;
  `EXPERIENCE_CLIENTS` set in the pod, the new code present. Rollback image: `sha256:9c044b06...` (Build 29). A build of one
  component needs `-e day1_verb=build`: without it `apply_openshift_build.yml` only ensures the image exists (green, no Build).
- **Network.** Unauthenticated HTTP from a pod in `zuno-openwebui`: ai-gateway `/v1/models` 401, mcp-gateway `/mcp` 405
  (reached). From an unlabelled pod in `zuno-mlops`: no answer from either (blocked). Probe pods deleted.
- **Label, from raw Prometheus (thanos-querier).** `zuno_model_calls_total{client="openclaw-spike",agent="openclaw"}` (WP-182's
  spike, through claw-operator's oauth2 proxy) and `{client="other"}` (WP-180's spike, Keycloak client `owui-scratch`, outside
  `EXPERIENCE_CLIENTS`, so bounded to `other` as designed), on error and success outcomes;
  `zuno_guardrails_evaluations_total{client="other"}` too. No `client="unifai"` series yet: no UnifAI call since the roll;
  same code path.
- **Platform findings, not part of this package.** With the GPU nodes NotReady, the fallback walks every local pair and each
  `*-maas` candidate costs about 60 s before the next one: a C1 chat reached `openai` after about 10 minutes, and
  claw-operator's proxy cuts at 300 s (WP-188). The NeMo guardrails backend answered `unavailable` (observe mode, response
  unaffected), under investigation.

## Coordination protocol (both tracks)

- **Ownership.** Track Open WebUI (WP-180, WP-181) owns `gitops/charts/open-webui/`, `gitops/apps/open-webui/`,
  `ansible/roles/open_webui/` and its evidence. Track OpenClaw (WP-182, WP-183) owns `gitops/charts/openclaw/`,
  `gitops/apps/openclaw/`, `ansible/roles/openclaw/`, `components/claw-token-proxy/` (if any) and its evidence.
- **Shared files** (ai-gateway, mcp-gateway, keycloak realm and role, namespaces, `Makefile`, `aap-config`, dashboards,
  ADR index and roadmap): a track that needs a change asks the other session first (`SendMessage`), one session makes it in
  a separate commit, the other rebases. Each track adds its own row and its own Keycloak client; it edits nothing else.
- **Git.** Each session works in its own detached worktree on `origin/devel`, rebases before pushing, and pushes its own
  SHAs explicitly. Never reset or stash the shared checkout.
- **Cluster.** Every cluster action needs the user's go **in the acting session**; a go relayed by the other session does not
  count. Announce to the other session what, when and how to roll back. A build or roll of a shared component (ai-gateway,
  mcp-gateway, Keycloak) happens once, agreed between the two.
- **Interfaces fixed here** and not renegotiated per track: the namespace label, the `client` values (`open-webui`,
  `openclaw-<persona>`), the logical agents `open-webui` and `openclaw` for the mcp-gateway, the in-cluster URLs
  `http://ai-gateway.zuno-ai-run.svc:8080/v1` and `http://mcp-gateway.zuno-ai-run.svc:8080/mcp`.

## Acceptance

`check_docs.py` green; ai-gateway suite with no new failure; on demo333, `zuno_model_tokens` has a `client` label with
`unifai` for a UnifAI chat, and a pod in a labelled test namespace reaches the ai-gateway while one in an unlabelled
namespace does not (HTTP request, not a TCP probe).
