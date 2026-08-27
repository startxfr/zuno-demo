# WP-085: Integrate OpenShift Lightspeed with Zuno inference, knowledge and identity

- **State:** **Done — live-verified 2026-08-27 on demo222.** Les quatre tests console sont
  concluants pour `consultant-01` et `sale-01` : documentation OpenShift, introspection cluster,
  connaissance Confluence interne, et refus correct d'une écriture Confluence. L'app-server charge
  `Loaded 2 tools from MCP server 'zuno-mcp'` — exactement le plafond `MCP_FRONTDOOR_CAPABILITIES`,
  servi par identité utilisateur réelle via TokenReview. `make d3 test platform` : 9/9.
  **Réserve** : l'inférence passe en direct sur le predictor KServe et non par MaaS — voir
  « Contournement MaaS » ci-dessous, bloqué sur WP-076.
- **ADRs:** ADR-0524 (Implemented, avec la réserve clause 1 - inférence hors MaaS)
- **Depends on:** ADR-0521/WP-076 (Implemented - MaaS is the local-model transport this reuses),
  ADR-0117 (Implemented - the Confluence MCP server), ADR-0060 (Implemented - Day 1/Day 2/Day 3
  sequencing)
- **Related:** WP-072/WP-073 (the `aap`/`aap-config` two-component split this mirrors)

## Contournement MaaS en vigueur (temporaire)

`olsConfig.provider.endpointMode: direct` — Lightspeed appelle
`qwen36-27b-instruct-kserve-workload-svc:8000/v1`, le même endpoint que le fallback documenté
d'`ai-gateway`, et non la passerelle MaaS. C'est une **régression assumée d'ADR-0521**, décidée
avec l'opérateur humain, parce que le plan de contrôle MaaS ne rapproche plus aucune identité
d'une `MaaSSubscription`.

Retour à MaaS = deux éditions, rien d'autre :
1. `gitops/charts/lightspeed-config/values.yaml` : `endpointMode: maas` +
   `credential.mode: saTokenSecret` (ou `apiKey`)
2. retirer le bloc `lightspeed` de `gitops/charts/models/templates/networkpolicy-qwen.yaml`
   et de `ansible/roles/models/tasks/install.yml`

L'entitlement MaaS (`MaaSSubscription` + sujet OPA) est resté en place et intact exactement pour
rendre ce retour trivial. Une garde de rendu refuse déjà `endpointMode: maas` combiné à
`credential.mode: staticToken`, qui produirait un 401 opaque.

## Vérification navigateur — quatre défauts, dont un de notre code (2026-08-27)

La vérification en tant que `consultant-01` a validé la documentation OpenShift du premier coup et
révélé quatre défauts, tous corrigés :

1. **`valueFrom.type` devait être `kubernetes`, pas `client`.** C'est le plus structurant, et il
   tranche l'inconnue que ce WP portait depuis le début (« le plugin console transmet-il le token
   pour `type: client` ? »). Réponse : **non** — la lecture de `ols/utils/mcp_utils.py` dans
   l'image de l'opérateur montre que `client` attend des en-têtes que *le client de l'API* doit
   fournir par serveur, ce que la console n'envoie jamais ; `zuno-mcp` était donc écarté **avant
   tout appel** (`requires client headers but none provided`) et la gateway ne recevait rien.
   `kubernetes` résout le placeholder en `Bearer <user_token>`, `user_token` étant documenté comme
   *"User's kubernetes token"*. C'est aussi ce que Red Hat utilise pour son propre serveur
   `openshift`, dans le même fichier de configuration. Le per-user est donc atteint **sans** le
   repli service-identity que ce WP tenait en réserve.

2. **Aucun accès au chat.** L'opérateur crée le ClusterRole `lightspeed-operator-query-access`
   mais ne le lie à personne : tout utilisateur voyait *"Not authorized"*. L'app-server tranche par
   `TokenReview` + `SubjectAccessReview`, donc le token console était bien transmis — il ne manquait
   que le droit.

3. **Introspection cluster vide.** *"You don't have permission to list pods"* était le comportement
   **correct** : `openshift-mcp-server` agit avec les droits réels de l'utilisateur, et les personas
   n'en avaient aucun. Résolu par une RoleBinding `view` sur les namespaces Zuno, en réutilisant la
   découverte `zunoManagedNamespaces` existante.

