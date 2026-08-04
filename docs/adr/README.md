# Architecture Decision Records

ADRs capture architecture decisions and preserve their history. Existing ADRs are not rewritten to hide later changes. A future decision supersedes an earlier ADR explicitly.

## Status values

- **Accepted** — current architecture decision.
- **Proposed** — expected future decision that still requires implementation validation.
- **Superseded** — replaced by a newer ADR.
- **Deprecated** — retained for history but no longer recommended.

## Version model

- **v0** — seven-day internal MVP baseline.
- **v1** — industrialization and production hardening.
- **v2** — multi-agent and richer interaction capabilities.
- **v3** — advanced optimization, model customization, and self-service.

## ADR template

Each record contains context, decision, alternatives, consequences, security implications, operational implications, and evolution notes.

## Index

- [ADR-0001: Use a monorepo for the Zuno platform](0001-use-a-monorepo-for-the-zuno-platform.md) — **Accepted**, **v0**
- [ADR-0002: Target OpenShift 4.20 with OpenShift AI 3.5 EA2 for the MVP](0002-target-openshift-420-with-openshift-ai-35-ea2-for-the-mvp.md) — **Accepted**, **v0**
- [ADR-0003: Use Make as the operator interface and Ansible as the automation engine](0003-use-make-as-the-operator-interface-and-ansible-as-the-automation-engine.md) — **Accepted**, **v0**
- [ADR-0004: Use GitHub as the canonical project source repository](0004-use-github-as-the-canonical-project-source-repository.md) — **Accepted**, **v0**
- [ADR-0005: Use OKF v0.2 as the declarative agent contract](0005-use-okf-v02-as-the-declarative-agent-contract.md) — **Accepted**, **v0**
- [ADR-0006: Define a Zuno extension profile for OKF](0006-define-a-zuno-extension-profile-for-okf.md) — **Accepted**, **v0**
- [ADR-0007: Separate reusable platform components from agent instances](0007-separate-reusable-platform-components-from-agent-instances.md) — **Accepted**, **v0**
- [ADR-0008: Deploy one frontend and one BFF per agent](0008-deploy-one-frontend-and-one-bff-per-agent.md) — **Accepted**, **v0**
- [ADR-0009: Separate Agent Runtime from AI Inference Gateway](0009-separate-agent-runtime-from-ai-inference-gateway.md) — **Accepted**, **v0**
- [ADR-0010: Use a central MCP Gateway](0010-use-a-central-mcp-gateway.md) — **Accepted**, **v0**
- [ADR-0011: Compute effective tool access as policy intersection](0011-compute-effective-tool-access-as-policy-intersection.md) — **Accepted**, **v0**
- [ADR-0012: Use Keycloak as the central identity provider](0012-use-keycloak-as-the-central-identity-provider.md) — **Accepted**, **v0**
- [ADR-0013: Propagate end-user identity through downstream calls](0013-propagate-end-user-identity-through-downstream-calls.md) — **Accepted**, **v0**
- [ADR-0014: Use delegated user OAuth for Google Workspace](0014-use-delegated-user-oauth-for-google-workspace.md) — **Accepted**, **v0**
- [ADR-0015: Use PostgreSQL with pgvector as the shared data platform](0015-use-postgresql-with-pgvector-as-the-shared-data-platform.md) — **Accepted**, **v0**
- [ADR-0016: Migrate the legacy SXA MySQL schema to PostgreSQL](0016-migrate-the-legacy-sxa-mysql-schema-to-postgresql.md) — **Accepted**, **v0**
- [ADR-0017: Expose sales operations through controlled MCP tools](0017-expose-sales-operations-through-controlled-mcp-tools.md) — **Accepted**, **v0**
- [ADR-0018: Use LangChain and LangGraph with OpenShift AI capabilities](0018-use-langchain-and-langgraph-with-openshift-ai-capabilities.md) — **Accepted**, **v0**
- [ADR-0019: Serve local models through OpenShift AI](0019-serve-local-models-through-openshift-ai.md) — **Accepted**, **v0**
- [ADR-0020: Support governed local and SaaS model routing](0020-support-governed-local-and-saas-model-routing.md) — **Accepted**, **v0**
- [ADR-0021: Route inference according to C1 C2 C3 classification](0021-route-inference-according-to-c1-c2-c3-classification.md) — **Accepted**, **v0**
- [ADR-0022: Manage agent definitions and policies through GitOps review](0022-manage-agent-definitions-and-policies-through-gitops-review.md) — **Accepted**, **v0**
- [ADR-0023: Use one OpenShift namespace per agent](0023-use-one-openshift-namespace-per-agent.md) — **Accepted**, **v0**
- [ADR-0024: Use Vault for application secrets](0024-use-vault-for-application-secrets.md) — **Accepted**, **v0**
- [ADR-0025: Keep real and nominative commercial data out of the public repository](0025-keep-real-and-nominative-commercial-data-out-of-the-public-repository.md) — **Accepted**, **v0**
- [ADR-0026: Provide an AIAgent CRD and operator](0026-provide-an-aiagent-crd-and-operator.md) — **Accepted**, **v0**
- [ADR-0027: Evaluate each initial agent with 20 scenarios and a 75 percent threshold](0027-evaluate-each-initial-agent-with-20-scenarios-and-a-75-percent-threshold.md) — **Accepted**, **v0**
- [ADR-0028: Instrument usage cost routing and distributed traces](0028-instrument-usage-cost-routing-and-distributed-traces.md) — **Accepted**, **v0**
- [ADR-0029: Support command-dispatch Make syntax](0029-support-command-dispatch-make-syntax.md) — **Accepted**, **v0**
- [ADR-0030: Keep ADR history immutable and supersede decisions explicitly](0030-keep-adr-history-immutable-and-supersede-decisions-explicitly.md) — **Accepted**, **v0**
- [ADR-0101: Harden shared services for 99.9 percent target availability](0101-harden-shared-services-for-999-percent-target-availability.md) — **Proposed**, **v1**
- [ADR-0102: Persist and resume long-running workflows](0102-persist-and-resume-long-running-workflows.md) — **Proposed**, **v1**
- [ADR-0103: Automate knowledge freshness and ACL synchronization](0103-automate-knowledge-freshness-and-acl-synchronization.md) — **Proposed**, **v1**
- [ADR-0104: Enforce signed OKF bundles at deployment](0104-enforce-signed-okf-bundles-at-deployment.md) — **Proposed**, **v1**
- [ADR-0105: Block releases on automated model and agent quality gates](0105-block-releases-on-automated-model-and-agent-quality-gates.md) — **Proposed**, **v1**
- [ADR-0106: Harden the platform toward SecNumCloud-oriented controls](0106-harden-the-platform-toward-secnumcloud-oriented-controls.md) — **Proposed**, **v1**
- [ADR-0201: Introduce controlled agent-to-agent communication using A2A](0201-introduce-controlled-agent-to-agent-communication-using-a2a.md) — **Proposed**, **v2**
- [ADR-0202: Introduce governed shared memory and delegation traces](0202-introduce-governed-shared-memory-and-delegation-traces.md) — **Proposed**, **v2**
- [ADR-0203: Add task-specific UI and richer human approval workflows](0203-add-task-specific-ui-and-richer-human-approval-workflows.md) — **Proposed**, **v2**
- [ADR-0204: Automatically remove inaccessible private RAG content](0204-automatically-remove-inaccessible-private-rag-content.md) — **Proposed**, **v2**
- [ADR-0301: Introduce LoRA and PEFT customization through MLOps pipelines](0301-introduce-lora-and-peft-customization-through-mlops-pipelines.md) — **Proposed**, **v3**
- [ADR-0302: Provide self-service agent onboarding through the catalog and operator](0302-provide-self-service-agent-onboarding-through-the-catalog-and-operator.md) — **Proposed**, **v3**
- [ADR-0303: Optimize routing using measured quality cost and latency](0303-optimize-routing-using-measured-quality-cost-and-latency.md) — **Proposed**, **v3**
