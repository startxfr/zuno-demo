# Zuno Demo

Zuno Demo is an internal MVP demonstrating a reusable agentic AI platform on Red Hat OpenShift AI. The platform hosts an initial catalog of five business agents while keeping runtime components generic and agent behavior declarative.

## Objectives

1. Demonstrate OpenShift AI capabilities for enterprise agentic applications.
2. Deliver five usable internal AI agents.
3. Build a reusable platform where new agents can be onboarded primarily through declarative configuration instead of bespoke platform code.

## MVP target

- Red Hat OpenShift Container Platform 4.22 on AWS, installed with IPI.
- Red Hat OpenShift AI 3.5 (`rhods-operator.3.5.0` GA, `stable-3.5` channel).
- Two worker nodes with one NVIDIA L4 24 GB GPU each.
- About 50 named users, 10 expected concurrent users, and 5 concurrent active conversations as the initial sizing reference.
- First-token objective below 6 seconds for interactive chat paths.
- Long-running document workflows may run for up to 10 minutes.
- Internal MVP first; 99.9% availability is an industrialized-target objective.

## Initial agent catalog

- **Comage** - sales assistant.
- **Tekos** - technical consultant assistant.
- **Arkos** - architecture assistant.
- **Advantage** - sales administration assistant.
- **Finage** - finance assistant.

Each agent has a dedicated frontend and BFF deployment while consuming shared platform services such as the agent runtime, AI/inference gateway, MCP gateway, RAG services, model serving, identity, secrets, observability, and data services.

## v0 build status

- **Tekos** is the sole mandatory end-to-end agent for v0 (ADR-0031): real
  frontend, BFF, Agent Runtime (LangGraph), MCP Gateway, RAG service,
  and Keycloak login with 13 anonymized demo personas
  across two group dimensions — agent entitlement and business role
  (ADR-0040/0041).
- **Comage, Advantage, Finage, Arkos** are catalog-only: OKF definitions
  (structurally validated by `make day2|d2 check agents`), reserved
  namespaces, access-gated portal tiles — no running workflow yet.
  Business-functional builds move to v1; see
  `platform/architecture/agent-platform-separation.md`.
- The AIAgent CRD/operator is retargeted to v1 (ADR-0350).

## Repository principles

- GitHub is the canonical source repository for the demo.
- Documentation and architecture deliverables are written in English and stored as Markdown.
- Architecture decisions are recorded as immutable ADRs covering v0, v1, v2, and v3 evolution.
- Agent definitions use Open Knowledge Format (OKF) v0.2 plus a Zuno-specific extension profile.
- Real commercial data and nominative data must never be committed to this public repository.
- `MEMORY.md` captures the project context so future work can resume consistently.
- Component images are built, scanned, SBOM'd and signed in CI and published under immutable tags (ADR-0115) - see `.github/README.md` and `RELEASING.md`.

## Operator workflow

Three manual inputs, and no secret is ever committed (ADR-0024): the
OpenShift API endpoint and a cluster-admin token; `ansible/confidential.yml`,
copied from the gitignored example and holding this environment's credentials
and per-cluster configuration; and, on a cluster whose catalog has moved past
the pinned build, a deliberate OpenShift AI version choice. Everything else is
automated - `make d0 check` reports anything missing before a first install and
applies nothing. See
[docs/platform/prerequisites.md](docs/platform/prerequisites.md).

```bash
oc login https://api.mycluster.com:6443 --token=<cluster-admin token>
ansible-galaxy collection install -r ansible/requirements.yml

# Day 0 (ADR-0056): cluster prerequisites - operators, CRDs, namespaces,
# secrets. "d0" is a short alias for "day0".
make d0 check
make d0 check namespaces
make d0 install
make d0 all argocd   # check + install, one component

# Day 1 (ADR-0060/ADR-0421): the remaining AI-platform-operator stack -
# mesh, databases, Kueue, OpenShift AI, etc.
make d1 check
make d1 check kiali
make d1 install
make d1 all openshift-ai   # check + install, one component
make d1 reconcile openshift-ai   # diagnose blockers and apply known remediations

# Day 2 (ADR-0060): AI infrastructure (llm, models) and content
# ingestion - build the platform's own component images, then run them.
make d2 build
make d2 install
make d2 check              # ADR-0053 acceptance/security gate for `agents`

# Day 3 (ADR-0057/0058): agent availability test and stresstest.
make d3 test
```

See [docs/README.md](docs/README.md).