4. **Un défaut de notre propre code.** `automountServiceAccountToken: false` — posture d'origine
   légitime (*"ce service n'appelle jamais l'API Kubernetes"*), rendue fausse par l'ajout de
   TokenReview à `app/auth.py`. Chaque appel de Lightspeed répondait **503**, ce qui faisait
   ressembler un bug d'infrastructure à un refus d'autorisation. Le montage est désormais
   conditionné à `lightspeed.enabled`.

**Piège méthodologique à retenir :** le test « demander la création d'une page Confluence » a
d'abord semblé réussir alors qu'aucun outil Confluence n'était chargé — le modèle refusait faute
d'outil, pas par politique. Un test négatif ne prouve rien tant que le chemin positif n'est pas
prouvé.

## Défauts externes constatés en live (2026-08-27)

1. **L'opérateur Lightspeed v1.1.2 ignore `spec.llm.providers[].credentialKey`** et exige en dur
   la clé `apitoken`, alors que son propre CRD documente le champ (*"defaults to apitoken if not
   set"*). Symptôme : `OLSConfig.status` vide, aucun operand. Contourné par `credential.mode:
   staticToken`, qui rend un Secret Opaque portant `apitoken`.
2. **MaaS ne résout plus les subscriptions** : `403 no matching subscription found for user`,
   reproduit pour l'identité **connue bonne** `ai-gateway` et sur `gpt-oss-20b`, un modèle que ce
   WP n'a jamais touché. Éliminés par test : cache informer (resync propre après redémarrage),
   PostgreSQL (connecté), `MaaSModelRef` (`Ready`), `MaaSSubscription` (`Ready`/`Valid`).
   Périmètre **WP-076/ADR-0521**, pas celui-ci.
3. **L'opérateur pose ses propres NetworkPolicies** : `lightspeed-app-server` n'admet sur 8443 que
   `openshift-console`, `openshift-monitoring` et l'ingress — **pas** le same-namespace. La sonde
   Day 3 cible donc `lightspeed-rhokp`/`openshift-mcp-server`, qui admettent `podSelector: {}`.

## Acquis positif

**TokenReview accepte un token de ServiceAccount legacy sans audience** — le 403 (et non 401) le
prouve. C'était la principale inconnue de l'étape 2 de ce WP, désormais tranchée.

## Goal

Make OpenShift Lightspeed answer console questions using a Zuno-served local model, the
operator's own OpenShift documentation and live-cluster introspection, and read-only internal
Confluence knowledge reached through the **existing** MCP Gateway - with the operator installed
in Day 1 and every Zuno-dependent wire connected in Day 2.

## Why

Every backing capability already exists; none of it is currently reachable from the console. Two
concrete blockers make this more than configuration, both verified in-repo:
`components/mcp-gateway` exposes REST (`/v1/tools/{name}/invoke`), not MCP, so Lightspeed's
`spec.mcpServers[]` has nothing to connect to; and `components/mcp-gateway/app/auth.py` accepts
only a Keycloak-issued JWT, which Lightspeed cannot produce from any of its three header sources.
Step 3 and step 4 below close exactly those two gaps.

## Component and file layout (ADR-0524 clause 7)

Two components, mirroring `aap`/`aap-config` exactly - two roles and **two charts**, one per
component. Each chart is rendered by the repository's standard `-d0`/`-d1` Application pair,
whose Helm value gates keep the rendered sets disjoint (`aap` does exactly this: `-d0` renders
namespace+Subscription, `-d1` the operand CR). So the split here is by component lifecycle and
day tier, **not** because ArgoCD cannot share a chart - it demonstrably can.

| | Day 1 - `lightspeed` | Day 2 - `lightspeed-config` |
|---|---|---|
| Role | `ansible/roles/lightspeed/tasks/{install,precheck,uninstall}.yml` | `ansible/roles/lightspeed_config/tasks/{install,precheck,uninstall}.yml` |
| Chart | `gitops/charts/lightspeed` | `gitops/charts/lightspeed-config` |
| Apps | `zuno-lightspeed-d0` (namespace + operator), `zuno-lightspeed-d1` -> `gitops/charts/noop` | `zuno-lightspeed-config-d0` (renders nothing), `zuno-lightspeed-config-d1` (the operand) |
| Contains | Namespace membership, OperatorGroup, Subscription, CSV wait | `OLSConfig/cluster`, provider Secret, CA ConfigMap, Keycloak client, MaaS entitlement wiring |
| Depends on | OLM only | `models`, `mcp`, `keycloak` |

Makefile placement:

- `DAY1_RUN_COMPONENTS`: insert `lightspeed` after `openshift-ai`, before `aiagent-operator` -
  it has no dependency on either, and this keeps `aiagent-operator` last as its comment requires.
- `DAY2_RUN_COMPONENTS`: append `lightspeed-config` **after `mlops`** (before the check-only
  `supply-chain`), so it runs once MaaS entitlement, the `/mcp` front-door and the agents are all
  in place.
- `ansible/playbooks/day1_install.yml` `day1_components` and `day2_install.yml`
  `day2_components` get the same two entries in the same positions, with a comment stating why
  the configuration half waits for Day 2.

The Day 1 role installs the operator and stops there. It must **not** create `OLSConfig` - an
`OLSConfig` without a reachable model or MCP endpoint sits Degraded for the whole Day 2 window.

## Steps

### Step 1 - Day 1: install the operator

Discover catalog and channel from the `PackageManifest` at run time rather than hardcoding, the
same pattern `ansible/roles/aap/tasks/install.yml` uses (fail loudly if the package is absent).
Confirmed on this cluster 2026-08-26: package `lightspeed-operator`, catalog `redhat-operators`,
`defaultChannel: stable`, CSV `lightspeed-operator.v1.1.2`, InstallModes **`OwnNamespace` only**.
`openshift-lightspeed` is added to `gitops/charts/namespaces/values.yaml` and owned solely by
`zuno-namespaces-d0`. It is an `openshift-*` operator namespace, which normally means the
component's own chart creates it (`lws`, `custom-metrics-autoscaler`) - but it holds a mandatory
singleton CR, so it is tracked centrally like the RHOAI namespaces instead. This chart's vendored
`project` block is therefore left **disabled**; enabling it in both places makes ArgoCD report the
Namespace as shared between two Applications. No `istio-injection` label. The entry sets
`skipNetworkPolicy: true` and no quota - see ADR-0524's Operational considerations for why both
are deferred rather than guessed, and treat replacing them as live-verification work.
The OperatorGroup is OwnNamespace-scoped (`target: openshift-lightspeed`) because the CSV supports
no other install mode - subscribing through a shared AllNamespaces OperatorGroup puts the CSV in
`Failed`/`UnsupportedOperatorGroup`, the exact failure `lws` documents.

### Step 2 - Day 2: local inference through MaaS

- `gitops/charts/models/values.yaml`: add a `MaaSSubscription` + `MaaSAuthPolicy` subject for
  Lightspeed's ServiceAccount, mirroring the existing `*-ai-gateway` entries (`user:
  system:serviceaccount:openshift-lightspeed:<sa>`, own rate limit, own priority).
  **The SA name cannot be determined ahead of the install** - checked 2026-08-26 against the
  v1.1.2 bundle CSV, which declares only `lightspeed-operator-controller-manager` (the operator's
  own SA); the operand ServiceAccounts are created by the operator at reconcile time. Read it off
  the running cluster after step 1 and before writing this value. It matters because the live
  `AuthPolicy/maas-gateway-auth` OPA `model_access` map lists only
  `system:serviceaccount:zuno-ai-run:ai-gateway` plus groups `agent_tekos`/`sales` - an unlisted
  identity is denied by omission, silently.
- `OLSConfig.spec.llm.providers[0]`: `type: rhoai_vllm`, `url` the MaaS gateway path for
  `qwen36-27b-instruct-maas`, `credentialsSecretRef` + `credentialKey`.
- `spec.ols.defaultProvider` / `defaultModel` set to that provider/model.
- `spec.ols.additionalCAConfigMapRef` for the MaaS gateway's serving CA (the CRD documents this
  field as CA trust "between OLS service and LLM Provider" - exactly this hop).

**Open item, narrowed 2026-08-26 (do not simply copy ai-gateway).** `credentialsSecretRef` takes
a **static Secret**, and neither of MaaS's two accepted credentials drops into that shape cleanly:

- *SA token* - the path this platform actually proved. `ai-gateway` mounts a **projected**
  ServiceAccount token (`audience: https://kubernetes.default.svc`, `expirationSeconds: 3600`),
  matching `AuthPolicy/maas-gateway-auth`'s `kubernetesTokenReview.audiences` exactly. WP-076 step
  3 made this the primary path. **Lightspeed's CRD cannot express a projected token** - there is no
  volume/projection field on `OLSConfig`, only `credentialsSecretRef`. Reproducing it means a
  long-lived `kubernetes.io/service-account-token` Secret, which is audience-less. Whether
  `TokenReview` accepts an audience-less legacy token when the policy requests an explicit audience
  must be **verified live against this cluster**, not assumed - it is the single fact this step
  turns on.
- *`sk-oai-*` API key* - fits `credentialsSecretRef` perfectly, but is currently **disabled
  platform-wide**: `gitops/charts/ai-gateway/values.yaml` sets `maasAdapter.apiKeyEnabled: false`
  and the Vault path `maas/gateway-api-key` is unseeded. That gate exists because of a live
  incident on 2026-08-26 - rendering the `ExternalSecret` against an unseeded Vault path leaves it
  permanently Degraded, and ArgoCD's wave-ordered sync then never reaches the Deployment, wedging
  the whole Application.

**Therefore:** decide by testing the legacy-token audience behaviour first, since it needs no new
secret material. If it works, use it. If it does not, mint and seed a real MaaS key **before**
rendering anything - and `gitops/charts/lightspeed-config` must replicate ai-gateway's
`apiKeyEnabled`-style gate so an unseeded path renders nothing rather than wedging the app.
Record which one won and why.

### Step 3 - Day 2: MCP front-door on the existing gateway

**Implementation finding (2026-08-26): a caller with no OKF bundle is denied everything.**
`app/policy.py`'s `evaluate()` fails closed on a caller that declares no agent and no task
(`"missing X-Zuno-Agent/X-Zuno-Task declaration"`), then requires that agent to declare the
requested tool in the named task - ADR-0011's first two factors, made enforced rather than
aspirational by ADR-0036. A standard MCP client declares neither.

An OKF bundle for Lightspeed was built and then **removed on the decision that Lightspeed is not a
Zuno agent and should not appear as one**. The replacement is an explicit, narrow exception:

- `evaluate_without_declaration()` in `app/policy.py` runs factors 3-5 only. It shares
  `_evaluate_tool_policy()` with `evaluate()`, so there is no duplicated policy logic and no way
  for the two to drift. Its docstring names the single sanctioned caller.
- The front-door carries a **capability allowlist** in place of the missing bundle -
  `lightspeed.frontdoorCapabilities` in `gitops/charts/mcp-gateway/values.yaml`, delivered as
  `MCP_FRONTDOOR_CAPABILITIES`. It is enforced on `tools/list` **and** on `tools/call`; enforcing
  it only on `tools/list` would make it advisory, since a client may call a name it was never
  advertised.
- `_authorize_and_invoke(frontdoor_policy=True)` is the only place the exception reaches the
  invoke path. Everything after the decision - self-scope check, auth_mode, delegated credentials,
  telemetry - is shared with the REST path.

Net effect: the ceiling is now harder to widen than a bundle would have been (a Helm value visible
in the Deployment spec, versus a Markdown edit under `agents/`), and factors 3-5 still run per
call. What is genuinely given up is per-*agent* scoping, which is meaningless for a caller that is
not an agent.

Add a standard MCP streamable-HTTP endpoint at `/mcp` to `components/mcp-gateway`, in the same
FastAPI app as `/v1/tools/{tool_name}/invoke`.

- `tools/list` returns the caller's **already-intersected** capability set - resolved through
  `app/policy.py` and `app/bindings.py`, never a hand-maintained list - so a caller entitled only
  to `confluence.page.search`/`.read` sees exactly two tools.
- `tools/call` routes into the same `evaluate()` -> `downstream.invoke()` path the REST endpoint
  uses. No second authorization path, no second binding registry.
- `gitops/charts/mcp-gateway`: NetworkPolicy gains a namespace-scoped ingress allow for
  `openshift-lightspeed` on 8080. Today it admits only `agent-runtime` and `acceptance-gate`
  pods.
- `OLSConfig.spec.featureGates: [MCPServer]` - **without this the whole `mcpServers[]` block is
  inert**; all feature gates are off by default on v1.1.2.
- `OLSConfig.spec.mcpServers[0]`: name `zuno-mcp`, `url`
  `http://mcp-gateway.zuno-ai-run.svc.cluster.local:8080/mcp`, a `timeout` well above the 5s
  default (the gateway's own `DOWNSTREAM_TIMEOUT_SECONDS` is 40s).
- Rebuild and redeploy `mcp-gateway`. **Push first** - the BuildConfig clones `origin/main`, not
  the local tree.

### Step 4 - Day 2: per-user identity (ADR-0524 clause 5)

**Per-user is the default.** `mcp.identityMode: perUser` sets
`mcpServers[0].headers[0].valueFrom.type: client`, so Lightspeed forwards the console user's own
OpenShift token, and `validate_token_or_kubernetes()` in `app/auth.py` resolves it through the
Kubernetes `TokenReview` API.

No group-mapping table was needed, which was not obvious up front: `oc get groups` on this cluster
returns `consultant` and `sales` among others, and both are already `allowed_groups` in
`policies/tools/tool-policy.yaml`. The reviewed groups therefore feed ADR-0011 directly.
`system:authenticated`, `system:authenticated:oauth` and `system:masters` are stripped first -
every authenticated principal carries them, so leaving them in would let any cluster user match a
policy entry that happened to list one.

The JWT path is untouched: `_looks_like_jwt()` routes three-segment tokens to the existing
Keycloak validator and everything else to TokenReview, and the new dependency is used **only** by
`/mcp`, so the REST contract still accepts Keycloak tokens and nothing else.

RBAC: `gitops/charts/mcp-gateway/templates/rbac-tokenreview.yaml` binds the gateway's
ServiceAccount to `system:auth-delegator` - create on tokenreviews/subjectaccessreviews and
nothing more. It is gated on `lightspeed.enabled`, because this is the only reason mcp-gateway
touches the Kubernetes API at all (its ServiceAccount previously carried no RBAC by design).

*Service identity* remains available as `identityMode: serviceIdentity` (Keycloak
client-credentials via a Vault-seeded Secret, group `lightspeed_readonly`) but is a **compatibility
fallback only**: it collapses every console user onto one identity and loses per-user Confluence
scoping.

**Verify live:** that the console plugin actually forwards the user token for `type: client` on
v1.1.2. If it does not, flip `identityMode` to `serviceIdentity`, record the evidence here, and do
not simulate it.

### Step 5 - Day 2: read-only Confluence

`policies/tools/tool-policy.yaml`: add the Lightspeed group to `allowed_groups` on
`confluence.page.search` and `confluence.page.read` **only**. Leave `.create` and `.update`
untouched. The `/mcp` front-door advertises only what that intersection permits, and
`spec.ols.toolsApprovalConfig` keeps its `tool_annotations` default. Three independent layers,
each sufficient on its own.

### Step 6 - Day 2/Day 3: native knowledge, introspection and operations

- Native OpenShift docs: **write nothing**. Leave `spec.ols.rag[]` empty and `byokRAGOnly` unset
  so the RHOKP sidecar keeps serving them.
- `spec.ols.introspectionEnabled`: leave at its `true` default (ADR-0524 clause 6).
- Day 3 `test`: **two complementary checks, neither of which hardcodes a Service name.**
  - `ansible/roles/lightspeed_config/tasks/precheck.yml` reads `OLSConfig.status.conditions` -
    the operator's own contract, covering model reachability, CA mount, cache and console plugin.
  - `ansible/roles/day3/tasks/lightspeed_health_check.yml` gets real HTTP evidence, because a
    condition is still the operator's self-report and would not catch a wedged API pod it
    believes is fine. It **discovers** the Service at run time (`k8s_info` over
    `openshift-lightspeed`, rejecting operator/webhook/metrics Services, preferring an
    app-server-shaped name), derives the scheme from the port's own name/number, and probes a
    candidate list of health paths, passing if any answers below 500 - a 4xx counts, since it
    still proves something is serving. Discovery, not a constant, so an operator upgrade that
    renames the Service does not read as an outage.

    The Job runs **in `openshift-lightspeed`**, not `zuno-ai-run`. Same-namespace traffic is
    always admitted by the platform default-deny baseline, so this needs no NetworkPolicy allow
    and keeps working whether or not that namespace's `skipNetworkPolicy` is later removed. It
    mounts the auto-populated `openshift-service-ca.crt` ConfigMap so TLS is genuinely verified
    rather than skipped, and falls back to an unverified connection only if that ConfigMap is
    absent - saying so in the result detail rather than silently claiming a verified check.

    Absent Lightspeed is not a failure: the file no-ops with a `skipped` row, so
    `make d3 test platform` stays green on a cluster that never installed the operator.

    **Live-verification follow-up:** the probe reports which Service and which health path
    answered. Once a real run shows both, pin the path in `PATHS` and record the Service name
    here, so the candidate sweep becomes a one-shot check rather than a permanent search.
- Day 3 `check`: both roles' `precheck.yml` are wired into `ansible/playbooks/day3_check.yml`,
  and a new `DAY3_CHECK_ONLY_COMPONENTS` Makefile group makes `make d3 check lightspeed` /
  `make d3 check lightspeed-config` valid targets (they support neither test/stresstest nor
  backup/restore). The component-filter expression in `day3_check.yml` was generalized off its
  hardcoded `'postgresql'` literal at the same time, or the two new entries would have been
  silently unreachable.
- Observability: the CSV sets `operatorframework.io/cluster-monitoring: true`, so operator
  metrics land in platform monitoring without extra work. Confirm before claiming it.
- Docs: `docs/platform/` component page and the ADR index row for ADR-0524.

## Verification checklist (operator step - ask before running)

- `make d1 install lightspeed`, then `oc get csv -n openshift-lightspeed` shows
  `lightspeed-operator.v1.1.2` `Succeeded` and `oc get crd olsconfigs.ols.openshift.io` exists.
- `make d2 build mcp` + `make d2 install mcp`, then `curl` the `/mcp` endpoint from an
  in-namespace debug pod and confirm `tools/list` returns exactly the read-only Confluence tools
  for the Lightspeed identity - and **404s or empty for a write capability**.
- `make d2 install lightspeed-config`, then `oc get olsconfig cluster -o
  jsonpath='{.status.conditions}'` reports healthy API/console-plugin/cache/MCP conditions.
- Browser verification as a real demo persona (see the Playwright method used for WP-061): open
  the console assistant and prove three answers - one from OpenShift documentation, one about
  live cluster state (introspection), one citing internal Confluence content.
- Negative test: ask Lightspeed to create or edit a Confluence page and confirm the gateway
  denies it, with the denial visible in `mcp-gateway` logs rather than only in the chat reply.
- `make d3 test platform` and `make d3 check lightspeed` both pass.

## Risks and known unknowns

1. **Console plugin token forwarding** (step 4) - the single largest unknown; gates the per-user
   half only, not the WP.
2. **MaaS credential shape** (step 2) - narrowed to one live test: does `TokenReview` accept an
   audience-less legacy SA-token Secret when the policy requests an explicit audience? Resolve
   early, it blocks every downstream step. Note the API-key alternative carries a known
   ArgoCD-wedging failure mode if rendered unseeded.
3. **MCP protocol conformance** - Lightspeed's client is stricter than `agent-runtime`'s REST
   caller. Test `tools/list`/`tools/call` against the real Lightspeed pod, not only against
   `components/mcp-gateway/tests`.
4. **Operator-managed PostgreSQL** - Lightspeed brings its own; do not attempt to point it at the
   PGO cluster, the CRD has no field for it.

## Status updates (once live-verified)

- ADR-0524 moves to `Implemented` only when steps 1-6 are all live-verified. If step 4's per-user
  half is blocked by the console plugin, ADR-0524 stays `Partially implemented` with the blocking
  evidence recorded here.
