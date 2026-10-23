# WP-156: Retire the zuno agent and RAG code

- **State:** Done (2026-10-24)
- **ADRs:** [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0572](../../adr/0572-scope-the-zuno-operator-to-the-platform-foundation.md)
- **Depends on:** [WP-155](wp-155-migrate-remaining-agents-and-cut-demo222-over.md)
- **Related:** [ADR-0564](../../adr/0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0556](../../adr/0556-introduce-a-zuno-operator-with-foundation-infra-and-stack-crds.md), [WP-147](wp-147-unifai-opentelemetry-instrumentation.md), [WP-153](wp-153-guardrails-into-the-ai-gateway.md), [WP-157](wp-157-slim-the-ai-gateway-via-maas.md)
- **Target:** v0.11
- **Estimated files touched:** ~300 deletions and ~25 edits in `zuno-demo` — six component/operator trees, their charts, Applications, Ansible roles, CI matrix entries, ExternalSecrets, Makefile lists, dashboards, and the ADR index statuses.

> The payoff. Only after demo222 runs on UnifAI does the code it replaced
> leave the repository, and the decision records move to Superseded in the
> same change so docs and code never disagree.

> **Update 2026-10-23.** demo222 is retired, so the "uninstall on each cluster"
> steps apply to demo333 only, and the soak criterion is measured on demo333.

## Goal

`components/{agent-runtime,agent-bff,agent-frontend,rag-service,rag-ingestion}`
and `operator/aiagent-operator` are gone with everything that builds, deploys
or tests them; the RAG tables leave pgvector without disturbing the shared
PostgreSQL cluster; dashboards read UnifAI telemetry; the ADRs that described
the removed code are Superseded; `check_docs.py` is green.

## Inventory (2026-10-23)

The full read-only inventory is in
[evidence/wp-156-retirement-inventory.md](../evidence/wp-156-retirement-inventory.md).
Three findings change the steps below:

- agent-runtime is installed and removed by the `llm` role, with ai-gateway:
  edit that role's loops; never `make d2 uninstall llm`;
- the `zuno-admin-api` Keycloak client stays (MaaS `externalOIDC.clientId`,
  the audience mapper of every client, unifai included); only the BFF
  ExternalSecrets go;
- the OKF sign/publish verb (`day3_sign.yml`, `run_okf_signing_job.yml`)
  reads bundles from the agent-runtime image: it is retired with it, the
  zuno-demo-agents release chain and `make d3 admit agents` (ADR-0580)
  replace it.

Cutover criteria are the user's call. On demo333 today: comage and tekos are
served by UnifAI; advantage, finage and naveo are `placeholder` and
deliberately not served (ADR-0007); arkos waits for the `plan_draft_write`
blueprint in an operator release; cognos and soursage are `placeholder`
(no graph shape needed until one becomes active).

**Cutover criterion (user decision, 2026-10-23):** retire when comage, tekos
and arkos are served by UnifAI on demo333 with parity checked; arkos needs
the operator release carrying the `plan_draft_write` blueprint. Placeholder
agents (advantage, finage, naveo, cognos, soursage) are out of scope: they
are served by UnifAI once their OKF status becomes active.

**Step-1 decisions (user, 2026-10-23):** mcp-gateway's
`knowledge.tech.search` (`search_technical_docs`, used by Lightspeed) is
redirected to UnifAI's RAG; the trustyai RAGAS job is redirected to UnifAI's
retrieval; dashboards and SLO rules on BFF/RAG metrics are removed here and
rebuilt in [WP-166](wp-166-rebuild-dashboards-and-slos-on-unifai-telemetry.md);
the Day 3 probes (demo personas, GPU failover drill, stresstest) are ported
to UnifAI. Redirecting to UnifAI's RAG needs a path UnifAI lacks today: its RAG
server accepts a browser session cookie or an internal secret that can act
as any user, and its NetworkPolicy admits nothing from zuno-ai-run. Agreed
design (2026-10-23, fork side owned by the UnifAI operator session): a
read-only RAG search endpoint authenticated only by the user's JWT
(signature, issuer, allow-listed audiences, expiry; same group ACL), a
stack NetworkPolicy option admitting named external clients to the RAG pod
only, and a domain tag on the technical sources (`knowledge.tech`) so the
mapping does not grow silently. The mcp-gateway handler and the RAGAS job
wait for it.

