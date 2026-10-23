# WP-156: Retire the zuno agent and RAG code

- **State:** Not started
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

## Steps

**Live prerequisites.** Steps 1 and 6 act on clusters. demo333 is powered
off: ask the user to power it on. Use `--context` explicitly on every `oc`
command. On demo222 respect demo freezes and message the parallel sessions
first.

1. **Uninstall before deleting.** On each cluster, run the uninstall verbs
   for the components still deployed (`make d2 uninstall agents`,
   `rag`, `rag-ingestion`; `make d1 uninstall aiagent-operator`; check the
   tier lists `DAY1_RUN_COMPONENTS`, `DAY2_RUN_COMPONENTS` in the `Makefile`
   for the exact names) while the roles still exist. Check the ArgoCD
   Applications are gone, not just OutOfSync.

2. **Inventory with grep, then delete.** `grep -rln` for each component name
   across the repo and delete, per component:
   - code: `components/agent-runtime`, `components/agent-bff`,
     `components/agent-frontend`, `components/rag-service`,
     `components/rag-ingestion`, `operator/aiagent-operator`;
   - charts: `gitops/charts/{agent-runtime,aiagent-operator,rag-service,rag-ingestion}`
     and the per-agent frontend charts (`gitops/charts/{advantage,arkos,comage,finage,naveo,tekos}`)
     if they only deploy agent-frontend — read each first;
   - Applications: `gitops/apps/{agent-runtime,aiagent-operator,rag,rag-ingestion}`
     and the per-agent ones under the same condition;
   - Ansible roles: `ansible/roles/{agent_build,aiagent_operator,aiagent_operator_build,rag,rag_build,rag_ingestion,rag_ingestion_build}`;
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

5. **pgvector.** Remove the RAG schema apply
   (`gitops/charts/rag-service/templates/{job-schema-apply.yaml,configmap-schema.yaml}`
   go with the chart). Drop the RAG schema and tables with an explicit,
   reviewed SQL script, never by deleting the PostgreSQL cluster or a
   database PGO manages (PGO does not recreate a dropped database and
   error-loops the whole cluster). Check which other users share the
   cluster first.

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

## Acceptance

No file references the removed components (`grep -rn` returns only ADR
history and CHANGELOG); `check_docs.py` green; CI lint and build workflows
green; on demo333 the step-6 chain passes and no orphan Deployment,
ExternalSecret, Keycloak client or RAG table remains; the PostgreSQL cluster
stays Healthy throughout.

## Open questions

- Do the per-agent charts (`gitops/charts/<agent>/`) carry anything besides
  agent-frontend (routes, ConfigMaps used by UnifAI)? Read before deleting.
- Does the zuno-okf extraction stream (ADR-0506..0510) need a status change
  in the same pass, since its consumer was the aiagent-operator?
