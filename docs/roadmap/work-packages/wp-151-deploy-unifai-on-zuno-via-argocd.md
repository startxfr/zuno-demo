# WP-151: Deploy UnifAI on zuno through ArgoCD

- **State:** Not started
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