More user decisions (2026-10-23), from porting the Day 3 probes: persona
tokens for evaluations, the stresstest and mlops come from a new dedicated
Keycloak client `zuno-evaluations` (password grant only), not the retiring
`<agent>-frontend` clients; a demo "project" is a UnifAI team (`webinar-*`,
ADR-0569), with per-team classification reported "not checked" (ADR-0565
clause 3 not implemented); the quota tests (`quota_429`, which target the
per-agent quota-demo routes) move to WP-157 and are reported "not run"
until then. Prepared on `prep/wp156`: evaluations default to UnifAI, Day 3
health and availability checks, the three probes, the acceptance gate's
UnifAI files, and the `zuno-evaluations` client with every consumer. Preparation runs on the branch `prep/wp156`, merged into devel
when WP-156 starts (devel deploys on demo333).

**Retirement order, from the inventory** (each step leaves the tree
green before the next):

1. Point what must survive away from the six: evaluations and Day 3
   probes to the UnifAI target; mlops acceptance gate target; mcp-gateway
   `knowledge.tech.search` removed or retargeted; trustyai RAGAS job
   retargeted or removed; dashboards and SLO rules rebuilt on ai-gateway and
   UnifAI metrics; the onboarding scaffold rewritten to emit an OKF bundle
   only.
2. Uninstall live (demo333), while the roles still exist: the `agents` role's
   Applications, `rag`, `rag-ingestion`, `aiagent-operator`, and the
   agent-runtime Applications from the `llm` role's loops only (ai-gateway
   stays).
3. Delete the code and its machinery together: components, charts,
   Applications, roles and build roles, Makefile lists with the AAP DAGs in
   the same change, build-publish matrix, lint steps, hardening entries,
   release tooling lists, the Transit OKF sign path.
4. Data: drop the RAG and agent PostgreSQL databases deliberately (never by
   removing PGO users and letting PGO error-loop), after mlops no longer
   reads `rag-tech`; keep `zuno-admin-api`, Redis and the persona groups.
5. ADR statuses: the supersessions listed in the inventory, written with
   their reciprocal Status lines; `check_docs.py` green.

## Steps

**Live prerequisites.** Steps 1 and 6 act on clusters. demo333 is powered
off: ask the user to power it on. Use `--context` explicitly on every `oc`
command. On demo222 respect demo freezes and message the parallel sessions
first.

1. **Uninstall before deleting.** On each cluster, run the uninstall verbs
   for the components still deployed (`make d2 uninstall agents`;
   `make d1 uninstall aiagent-operator`; agent-runtime through the `llm`
   role's loops, never `make d2 uninstall llm`, which removes ai-gateway; check the
   tier lists `DAY1_RUN_COMPONENTS`, `DAY2_RUN_COMPONENTS` in the `Makefile`
   for the exact names) while the roles still exist. Check the ArgoCD
   Applications are gone, not just OutOfSync.

2. **Inventory with grep, then delete.** `grep -rln` for each component name
   across the repo and delete, per component:
   - code: `components/agent-runtime`, `components/agent-bff`,
     `components/agent-frontend`, `operator/aiagent-operator`;
   - charts: `gitops/charts/{agent-runtime,aiagent-operator}`
     and the per-agent frontend charts (`gitops/charts/{advantage,arkos,comage,finage,naveo,tekos}`)
     if they only deploy agent-frontend — read each first;
   - Applications: `gitops/apps/{agent-runtime,aiagent-operator}`
     and the per-agent ones under the same condition;
   - Ansible roles: `ansible/roles/{agent_build,aiagent_operator,aiagent_operator_build}`;
     keep `ansible/roles/agents` only if it still drives signing/OCI publish;
   - Makefile lists (`DAY1_*`, `DAY2_*`, `DAY3_*`) and help lines;
   - CI: matrix entries in `.github/workflows/build-publish.yml`, and
     `platform/supply-chain/check_build_matrix.py` expectations;
   - Keycloak: `externalsecret-<agent>-frontend.yaml` templates in
     `gitops/charts/keycloak/templates/` and the matching clients in
     `files/realm-zuno.json` (the live clients must be removed by the
     reconcile job or by hand: the realm import is create-only);
   - Vault seed entries and ExternalSecrets of the removed services.
   Keep `agents/` (OKF bundles stay the source of truth) and `evaluations/`.

3. **Evaluations.** Remove the agent-runtime target from
   `evaluations/*/run_scenarios.py` so `--target unifai` becomes the only
   path; update `evaluations/README.md`.

