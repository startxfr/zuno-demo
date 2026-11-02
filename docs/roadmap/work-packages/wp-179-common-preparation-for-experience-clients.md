# WP-179: Common preparation for experience clients

- **State:** Not started
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
