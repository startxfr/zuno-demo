# WP-151: Deploy UnifAI on zuno through ArgoCD

- **State:** Done
- **ADRs:** [ADR-0574](../../adr/0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md), [ADR-0562](../../adr/0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0560](../../adr/0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md)
- **Depends on:** [WP-146](wp-146-unifai-identity-and-context-header-forwarding.md), [WP-150](wp-150-unifai-operator-okf-agent-bundles.md)
- **Related:** [ADR-0557](../../adr/0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md), [ADR-0558](../../adr/0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md), [ADR-0559](../../adr/0559-follow-the-cluster-version-and-never-branch-by-ocp-version.md), [WP-147](wp-147-unifai-opentelemetry-instrumentation.md), [WP-149](wp-149-unifai-rag-qdrant-hybrid-sources-backup.md), [WP-154](wp-154-tekos-pilot-on-demo333.md)
- **Target:** v0.11
- **Estimated files touched:** ~20 in `zuno-demo` — a new `gitops/charts/unifai/` chart, `gitops/apps/unifai/application-d{0,1}.yaml`, an Ansible role, the Keycloak realm/client files, ExternalSecrets, NetworkPolicy allowlists in `ai-gateway` and `mcp-gateway`, the namespaces chart. None in `startx-unifai`.

> The zuno-side integration. It deploys the operator and one UnifaiStack the
> same way every other operator-backed component is deployed here, wired to
> the zuno realm, the ai-gateway and the mcp-gateway.

## Goal

`make d1 install unifai` (or the tier ADR-0574 assigns) brings up the
unifai-operator from a pinned catalog tag and a `UnifaiStack` in a zuno
namespace that authenticates against realm `zuno`, calls models only through
the ai-gateway, reaches tools only through the mcp-gateway, exports OTel,
and is Synced and Healthy in ArgoCD.

## Steps

1. **Read the conventions.** `gitops/apps/README.md` (the `-d0`/`-d1` pair,
   project `zuno`, Ansible applies Applications directly — `gitops/apps/` is
   not git-synced by anything), `gitops/apps/ai-gateway/` as a model,
   `ansible/tasks/apply_gitops_app.yml`, and one existing role with an OLM
   operator (e.g. `ansible/roles/mariadb/`). Read the example
   `fork/unifai-operator/examples/stack/stack-unifai-devel.yaml` in
   `/home/cl/ClaudeCode/startx-unifai`.

2. **Chart `gitops/charts/unifai/`.** Templates, in sync-wave order:
   CatalogSource (`openshift-marketplace`, image
   `quay.io/zuno/unifai-operator-catalog:<version>` — a version tag pinned in
   values, never `latest` or a moving tag), OperatorGroup, Subscription with
   an explicit `source` and channel (`stable`), then `UnifaiStack` (name
   `unifai`, one per namespace), then object CRs in later waves:
   `UnifaiLLM` entries of type `openai_compatible` pointing at
   `http://ai-gateway.<ns>.svc:8080/v1` with `auth_mode: forward_user_token`
   and the `X-Zuno-*` `default_headers` (WP-146), `UnifaiProvider` entries
   for MCP pointing at the mcp-gateway, `UnifaiAgentBundle` CRs (WP-150),
   `UnifaiRAGSource` CRs (WP-149). Each object kind sits behind a values
   flag so the chart can ship before the fork features it uses. Add a
   `checks.yaml` like other charts.

3. **UnifaiStack values.** `identity.external`: Keycloak URL, realm `zuno`,
   client `unifai`, `clientSecret` from an ExternalSecret.
   `rag.embedding.mode: remote` with the URL and model of
   `gitops/charts/rag-service/values.yaml` (`embeddingServiceUrl`,
   `embeddingModelName: qwen3-embedding-0.6b`), dimension 1024;
   `rag.docling.mode: remote`; storage class `gp3-csi`; OTel endpoint
   (WP-147) when available; `exposure.networkPolicy: true`;
   `deletionPolicy: Retain`. Images pinned by digest in
   `UnifaiStack.spec.images` and verified like ours (`ansible/roles/supply_chain`).