4. **Guardrails and telemetry.** Confirm the ai-gateway guardrails hook
   (WP-153) is on everywhere before the agent-runtime one disappears.
   Rewrite `gitops/charts/grafana/templates/dashboard-run-trace.yaml`,
   `gitops/charts/perses/templates/dashboard-run-trace.yaml` and
   `gitops/charts/grafana/templates/dashboard-usage-cost.yaml` on UnifAI and
   ai-gateway metrics only (WP-147).

5. **PostgreSQL.** Drop only the agent-runtime databases' users and grants
   (`agent-checkpoints`, `agent-conversations`) with an explicit, reviewed
   change, never by deleting the PostgreSQL cluster or a database PGO
   manages (PGO does not recreate a dropped database and error-loops the
   whole cluster). The RAG schema and its pgvector tables stay with
   rag-service (decision below; their removal is part of WP-168).

6. **Run the full chain.** On demo333: `make d0 check`, `make d1 check`,
   `make d2 check`, `make d3 test`; every ArgoCD Application Synced and
   Healthy (read Synced and Degraded together).

7. **Docs.** Update the ADR index `docs/adr/README.md` and the superseded
   records per its "How a decision changes" section: ADRs listed under
   "Planned supersession" in ADR-0561, ADR-0564 and ADR-0568 (e.g.
   ADR-0018, ADR-0039, ADR-0342, ADR-0308, ADR-0327, and the RAG ADRs) move
   to Superseded or Superseded in part with reciprocal links; set ADR-0572's
   amendment of ADR-0556 in force. Run `python3 platform/docs/check_docs.py`.
   Update `components/README.md`.

## Phase 2 done (2026-10-23)

**Uninstalled live on demo333** (ArgoCD Applications deleted, before any
code left): `agent-runtime` (from the `llm` role's loops only, ai-gateway
stays), every per-agent agent-frontend + agent-bff Application (charts
`tekos` - Application `zuno-api` -, `comage`, `advantage`, `finage`,
`arkos`, `naveo`), `aiagent-operator` with its CRD, and
`zuno-connectivity-link-quota-d1` (the Kuadrant quota demo route half).

**Removed from the repository** (branch `prep/wp156-phase2`):

- Steps 2-3: `components/{agent-runtime,agent-bff,agent-frontend}`,
  `operator/aiagent-operator`; charts `agent-runtime`, `aiagent-operator`
  and the six per-agent charts (read first: each rendered only the
  frontend/BFF workloads, their ExternalSecrets/Route/NetworkPolicy, or an
  AIAgent CR); their Applications and `gitops/apps/connectivity-link-quota`;
  roles `agent_build`, `aiagent_operator`, `aiagent_operator_build`; the
  Makefile lists with the AAP surveys and DAGs; the build-publish matrix
  entries, the lint Go job (agent-bff, agent-frontend and its Redis
  service), the agent-runtime tests, the AIAgent contract check,
  `platform/api/lint_openapi.py` and the deployment-snapshot CI step; the
  hardening and release-tooling lists; the agent-runtime NetworkPolicy
  peers in ai-gateway, mcp-gateway and rag-service and the frontend peer
  in redis; the per-agent frontend session Vault seeds.
- The `agents` role stays for its check (the ADR-0053 acceptance gate,
  run against UnifAI): install/uninstall apply nothing, precheck reads the
  UnifaiAgentBundles. The `llm` role loses only agent-runtime.
- connectivity-link: the Day 1 gateway half stays; `quotaEnforcement.routes`
  keeps only `name`/`hostname`, nothing sets `route.enabled`, and the route
  template requires an explicit backend. Quota in front of UnifAI is
  WP-157's.
- Step 3 (evaluations): UnifAI is the only target of
  `evaluations/*/run_scenarios.py` and every `security_checks.py`
  (`--target`/`EVAL_TARGET` accept only `unifai`); the runtime/BFF/frontend
  handlers and constants are gone, check and scenario counts unchanged
  (naveo's `entitlement_without_business_role_denied`, which still posted
  to the BFF, is now reported skipped as a placeholder agent). The
  runtime-only `stress_test.py` batteries of tekos, arkos and comage are
  deleted (the stresstest reports that layer "not run"), and the
  tool-calling conformance test no longer reads agent-runtime's source.
  The `<AGENT>_FRONTEND_CLIENT_SECRET` fallback stays.
- `platform/templates/agent/scaffold_agent.py` no longer emits the AIAgent
  CR, chart, Applications, frontend client or frontend/BFF images; it
  writes the OKF bundle draft (to move to zuno-demo-agents, ADR-0576) and
  the evaluation skeleton.
