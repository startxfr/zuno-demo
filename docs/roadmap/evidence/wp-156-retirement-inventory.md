# WP-156 retirement inventory (2026-10-23)

Read-only inventory, on `devel` at `e8e9dea3`, of everything that builds,
deploys, configures, tests or documents the six components WP-156 retires:
agent-runtime, agent-bff, agent-frontend, rag-service, rag-ingestion and
aiagent-operator. Nothing was modified. Line numbers are those of that tree
and drift; re-grep before editing.

## Corrections to the WP-156 plan

1. **agent-runtime is installed by the `llm` role, not by `agents`.**
   `ansible/roles/llm/tasks/{install,uninstall,precheck}.yml` apply and
   delete `zuno-agent-runtime-d*` together with ai-gateway. `make d2
   uninstall llm` would remove ai-gateway too: edit the role's loops, do not
   uninstall `llm`.
2. **The `zuno-admin-api` Keycloak client must stay.** MaaS uses it as
   `externalOIDC.clientId` (`gitops/charts/models/values.yaml`,
   `models/templates/maas.yaml`), and every realm client, `unifai` included,
   carries a `maas-gateway-audience` mapper to it. Only the BFF ExternalSecrets
   go.
3. **The OKF sign/publish verb depends on the agent-runtime image.**
   `ansible/tasks/run_okf_signing_job.yml` copies bundles out of
   `agent-runtime:latest`; `ansible/playbooks/day3_sign.yml` force-refreshes
   `agent-runtime-okf-signatures` and waits for the Deployment; the `llm`
   install does a first-run signing. Under ADR-0576..0580 these steps are
   replaced by the zuno-demo-agents release chain and `make d3 admit agents`:
   retire `day3_sign.yml`'s runtime steps together with agent-runtime (WP-165
   also removes the Transit OKF path).

## Shared machinery

- Makefile: `DAY1_RUN_COMPONENTS`/`DAY1_BUILD_COMPONENTS` (aiagent-operator),
  `DAY2_RUN_COMPONENTS` (rag, rag-ingestion, agents),
  `DAY2_BUILD_COMPONENTS` (rag, rag-ingestion, agent), `DAY3_TEST_COMPONENTS`
  and `DAY3_SIGN_COMPONENTS` (agents); help and examples. `DAY3_ADMIT_COMPONENTS`
  (ADR-0580) stays.
- AAP: `gitops/charts/aap-config/values.yaml` survey components and workflow
  DAG nodes (day1 install/check/reconcile/build, day2 install/check/build,
  `zuno-day3-sign`); `ansible/roles/aap_config/defaults/main.yml`.
  `check_docs.py`'s `check_aap_workflow_dags` requires the DAGs and the
  Makefile lists to change together.
- Playbooks: `day1_{install,check,reconcile,uninstall,build}.yml`
  (aiagent_operator, aiagent_operator_build), `day2_{install,check,uninstall,build}.yml`
  (rag, rag_ingestion, agents, rag_build, rag_ingestion_build, agent_build).

## Per component