4. **Keycloak client.** Add client `unifai` to
   `gitops/charts/keycloak/files/realm-zuno.json` — the realm import is
   create-only, so the live realm only gets it through
   `templates/job-client-reconcile.yaml` (fed by `configmap-clients.yaml`
   from the same file). Add `templates/externalsecret-unifai-client.yaml` on
   the model of `externalsecret-tekos-frontend.yaml`, and the Vault seed path
   next to the existing client secrets. Redirect URIs use the
   `apps.mycluster.example.com` placeholder the chart already substitutes.

5. **Namespace, mesh, NetworkPolicies.** Add the namespace to
   `gitops/charts/namespaces/values.yaml`. Enrol it in the mesh only if the
   UnifAI pods must reach meshed services with mTLS; remember injection is
   not allowlist membership (add it to the `zuno-mesh` allowlist explicitly).
   Add an ingress peer for UnifAI's multi-agent pods to
   `gitops/charts/ai-gateway/templates/networkpolicy.yaml` and
   `gitops/charts/mcp-gateway/templates/networkpolicy.yaml`, using one peer
   element with both `namespaceSelector` and `podSelector` (intersection,
   as the existing zuno-mlops peer explains).

6. **Applications and role.** `gitops/apps/unifai/application-d0.yaml`
   (catalog, OperatorGroup, Subscription) and `application-d1.yaml`
   (UnifaiStack and objects), and `ansible/roles/unifai/tasks/{install,precheck,check,uninstall}.yml`
   on the model of `ansible/roles/aiagent_operator/tasks/`. Wire the
   component into the Makefile component list of its tier. Run
   `python3 platform/docs/check_docs.py` and `helm template` the chart.

7. **Live install on demo333 — ask first.** demo333 is powered off: ask the
   user to power it on. demo333 already runs the unifai-operator from a
   manually created CatalogSource `unifai-operator-catalog` and Subscription
   `unifai-operator` in `openshift-operators`, managing two stacks
   (`unifai-devel`, `unifai-olm`). Do NOT create a second Subscription for
   the same package: either adopt the existing CatalogSource/Subscription
   into the chart (same names, same namespace) or disable the `-d0` side on
   demo333 via values. Agree the choice with the startx-unifai session first
   — any operator change rolls out to both existing stacks. Use
   `oc --context <demo333-context>` on every command; never touch demo222.

## Progress (2026-10-17, demo333)

1. **Done: repo work** (`05a65658`, fixes `f1fc5668`, `e1a2ed92`, `5a05eddd`).
   - Chart `gitops/charts/unifai/` and Applications `zuno-unifai-d0`/`-d1`.
   - Role `ansible/roles/unifai/`. The role renders no operator objects when
     a Subscription for the package exists that `zuno-unifai-d0` does not own.
   - Client `unifai` in realm zuno, with its secret seeded in Vault at
     `keycloak/unifai`.
   - Namespace `zuno-unifai` (not meshed), plus NetworkPolicy peers on
     ai-gateway, mcp-gateway and the embedding predictor.
   - Wiring into the Makefile, the Day 2 playbooks and the AAP DAGs.
   - `check_docs.py` is green.
2. **Done: deployed on demo333.** Branch `demo333` was fast-forwarded to
   `demo222`. The Vault path was seeded, and the client reconcile Job logged
   `created client unifai`. The token endpoint accepts the seeded secret and
   rejects a wrong one. The role was run locally, never through AAP, with
   `zuno_gitops_target_revision=demo333`. On demo333, `zuno-unifai-d0`
   renders nothing because the hand-made Subscription is kept.
   - `UnifaiStack zuno-unifai/unifai` is Ready, with all 14 pods Running.
     `unifai-devel` and `unifai-olm` stayed Ready throughout.
   - `UnifaiLLM zuno-gateway` and `UnifaiProvider mcp-gateway` are Ready.
   - From the UnifAI pods, the ai-gateway and the mcp-gateway answer, and the
     embedding predictor returns 1024-dimension vectors to the RAG pods only.