- Step 7: the planned supersessions are written (ADR index and
  [CHANGELOG](../../adr/CHANGELOG.md), 2026-10-23), RAG ADRs excluded.

**What remains:**

- Step 5, done 2026-10-23 after a review approved by the user: the
  databases `agent-checkpoints` (89 MB, 4 tables) and `agent-conversations`
  (8.5 MB, 6 tables) had no connection and no grant beyond their own roles,
  and rag-service does not read them (its project-membership projection
  was pushed by agent-runtime). Removed from `spec.users`, the init and
  schema-grants SQL, the values, the two credential ExternalSecrets, the
  postgresql role's bootstrap list and the vault seeds; once PGO had
  reconciled, both databases and the roles `agentcheckpoints` and
  `agentconversations` were dropped by hand, after a `pg_dump` of each
  (kept outside the repository) and on top of the pgBackRest backups.
- The eight `<agent>-frontend` Keycloak clients, their `access` roles and
  group mappings, their `<agent>-frontend-client-secret` ExternalSecrets,
  `KC_VAULT` items and Vault seeds were removed on 2026-10-23 once the
  harnesses and the mlops mirror had moved to `zuno-evaluations` (WP-169).
  The live clients were deleted by hand: the reconcile Job never deletes
  one. Their Vault paths `keycloak/<agent>-frontend` stay as inert data.
- The `make d3 sign agents` verb signs the last agent-runtime image left in
  `zuno-ai-build` and has no consumer: `make d3 admit agents` replaces it,
  WP-165 removes it with the OKF Transit chain.
- Step 4: dashboards and SLO rules on BFF/runtime metrics are WP-166's.
- Step 6: the live chain on demo333 after the merge into devel.
- Comments in kept components (ai-gateway, mcp-gateway, rag-service,
  mlops, diagram-render) still name agent-runtime as their past caller.
- ADR-0042, ADR-0214 and ADR-0411 concern only the retired frontend but
  are in no planned supersession list: left for a decision.

## Decision of 2026-10-23: the Red Hat documentation keeps `rag-service` alive

The knowledge corpus of `rag-service` is the Red Hat product documentation
(about 874 `docs.redhat.com` pages loaded by `rag-ingestion`); UnifAI's RAG holds
only the tekos Confluence spaces. The user decided to retire everything else of the
old stack now and to **keep `rag` (rag-service) and `rag-ingestion`** for that
documentation only, until [WP-168](wp-168-migrate-the-red-hat-product-documentation-to-unifai-rag.md)
moves it to UnifAI. In this work package, `rag-service`, `rag-ingestion`, their
charts, Applications, raw S3 prefix and the mcp-gateway fallback to `rag-service`
therefore stay; the removal of the rag stack is part of WP-168.

## Acceptance

No file references the removed components (`grep -rn` returns only ADR
history and CHANGELOG); `check_docs.py` green; CI lint and build workflows
green; on demo333 the step-6 chain passes and no orphan Deployment,
ExternalSecret or Keycloak client of the four retired components remains;
`search_technical_docs` still answers from UnifAI and rag-service; the PostgreSQL cluster
stays Healthy throughout.

## Open questions

- ~~Do the per-agent charts (`gitops/charts/<agent>/`) carry anything besides
  agent-frontend?~~ No (read 2026-10-23): frontend/BFF Deployments,
  Services, ServiceAccounts, ExternalSecrets, Route and NetworkPolicy, or a
  single AIAgent CR for arkos/naveo.
- ~~Does the zuno-okf extraction stream (ADR-0506..0510) need a status change
  in the same pass?~~ No: ADR-0506, ADR-0507, ADR-0509 and ADR-0510 were
  already retired by ADR-0576/ADR-0580 on 2026-10-22; ADR-0508 stays
  `Proposed`.

## Step 6 on demo333 (2026-10-24)

The full chain ran green on demo333 after phase 2, the PGO drop and the
WP-165 cutover: `make d0 check` and `make d1 check` with no failure;
`make d2 check` for every Day 2 component (all installed; supply-chain: 11
images verified; agents: the pinned release admitted keyless and the tekos
acceptance gate as the `eval-*` personas 18/18, 12/12, 4/4, catalog 8/8);
`make d3 test` 15/15. Every Application Synced and Healthy apart from the
three pre-existing OutOfSync ones. `rag-service` and `rag-ingestion` remain
on purpose for the Red Hat documentation until WP-168 (decision above).