| Component | Source | Build | Deploy | Main cross-references |
|---|---|---|---|---|
| agent-runtime | `components/agent-runtime` (57 files) | Dockerfile, build-publish matrix, `agent_build` | chart `agent-runtime`, apps `agent-runtime/d0,d1`, role `llm` | NetworkPolicy peers in ai-gateway, mcp-gateway, rag-service; Vault `agent-runtime/*`, `zuno/okf-signatures`; PGO users agent-checkpoints/conversations; `agentRuntimeBaseUrl` in per-agent charts; ai-gateway guardrails comment; dashboards run-trace/usage-cost; `evaluations/tekos/run_scenarios.py` default target |
| agent-bff | `components/agent-bff` (16 files) | Dockerfile, matrix, `agent_build` | per-agent charts tekos/comage/advantage/finage (raw), arkos/naveo (AIAgent CR); role `agents` | `zuno-admin-api` client (keep it), `zuno_bff_*` metrics behind every overview dashboard and `prometheusrule-slo.yaml`; `platform/api/lint_openapi.py` hard-codes its OpenAPI |
| agent-frontend | `components/agent-frontend` (52 files) | Dockerfile, matrix, `agent_build` | same per-agent charts | 8 `<agent>-frontend` Keycloak clients and their ExternalSecrets; Vault session secrets; Redis session store (Redis stays for ai-gateway); connectivity-link quota demo Routes; day2 availability, stresstest, failover probe and acceptance gate jobs |
| rag-service | `components/rag-service` (24 files), `data/rag` | Dockerfile, matrix, `rag_build` | chart `rag-service`, apps `rag/d0,d1`, role `rag` | models NetworkPolicies admitting it; PGO rag-* users and init SQL; mcp-gateway `search_technical_docs` handler and tool policy/bindings; trustyai RAGAS job; OGX server config; `zuno_rag_*` metrics and freshness-lag rule |
| rag-ingestion | `components/rag-ingestion` (12 files) | `rag_ingestion_build` (not in the matrix by design) | chart `rag-ingestion`, apps `rag-ingestion/d0,d1`, role `rag_ingestion` | MariaDB KFP metadata DB; Vault `rag/s3` (shared with mlops, models, mlflow), `rag/embedding`; embedding NetworkPolicy; day2 stresstest layer |
| aiagent-operator | `operator/aiagent-operator` (64 files) | Dockerfile, matrix, `aiagent_operator_build` | chart `aiagent-operator`, apps `aiagent-operator/d0,d1`, role `aiagent_operator`; CRs in charts arkos, naveo | `check_workload_hardening.py` exemptions; `scaffold_agent.py` generates AIAgent CRs; `generate_deployment_snapshot.py` and `agents/arkos/deployment/` |

## Tests and CI that break

- `lint.yml`: the python job (agent-runtime, rag-service, rag-ingestion
  steps), the go job (agent-bff, agent-frontend with its Redis service),
  `lint_openapi.py`, `validate_contract.py`, `generate_deployment_snapshot.py
  --check`, the scaffold test.
- `evaluations/tests/test_tool_calling_conformance.py` reads
  `components/agent-runtime/app/graph/nodes.py`: a hard break.
- `check_build_matrix.py`, `check_workload_hardening.py`, `helm lint`:
  entries and charts must go together.
- `check_docs.py`: day0/day1 role checks, AAP DAGs, printed make commands
  (`make d2 build agent` in `verify_okf_signatures.yml`, `day3_sign.yml`),
  ADR index and supersession reciprocity.
- `platform/supply-chain/{tag_local_release,verify_signatures,pin_release}.py`
  and `pinned-releases.yaml` list these images.

## ADRs

Fully superseded at cutover (ADR-0561, ADR-0564, ADR-0568 planned lists):
0008, 0039, 0044, 0045, 0046, 0054, 0103, 0105, 0204, 0209, 0212, 0215, 0308,
0327, 0342, 0350, 0515, 0519, 0520, 0525. In part: 0015, 0106, 0322, 0330,
0508, 0527, 0534, 0540, 0544. Concern only these components but are in no
planned list (decide): 0042 (browser sessions), 0214 (frontend chrome), 0411
(Vault PKI root for frontend OIDC), 0109 (freshness scoring, in rag-service).

## Risky couplings (live components still depending on the six)

1. `zuno-admin-api` Keycloak client (MaaS, every client's audience mapper).
2. agent-runtime in the `llm` role with ai-gateway.
3. The OKF sign/publish verb and the agent-runtime image.
4. mcp-gateway's `knowledge.tech.search` proxies to rag-service (its
   NetworkPolicy never admitted mcp-gateway, so the path may already be dead;
   code and policy still need removing or retargeting).
5. trustyai-config RAGAS job and `components/trustyai-eval/ragas_eval.py`.
6. mlops reads `document_embeddings` from `rag-tech` with Vault
   `rag/postgresql-app` and runs `evaluations/<agent>/run_acceptance_gate.py`,
   whose default target is agent-runtime/BFF: dropping the RAG tables or that
   credential breaks mlops.
7. Every `evaluations/*` script and the Day 3 probes default to
   runtime/BFF/frontend.
8. Shared PostgreSQL: the RAG and agent databases are PGO `spec.users`
   entries; removing the values deletes roles and grants (never let PGO drop
   a database).
9. Per-agent charts also back the connectivity-link quota demo Routes; Redis
   stays for ai-gateway; frontend client secrets feed eval and probe jobs.
10. Dashboards and SLOs built on BFF and RAG metrics go blank.
11. The onboarding scaffold emits AIAgent CRs and BFF/frontend images: it
    must be rewritten, not just deleted.
12. The OGXServer and the `ogx` database probably become dead config.