3. **Live findings, fixed in the repo.**
   - Vault `confluence/technical` carries `email`/`token`, not the
     `CONFLUENCE_*` names.
   - The MCP transport enum value is `"streamable http"`.
   - Realm zuno has no `admin` user. `adminUsers` and `sharedPublishers`
     now default to the `ai-ops-01` persona.
   - The client needs the UI redirect URI as well as the identity one.
   - ArgoCD has no health check for `UnifaiStack`: the Application read
     Healthy while the stack was in Error. The install role now waits on the
     operator's phase.
   - The operator does not retry an object after a permanent HTTP 400 until
     its spec changes. Recreate the object after fixing the backend.
   - The `:devel` UnifAI images are built from `origin/devel`, which does
     not yet contain the WP-146/147/149 commits. Multiagent is pinned to
     `devel-75c057d02` by digest, through `zuno_unifai_values`, until the
     fork's `devel` is pushed and rebuilt.
4. **Done: acceptance, 2026-10-22** (demo333, GPU nodes down, so local
   models were unavailable). The stack was re-pinned with
   `stack.version: devel-38279972f`, five immutable images built from fork
   `devel` 38279972f (WP-146/147/149 included); `:devel` was not moved, so
   `unifai-devel` and `unifai-olm` were untouched. Chart value added in
   `6b6c0d47`.
   - A real browser login as `ai-ops-01` through realm zuno, then two runs
     of a throwaway workflow (agent on an LLM pointing at the ai-gateway,
     `forward_user_token`, `X-Zuno-Agent: wp151-{node_name}`) answered 200
     with a model reply.
   - The ai-gateway accepted the user's own realm zuno JWT
     (`/v1/chat/completions` depends on `validate_token`): Prometheus
     `zuno_model_calls_total{agent="wp151-wp151-agent"}` carries
     `user=6ab34a06-...`, the Keycloak id of `ai-ops-01` in realm zuno.
   - Tempo spans show `zuno.classification=C2` for the run tagged
     `zuno-classification: C2` and the default `C1` for the untagged run.
   - With the local models down, the gateway fell back through the local
     providers to `openai` (eligible for C1 and C2), as the policy says.
   - Test objects deleted afterwards; `zuno-gateway` and `mcp-gateway` stay.
5. **Follow-ups (not blocking).**
   - UnifAI's LLM validator probes `GET /v1/models/{id}` and then
     `POST /v1/completions`; the ai-gateway implements neither, so each
     validation logs two 404s. Either serve `GET /v1/models/{id}` in the
     ai-gateway or validate through `/v1/chat/completions` in the fork.
   - `UnifaiRAGSource` objects wait for operator 0.1.18 on stable (WP-149,
     WP-154), and RAG ingestion waits for the GPU embedding predictor.

## Acceptance

`helm template gitops/charts/unifai` renders; `check_docs.py` is green; on
demo333 the Applications `zuno-unifai-d0`/`-d1` are Synced and Healthy (read
Synced and Degraded together), `UnifaiStack/unifai` reports all components
Ready, a persona logs in to the UnifAI UI through realm `zuno`, and an
ai-gateway log line shows a request from UnifAI carrying the user's JWT and
`X-Zuno-Agent`. The existing `unifai-devel` and `unifai-olm` stacks remain
Ready throughout.

## Open questions

- Namespace name (`zuno-unifai` proposed) and which day tier the component
  belongs to (ADR-0574 decides; d1 is assumed here).
- Adopt the demo333 Subscription or skip `-d0` there? Step 7.
- Does the stack need GPU for `rag-celery` once embedding and docling are
  remote? The fork's dev profile runs it without GPU; confirm the values.
